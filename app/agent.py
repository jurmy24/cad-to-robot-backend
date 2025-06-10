from pydantic import BaseModel
from typing import Dict, List, Any, AsyncGenerator
from agents import TResponseInputItem
from datetime import datetime

# Agent imports
from agents import (
    Agent,
    ItemHelpers,
    Runner,
    TResponseInputItem,
)
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from openai.types.responses import ResponseTextDeltaEvent
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

# Own imports
from app.tool_calling import faq_lookup_tool, update_seat


# Agent context definition
class AirlineAgentContext(BaseModel):
    passenger_name: str | None = None
    confirmation_number: str | None = None
    seat_number: str | None = None
    flight_number: str | None = None


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
