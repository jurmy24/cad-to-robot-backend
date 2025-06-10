from pydantic import BaseModel
from typing import Dict, List, Any, AsyncGenerator
from agents import TResponseInputItem
from datetime import datetime
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Agent imports
from agents import (
    Agent,
    ItemHelpers,
    Runner,
    TResponseInputItem,
)
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from openai.types.responses import ResponseTextDeltaEvent

# Import CAD to URDF tools
from app.augmented_tools.read_mates import read_mates
from app.augmented_tools.read_urdf import read_urdf
from app.augmented_tools.rename_mates import rename_mates
from app.augmented_tools.remove_duplicate_links import remove_duplicate_links
from app.augmented_tools.set_material import set_material, set_multiple_materials
from app.augmented_tools.run_onshape_conversion import run_onshape_conversion


# Agent context definition for CAD to URDF operations
class CADtoURDFContext(BaseModel):
    robot_name: str | None = None
    current_mates: List[str] = []
    pending_renames: Dict[str, str] = {}
    urdf_issues: List[str] = []
    last_analysis: str | None = None


def load_system_prompt() -> str:
    """Load the system prompt from system_prompts.txt"""
    try:
        with open("system_prompt.txt", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are a CAD to URDF conversion assistant."


# Initialize the CAD to URDF agent
cad_agent = Agent[CADtoURDFContext](
    name="CAD to URDF Agent",
    handoff_description="An intelligent assistant that specializes in converting OnShape assemblies to simulation-ready URDF files.",
    instructions=(
        f"{RECOMMENDED_PROMPT_PREFIX} "
        f"{load_system_prompt()} "
        "\n\nThe robot name you should work with is: folding-mechanism "
        "\n\n## THINKING AND REASONING REQUIREMENTS:"
        "\nYou MUST always write down your thoughts and reasoning before taking any action. "
        "Start each response by explaining:"
        "- What you understand about the current situation"
        "- What you plan to do and why"
        "- What you expect the outcome to be"
        "\n\n## TOOL USAGE REQUIREMENTS:"
        "\nBefore using any tool, you MUST explain to the user what you're going to do. "
        "For example: "
        "- Before reading mates: 'Let me analyze the current mate names in your assembly.' "
        "- Before renaming mates: 'I'll update the mate names to use proper dof_ prefixes for joint recognition.' "
        "- Before removing duplicates: 'I'll identify and remove duplicate links from your URDF file.' "
        "- Before setting materials: 'I'll update the visual appearance of the specified links.' "
        "\n\n## POST-URDF CONVERSION REQUIREMENTS:"
        "\nAfter attempting URDF conversion (using run_onshape_conversion), you MUST:"
        "1. **IF CONVERSION FAILED**: Analyze the error message and take corrective action first"
        "   - If PLANAR mates are mentioned, use rename_mates to fix them"
        "   - **AFTER fixing mates, IMMEDIATELY run run_onshape_conversion again**"
        "   - If other mate issues exist, address them before retrying"
        "2. **IF CONVERSION SUCCEEDED**: Immediately read and analyze the generated URDF file"
        "3. Check for duplicate links and remove them if found"
        "4. Verify mate names and rename them if they don't follow dof_ conventions"
        "5. Assess if materials need to be set for better visualization"
        "6. Provide a comprehensive summary of all changes made"
        "\n\n## CAD DATA MODIFICATION REQUIREMENTS:"
        "\nIMPORTANT: If you modify any CAD-related files, you MUST rebuild the URDF!"
        "\nAfter using tools that modify CAD data (like rename_mates), you MUST:"
        "1. **IMMEDIATELY** run run_onshape_conversion again to rebuild the URDF"
        "2. The URDF file becomes outdated when CAD data changes"
        "3. Always regenerate before doing URDF analysis or further modifications"
        "\nCAD data modifications include:"
        "- Renaming mates (changes assembly structure)"
        "- Modifying config.json or assembly_data.json"
        "- Any changes to joint/mate definitions"
        "\n\n## FAILURE HANDLING:"
        "\nNEVER stop after a tool failure. Always:"
        "- Analyze the error message carefully"
        "- Determine what corrective action is needed"
        "- Use appropriate tools to fix the issues"
        "- Continue with the workflow until completion"
        "\n\nAlways explain what changes you're making and why they're necessary for proper URDF conversion. "
        "Use the ReAct framework: Think, Act, Observe, Reflect."
    ),
    tools=[
        run_onshape_conversion,
        read_mates,
        read_urdf,
        rename_mates,
        remove_duplicate_links,
        set_material,
        set_multiple_materials,
    ],
)

# Store conversation context and pending tool calls
conversation_contexts: Dict[str, CADtoURDFContext] = {}
conversation_history: Dict[str, List[TResponseInputItem]] = {}
pending_tool_calls: Dict[str, Dict[str, Any]] = {}


def get_tool_access_level(tool_name: str) -> str:
    """Determine if a tool requires approval (write) or can run immediately (read)"""
    write_tools = {
        "run_onshape_conversion",
        "rename_mates",
        "remove_duplicate_links",
        "set_material",
        "set_multiple_materials",
    }
    return "write" if tool_name in write_tools else "read"


async def get_agent_response(
    message: str, client_id: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Get response from the CAD to URDF agent system and format it for WebSocket.
    """
    # Initialize context and history for this client if not exists
    if client_id not in conversation_contexts:
        conversation_contexts[client_id] = CADtoURDFContext(
            robot_name="folding-mechanism"
        )
        conversation_history[client_id] = []

    context = conversation_contexts[client_id]
    history = conversation_history[client_id]

    # Add user message to history
    history.append({"content": message, "role": "user"})

    try:
        # Run the agent
        result = Runner.run_streamed(cad_agent, history, context=context)

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
                    access = get_tool_access_level(tool_name)

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
                        # For testing, auto-approve write operations and continue
                        approval_response = await handle_tool_approval(call_id, True)
                        if approval_response["type"] == "tool_observation":
                            yield approval_response
                        # Continue processing instead of returning

                elif event.item.type == "tool_call_output_item":
                    # Tool execution completed
                    if current_tool_call:
                        # Update context based on tool results
                        await update_context_from_tool_result(
                            context, current_tool_call["name"], event.item.output
                        )

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
            "content": f"Error processing CAD to URDF request: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "sender": "system",
        }


async def update_context_from_tool_result(
    context: CADtoURDFContext, tool_name: str, output: str
):
    """Update the context based on tool execution results"""
    if tool_name == "run_onshape_conversion":
        # Record OnShape conversion attempt (success or failure)
        context.last_analysis = output
        if "✅" in output:
            context.urdf_issues.append("OnShape conversion completed")
        elif "❌" in output:
            context.urdf_issues.append("OnShape conversion failed - needs mate fixes")
            # Extract specific error information
            if "planar_1" in output.lower():
                context.pending_renames["planar_1"] = "needs_dof_prefix"
            if "PLANAR" in output and "not supported" in output:
                context.urdf_issues.append("PLANAR mate types need to be renamed")
    elif tool_name == "read_mates":
        # Extract mate names from the output
        if "ROBOT MATE NAMES" in output:
            context.last_analysis = output
            # Could parse mate names from output if needed
    elif tool_name == "read_urdf":
        # Store URDF analysis
        context.last_analysis = output
    elif tool_name == "rename_mates":
        # Clear pending renames if successful, but mark URDF as needing rebuild
        if "✅" in output:
            context.pending_renames = {}
            context.urdf_issues.append("URDF needs rebuild - CAD data was modified")
        elif "❌" in output:
            context.urdf_issues.append("Mate renaming failed - needs attention")
    elif tool_name in [
        "remove_duplicate_links",
        "set_material",
        "set_multiple_materials",
    ]:
        # Record that modifications were made
        if "✅" in output:
            if "issues" not in [issue.lower() for issue in context.urdf_issues]:
                context.urdf_issues.append(f"Modified with {tool_name}")


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
        # Execute the tool - actually call the real tool functions
        tool_name = tool_info["tool_call"]["name"]
        args = tool_info["tool_call"]["arguments"]

        try:
            if tool_name == "run_onshape_conversion":
                from app.augmented_tools.run_onshape_conversion import (
                    run_onshape_conversion,
                )

                robot_name = args.get("robot_name", "folding-mechanism")
                output = await run_onshape_conversion(robot_name)

            elif tool_name == "rename_mates":
                from app.augmented_tools.rename_mates import rename_mates

                robot_name = args.get("robot_name", "folding-mechanism")
                rename_mapping_json = args.get("rename_mapping_json", "{}")
                output = await rename_mates(robot_name, rename_mapping_json)

            elif tool_name == "remove_duplicate_links":
                from app.augmented_tools.remove_duplicate_links import (
                    remove_duplicate_links,
                )

                robot_name = args.get("robot_name", "folding-mechanism")
                output = await remove_duplicate_links(robot_name)

            elif tool_name == "set_material":
                from app.augmented_tools.set_material import set_material

                robot_name = args.get("robot_name", "folding-mechanism")
                link_name = args.get("link_name", "unknown")
                rgba = args.get("rgba", "1 0 0 1")
                output = await set_material(robot_name, link_name, rgba)

            elif tool_name == "set_multiple_materials":
                from app.augmented_tools.set_material import set_multiple_materials

                robot_name = args.get("robot_name", "folding-mechanism")
                materials_json = args.get("materials_json", "{}")
                output = await set_multiple_materials(robot_name, materials_json)

            else:
                output = f"❌ Unknown tool: {tool_name}"

        except Exception as e:
            output = f"❌ Error executing {tool_name}: {str(e)}"

        # Update context
        client_id = tool_info["client_id"]
        if client_id in conversation_contexts:
            await update_context_from_tool_result(
                conversation_contexts[client_id], tool_name, output
            )

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
            "content": f"CAD to URDF tool execution was rejected by user",
            "timestamp": datetime.now().isoformat(),
            "sender": "system",
        }


# Additional helper function for getting robot status
async def get_robot_status(client_id: str) -> Dict[str, Any]:
    """Get current status of the robot conversion process"""
    if client_id not in conversation_contexts:
        return {"error": "No active session found"}

    context = conversation_contexts[client_id]
    return {
        "robot_name": context.robot_name,
        "current_mates": context.current_mates,
        "pending_renames": context.pending_renames,
        "urdf_issues": context.urdf_issues,
        "has_analysis": context.last_analysis is not None,
    }


if __name__ == "__main__":
    import asyncio
    import os

    async def test_agent():
        """Test the CAD to URDF agent with folding-mechanism data in a single interaction"""
        # Change to parent directory so tools can find data/ folder
        original_cwd = os.getcwd()
        if os.path.basename(os.getcwd()) == "app":
            os.chdir("..")
            print(f"Changed directory from {original_cwd} to {os.getcwd()}")

        robot_name = "folding-mechanism"
        test_client_id = "test_client"

        print("🤖 CAD to URDF Agent Demo - Single Interaction")
        print("=" * 60)
        print(f"Robot: {robot_name}")
        print(f"Data directory: data/{robot_name}")
        print(f"Current working directory: {os.getcwd()}")
        print("=" * 60)

        # Single comprehensive message that leverages the system prompt
        comprehensive_message = """Please perform a complete CAD to URDF conversion workflow for the folding-mechanism robot. I need you to:

1. First, run the OnShape to URDF conversion tool to generate an initial URDF file
2. Analyze the current assembly by reading the existing mates to understand the joint structure
3. Examine the existing URDF file to identify any issues or areas that need improvement
4. Based on your analysis, fix any issues you find including:
   - Renaming mates to use proper dof_ prefixes for joint recognition 
   - Removing any duplicate links from the URDF
   - Setting appropriate materials for visual appearance if needed
   - Any other improvements to make the URDF simulation-ready

Please work through this systematically, explaining each step and the reasoning behind your actions. Use your available tools to analyze, diagnose, and fix the robot's URDF configuration."""

        print("\n🧠 Running Complete CAD to URDF Workflow...")
        print("-" * 40)

        await run_agent_interaction(
            test_client_id, comprehensive_message, "Complete Workflow"
        )

        # Final status
        print("\n" + "=" * 60)
        print("Final Robot Status:")
        status = await get_robot_status(test_client_id)
        for key, value in status.items():
            print(f"  {key}: {value}")
        print("=" * 60)
        print("🎉 Single interaction demo completed!")

        # Restore original directory
        os.chdir(original_cwd)

    async def run_agent_interaction(client_id: str, message: str, phase_name: str):
        """Run a single agent interaction and handle the responses"""
        full_response = ""

        try:
            async for response in get_agent_response(message, client_id):
                if response["type"] == "stream":
                    # Just accumulate, don't print each token
                    full_response = response["content"]
                elif response["type"] == "tool_action":
                    tool_action = response["tool_action"]
                    print(f"\n🔧 Tool Action: {tool_action['name']}")
                    print(f"   Arguments: {tool_action['arguments']}")
                    print(f"   Access Level: {tool_action['access']}")

                    # For testing, auto-approve write operations
                    if tool_action["access"] == "write":
                        print("   ✅ Auto-approving for demo...")
                        approval_response = await handle_tool_approval(
                            tool_action["call_id"], True
                        )
                        if approval_response["type"] == "tool_observation":
                            print(
                                f"   Result: {approval_response['tool_observation']['output']}"
                            )

                elif response["type"] == "tool_observation":
                    print(f"🔍 Tool Result: {response['tool_observation']['output']}")
                elif response["type"] == "error":
                    print(f"❌ Error: {response['content']}")
                elif response["type"] == "stream_complete":
                    # Print the final accumulated response
                    if full_response.strip():
                        print(f"\n💬 {phase_name} Response:")
                        print(full_response)
                    print(f"\n✅ {phase_name} completed")
                    break
        except Exception as e:
            print(f"❌ {phase_name} failed with error: {str(e)}")

    # Run the async test
    asyncio.run(test_agent())
