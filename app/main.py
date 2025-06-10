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


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            # Handle tool approval responses
            if message_data.get("type") == "tool_approval_response":
                call_id = message_data.get("call_id")
                approved = message_data.get("approved", False)

                if call_id:
                    response = await handle_tool_approval(call_id, approved)
                    await manager.send_personal_message(json.dumps(response), client_id)
            else:
                # Use agent responses for regular messages
                async for response in get_agent_response(
                    message_data.get("content", ""), client_id
                ):
                    await manager.send_personal_message(json.dumps(response), client_id)

    except WebSocketDisconnect:
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
