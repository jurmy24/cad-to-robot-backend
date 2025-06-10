from fastapi import (
    FastAPI,
    File,
    UploadFile,
    Request,
    HTTPException,
    Form,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, AsyncGenerator, Any
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import os
import zipfile
import tempfile
import shutil
import json
import asyncio
from pathlib import Path
from app.agent import get_agent_response, handle_tool_approval
from app.services.run_onshape_to_robot import run_onshape_to_robot
from app.websockets import manager


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # Your frontend URL
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Ensure data directory exists
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# Store active requests for cancellation
active_requests: Dict[str, asyncio.Task] = {}


@app.get("/")
async def root():
    return {"message": "OnShape Robot Processing API"}


@app.post("/upload_robot")
async def upload_robot(
    request: Request, robot_zip: UploadFile = File(...), robot_name: str = Form(...)
):
    """
    Endpoint to receive robot zip files from frontend, process them with onshape-to-robot,
    and return the generated URDF files as a zip.
    """

    # Validate file type
    if not robot_zip.filename or not robot_zip.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a zip file")

    # Validate robot name
    if not robot_name or not robot_name.strip():
        raise HTTPException(status_code=400, detail="Robot name is required")

    # Create directories
    robot_data_dir = DATA_DIR / robot_name
    robot_data_dir.mkdir(exist_ok=True)

    temp_dir = None
    try:
        # Read uploaded file
        file_contents = await robot_zip.read()

        print(f"Processing robot upload: {robot_zip.filename}")
        print(f"Robot name: {robot_name}")
        print(f"File size: {len(file_contents)} bytes")
        print(f"Robot directory: {robot_data_dir}")

        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, "robot.zip")

        # Write zip file to temp location
        with open(zip_path, "wb") as f:
            f.write(file_contents)

        # Extract zip to robot data directory
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(robot_data_dir)

        print(f"Extracted zip contents to: {robot_data_dir}")

        # List extracted files for debugging
        extracted_files = list(robot_data_dir.rglob("*"))
        print(
            f"Extracted files: {[str(f.relative_to(robot_data_dir)) for f in extracted_files if f.is_file()]}"
        )

        # Run onshape-to-robot processing
        print("Starting onshape-to-robot processing...")
        success, logs, error_message = run_onshape_to_robot(str(robot_data_dir))

        if not success:
            raise HTTPException(
                status_code=500, detail=f"Robot processing failed: {error_message}"
            )

        # Look for generated URDF and mesh files
        output_files = (
            list(robot_data_dir.rglob("*.urdf"))
            + list(robot_data_dir.rglob("*.stl"))
            + list(robot_data_dir.rglob("*.dae"))
        )

        if not output_files:
            raise HTTPException(
                status_code=500, detail="No URDF or mesh files were generated"
            )

        # Create output zip with generated files
        output_zip_path = robot_data_dir / f"{robot_name}_output.zip"

        with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in output_files:
                # Add file to zip with relative path
                arcname = file_path.relative_to(robot_data_dir)
                zipf.write(file_path, arcname)

        print(f"Created output zip: {output_zip_path}")
        print(f"Processing completed successfully!")

        # Return the zip file directly
        return FileResponse(
            path=output_zip_path,
            filename=f"{robot_name}_output.zip",
            media_type="application/zip",
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        # Clean up temporary directory
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


async def stream_response(message: str) -> AsyncGenerator[str, None]:
    """
    Helper function to simulate streaming a response.
    In a real implementation, this would be replaced with actual AI streaming.
    """
    # Split the message into words to simulate streaming
    words = message.split()
    for word in words:
        # Simulate some processing time
        await asyncio.sleep(0.1)
        yield word + " "


async def send_urdf_file(client_id: str, robot_name: str = "default-robot"):
    """Send the current URDF file content to the client"""
    try:
        # Look for URDF file in the robot directory
        robot_dir = DATA_DIR / robot_name
        possible_urdf_paths = [
            robot_dir / "robot.urdf",
            robot_dir / f"{robot_name}.urdf",
            *list(robot_dir.glob("*.urdf")),
        ]

        urdf_path = None
        for path in possible_urdf_paths:
            if path.exists():
                urdf_path = path
                break

        if urdf_path and urdf_path.exists():
            with open(urdf_path, "r", encoding="utf-8") as f:
                urdf_content = f.read()

            urdf_response = {
                "type": "urdf_file",
                "urdf_content": urdf_content,
                "file_path": str(urdf_path.relative_to(DATA_DIR)),
                "timestamp": datetime.now().isoformat(),
                "sender": "system",
            }
            await manager.send_personal_message(json.dumps(urdf_response), client_id)
        else:
            # URDF file not found
            error_response = {
                "type": "urdf_error",
                "content": f"URDF file not found in {robot_dir}",
                "timestamp": datetime.now().isoformat(),
                "sender": "system",
            }
            await manager.send_personal_message(json.dumps(error_response), client_id)

    except Exception as e:
        error_response = {
            "type": "urdf_error",
            "content": f"Error reading URDF file: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "sender": "system",
        }
        await manager.send_personal_message(json.dumps(error_response), client_id)


async def handle_agent_request(message: str, client_id: str, request_id: str):
    """Handle agent request with cancellation support"""
    try:
        async for response in get_agent_response(message, client_id):
            # Check if request was cancelled
            if request_id not in active_requests:
                print(f"Request {request_id} was cancelled")
                return

            await manager.send_personal_message(json.dumps(response), client_id)

            # Check if this was a successful tool observation for URDF-modifying tools
            if response.get("type") == "tool_observation" and "✅" in response.get(
                "tool_observation", {}
            ).get("output", ""):
                output = response.get("tool_observation", {}).get("output", "")
                # Check if any URDF-modifying operations completed successfully
                if any(
                    keyword in output.lower()
                    for keyword in [
                        "onshape",
                        "conversion completed",
                        "duplicate",
                        "removed",
                        "material",
                        "urdf",
                        "robot processing completed",
                    ]
                ):
                    await send_urdf_file(client_id)
    except asyncio.CancelledError:
        print(f"Agent request {request_id} was cancelled")
        # Send cancellation confirmation
        cancellation_response = {
            "type": "cancellation_confirmed",
            "content": "Request cancelled",
            "timestamp": datetime.now().isoformat(),
            "sender": "assistant",
            "request_id": request_id,
        }
        await manager.send_personal_message(
            json.dumps(cancellation_response), client_id
        )
    except Exception as e:
        print(f"Error in agent request {request_id}: {e}")
    finally:
        # Clean up active request
        if request_id in active_requests:
            del active_requests[request_id]


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            # Extract robot_name from message data, with fallback to default
            robot_name = message_data.get("robot_name", "stable-wheel-legged")

            # Handle tool approval responses
            if message_data.get("type") == "tool_approval_response":
                call_id = message_data.get("call_id")
                approved = message_data.get("approved", False)

                if call_id:
                    response = await handle_tool_approval(call_id, approved)
                    await manager.send_personal_message(json.dumps(response), client_id)

                    # Check if this was a URDF-modifying tool that succeeded
                    if (
                        approved
                        and response.get("type") == "tool_observation"
                        and response.get("tool_observation", {})
                        .get("output", "")
                        .startswith("✅")
                    ):
                        # Extract tool name from the response (this is a bit hacky, but works)
                        output = response.get("tool_observation", {}).get("output", "")
                        urdf_modifying_tools = [
                            "run_onshape_conversion",
                            "remove_duplicate_links",
                            "set_material",
                            "set_multiple_materials",
                        ]

                        # Check if any of the URDF-modifying tools were mentioned in the output
                        for tool_name in urdf_modifying_tools:
                            if any(
                                keyword in output.lower()
                                for keyword in [
                                    "onshape",
                                    "conversion",
                                    "duplicate",
                                    "material",
                                    "urdf",
                                ]
                            ):
                                await send_urdf_file(client_id)
                            if any(keyword in output.lower() for keyword in [
                                "onshape", "conversion", "duplicate", "material", "urdf"
                            ]):
                                await send_urdf_file(client_id, robot_name)
                                break
            else:
                # Use agent responses for regular messages
                async for response in get_agent_response(
                    message_data.get("content", ""), client_id, robot_name
                ):
                    await manager.send_personal_message(json.dumps(response), client_id)
                    
                    # Check if this was a successful tool observation for URDF-modifying tools
                    if (response.get("type") == "tool_observation" and 
                        "✅" in response.get("tool_observation", {}).get("output", "")):
                        
                        output = response.get("tool_observation", {}).get("output", "")
                        # Check if any URDF-modifying operations completed successfully
                        if any(keyword in output.lower() for keyword in [
                            "onshape", "conversion completed", "duplicate", "removed", 
                            "material", "urdf", "robot processing completed"
                        ]):
                            await send_urdf_file(client_id, robot_name)

    except WebSocketDisconnect:
        # Cancel all active requests for this client
        tasks_to_cancel = [
            task
            for request_id, task in active_requests.items()
            # You might want to associate request_id with client_id if needed
        ]
        for task in tasks_to_cancel:
            task.cancel()

        manager.disconnect(client_id)
        await manager.broadcast(
            json.dumps(
                {
                    "type": "system",
                    "content": f"Client {client_id} left the chat",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )
