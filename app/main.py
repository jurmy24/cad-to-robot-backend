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
import uuid
import json
import asyncio
from pathlib import Path
from app.services.run_onshape_to_robot import run_onshape_to_robot

# Agent imports
from agents import (
    Agent,
    ItemHelpers,
    RunContextWrapper,
    Runner,
    TResponseInputItem,
    function_tool,
)
from openai.types.responses import ResponseTextDeltaEvent
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX


# Agent context definition
class AirlineAgentContext(BaseModel):
    passenger_name: str | None = None
    confirmation_number: str | None = None
    seat_number: str | None = None
    flight_number: str | None = None


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


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_personal_message(self, message: str, client_id: str):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            await connection.send_text(message)


manager = ConnectionManager()


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


@app.post("/message")
async def message(request: Request, message: str = Form(...)):
    print(f"Received message: {message}")

    return JSONResponse(
        content={
            "message": "Message received. I would like to thank you for helping me receive this beautiful message from you!"
        }
    )


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


# Store conversation context and pending tool calls
conversation_contexts: Dict[str, AirlineAgentContext] = {}
conversation_history: Dict[str, List[TResponseInputItem]] = {}
pending_tool_calls: Dict[str, Dict[str, Any]] = {}


async def get_agent_response(
    message: str, client_id: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Get response from the actual agent system and format it for WebSocket.
    """
    # Initialize context and history for this client if not exists
    if client_id not in conversation_contexts:
        conversation_contexts[client_id] = AirlineAgentContext()
        conversation_history[client_id] = []

    context = conversation_contexts[client_id]
    history = conversation_history[client_id]

    # Add user message to history
    history.append({"content": message, "role": "user"})

    try:
        # Run the agent
        result = Runner.run_streamed(triage_agent, history, context=context)

        current_streaming_content = ""
        current_tool_call = None

        async for event in result.stream_events():
            if event.type == "raw_response_event" and isinstance(
                event.data, ResponseTextDeltaEvent
            ):
                # Stream text response
                delta_content = event.data.delta
                current_streaming_content += delta_content
                yield {
                    "type": "stream",
                    "content": current_streaming_content,
                    "timestamp": datetime.now().isoformat(),
                    "sender": "assistant",
                }

            elif event.type == "run_item_stream_event":
                if event.item.type == "tool_call_item":
                    # Tool call started - use safe attribute access
                    tool_call = event.item.raw_item
                    tool_name = getattr(
                        tool_call, "name", str(type(tool_call).__name__)
                    )
                    tool_args = getattr(tool_call, "arguments", {})
                    call_id = getattr(tool_call, "id", str(hash(str(tool_call))))

                    # Determine access level
                    access = "write" if tool_name == "update_seat" else "read"

                    current_tool_call = {
                        "name": tool_name,
                        "arguments": tool_args,
                        "call_id": call_id,
                        "access": access,
                    }

                    yield {
                        "type": "tool_action",
                        "tool_action": current_tool_call,
                        "timestamp": datetime.now().isoformat(),
                        "sender": "system",
                    }

                    # If it's a write operation, store it as pending and wait for approval
                    if access == "write":
                        pending_tool_calls[call_id] = {
                            "client_id": client_id,
                            "tool_call": current_tool_call,
                            "event_item": event.item,
                        }
                        # Don't yield tool_observation yet, wait for approval
                        return

                elif event.item.type == "tool_call_output_item":
                    # Tool execution completed
                    if current_tool_call:
                        yield {
                            "type": "tool_observation",
                            "tool_observation": {
                                "call_id": current_tool_call["call_id"],
                                "output": event.item.output,
                            },
                            "timestamp": datetime.now().isoformat(),
                            "sender": "system",
                        }

                elif event.item.type == "message_output_item":
                    # Final message from agent
                    final_content = ItemHelpers.text_message_output(event.item)
                    history.append(
                        {
                            "content": final_content,
                            "role": "assistant",
                        }
                    )

        # Send completion message
        yield {
            "type": "stream_complete",
            "timestamp": datetime.now().isoformat(),
            "sender": "system",
        }

    except Exception as e:
        yield {
            "type": "error",
            "content": f"Error processing request: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "sender": "system",
        }


async def handle_tool_approval(call_id: str, approved: bool) -> Dict[str, Any]:
    """
    Handle tool approval response and continue execution if approved.
    """
    if call_id not in pending_tool_calls:
        return {
            "type": "error",
            "content": "Tool call not found or already processed",
            "timestamp": datetime.now().isoformat(),
            "sender": "system",
        }

    tool_info = pending_tool_calls[call_id]

    if approved:
        # Execute the tool (simulate the execution result)
        tool_name = tool_info["tool_call"]["name"]

        if tool_name == "update_seat":
            # Simulate successful seat update
            args = tool_info["tool_call"]["arguments"]
            confirmation = args.get("confirmation_number", "ABC123")
            new_seat = args.get("new_seat", "12A")
            output = f"Successfully updated seat to {new_seat} for confirmation {confirmation}"
        else:
            output = f"Tool {tool_name} executed successfully"

        # Clean up pending call
        del pending_tool_calls[call_id]

        return {
            "type": "tool_observation",
            "tool_observation": {"call_id": call_id, "output": output},
            "timestamp": datetime.now().isoformat(),
            "sender": "system",
        }
    else:
        # Tool was rejected
        del pending_tool_calls[call_id]

        return {
            "type": "tool_rejected",
            "content": f"Tool execution was rejected by user",
            "timestamp": datetime.now().isoformat(),
            "sender": "system",
        }


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


@function_tool(
    name_override="faq_lookup_tool",
    description_override="Lookup frequently asked questions.",
)
async def faq_lookup_tool(question: str) -> str:
    if "bag" in question or "baggage" in question:
        return (
            "You are allowed to bring one bag on the plane. "
            "It must be under 50 pounds and 22 inches x 14 inches x 9 inches."
        )
    elif "seats" in question or "plane" in question:
        return (
            "There are 120 seats on the plane. "
            "There are 22 business class seats and 98 economy seats. "
            "Exit rows are rows 4 and 16. "
            "Rows 5-8 are Economy Plus, with extra legroom. "
        )
    elif "wifi" in question:
        return "We have free wifi on the plane, join Airline-Wifi"
    return "I'm sorry, I don't know the answer to that question."


@function_tool
async def update_seat(
    context: RunContextWrapper[AirlineAgentContext],
    confirmation_number: str,
    new_seat: str,
) -> str:
    """
    Update the seat for a given confirmation number.

    Args:
        confirmation_number: The confirmation number for the flight.
        new_seat: The new seat to update to.
    """
    # Update the context based on the customer's input
    context.context.confirmation_number = confirmation_number
    context.context.seat_number = new_seat
    # Generate a flight number if not set
    if context.context.flight_number is None:
        import random

        context.context.flight_number = f"FLT-{random.randint(100, 999)}"
    return f"Updated seat to {new_seat} for confirmation number {confirmation_number}"


# Initialize the agent
triage_agent = Agent[AirlineAgentContext](
    name="Triage Agent",
    handoff_description="A helpful agent that can handle all airline-related requests.",
    instructions=(
        f"{RECOMMENDED_PROMPT_PREFIX} "
        "You are a helpful airline assistant that can handle all customer requests. "
        "You have access to tools for both answering questions and updating seat bookings. "
        "Before using any tool, you MUST explain to the customer what you're going to do. "
        "For example: "
        "- Before using the FAQ tool: 'Let me look up that information for you about our baggage policy.' "
        "- Before using the seat update tool: 'I'll help you update your seat. I'll need your confirmation number and desired seat number.' "
        "Always be friendly and professional in your explanations. "
        "If you need more information from the customer, ask for it clearly and explain why you need it."
    ),
    tools=[faq_lookup_tool, update_seat],
)
