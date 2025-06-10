from typing import Dict
from agents import RunContextWrapper, function_tool
from app.agent import AirlineAgentContext
from app.tools.read_urdf import read_urdf
from app.tools.remove_duplicate_links import remove_duplicate_links
from app.tools.rename_mates import rename_mates
from app.tools.read_mates import read_mates
from app.tools.set_link_materials import MaterialInfo, set_link_materials


@function_tool(
    name_override="read_urdf_tool",
    description_override="Read the URDF file for a given robot name.",
)
async def read_urdf_tool(robot_name: str) -> str:
    """
    Read and analyze URDF file information.

    This tool reformats URDF files into LLM-friendly summaries that preserve
    all important information while using fewer tokens.

    Args:
        robot_name: Name of the robot (e.g., "folding-mechanism")

    Returns:
        Formatted string containing robot summary with link count, joint count,
        materials count, mesh files, joint types breakdown, and lists of all
        link and joint names.

    Raises:
        FileNotFoundError: If URDF file doesn't exist in robots/{robot_name}/robot.urdf
        RuntimeError: If parsing fails or other errors occur
    """
    return read_urdf(robot_name)


@function_tool(
    name_override="remove_duplicate_links_tool",
    description_override="Remove duplicate links from the URDF file for a given robot name.",
)
async def remove_duplicate_links_tool(robot_name: str) -> str:
    """
    Remove duplicate links from URDF files.

    This tool identifies and removes duplicate links that have identical:
    - Mesh files (visual and collision)
    - Origins (xyz, rpy coordinates)

    Automatically detects duplicates and removes them while keeping the first
    occurrence of each duplicate group. Also removes associated joints that
    reference the removed links.

    Args:
        robot_name: Name of the robot (e.g., "folding-mechanism")

    Returns:
        Human-readable string describing what duplicate links were found and removed,
        including backup file information and affected joints count.

    Raises:
        FileNotFoundError: If URDF file doesn't exist in robots/{robot_name}/robot.urdf
        RuntimeError: If processing fails or other errors occur
    """
    return remove_duplicate_links(robot_name)


@function_tool(
    name_override="rename_mates_tool",
    description_override="Rename mates in the URDF file for a given robot name.",
)
async def rename_mates_tool(robot_name: str, rename_mapping: Dict[str, str]) -> str:
    """
    Rename mates consistently across robot JSON files.

    This tool renames mate names in all three robot JSON files:
    - matevalues_data.json (contains "mateName" field)
    - features_data.json (contains "name" field in mate features)
    - assembly_data.json (contains "name" field in features)

    Args:
        robot_name: Name of the robot (e.g., "folding-mechanism")
        rename_mapping: Dictionary mapping old mate names to new mate names
                       Example: {"Revolute 1": "dof_revolute_1", "Planar 1": "dof_base_joint"}

    Returns:
        Human-readable string describing what renames were performed, including
        total instances renamed, files updated, and any validation errors.

    Raises:
        FileNotFoundError: If robot JSON files don't exist in robots/{robot_name}/
        ValueError: If invalid mate names are provided in rename_mapping
        RuntimeError: If renaming operation fails
    """
    return rename_mates(robot_name, rename_mapping)


@function_tool(
    name_override="read_mates_tool",
    description_override="Read the mates in the URDF file for a given robot name.",
)
async def read_mates_tool(robot_name: str) -> str:
    """
    Read and analyze mate names from robot assembly JSON files.

    This tool analyzes the robot assembly files to extract mate information including:
    - List of all unique mate names found across all files
    - File-by-file breakdown showing which mates are in each file
    - Inconsistency analysis (missing mates, count mismatches)
    - Duplicate detection within files
    - Analysis of naming conventions (e.g., which mates have "dof_" prefix)

    Args:
        robot_name: Name of the robot (e.g., "folding-mechanism")

    Returns:
        Formatted string containing comprehensive mate analysis including counts,
        inconsistencies, file loading issues, and recommendations for proper
        naming conventions.

    Raises:
        FileNotFoundError: If no JSON files can be found in robots/{robot_name}/
        RuntimeError: If parsing fails or other errors occur
    """
    return read_mates(robot_name)


@function_tool(
    name_override="set_link_materials_tool",
    description_override="Set the materials for the links in the URDF file for a given robot name.",
)
async def set_link_materials_tool(
    robot_name: str, link_materials: Dict[str, MaterialInfo]
) -> str:
    """
    Set materials/colors for multiple links in URDF file.

    This tool modifies the visual appearance of links by setting their material
    colors using RGBA values. It can set materials for multiple links at once
    and will create or modify the visual/material/color elements as needed.

    Args:
        robot_name: Name of the robot (e.g., "folding-mechanism")
        link_materials: Dictionary mapping link names to MaterialInfo objects
                       Example: {"back_left_axle": MaterialInfo(rgba="0.8 0.2 0.2 1.0", name="red_material")}

    Returns:
        Human-readable string describing what materials were set, including
        success count, backup file location, and any links that failed to update.

    Raises:
        FileNotFoundError: If URDF file doesn't exist in robots/{robot_name}/robot.urdf
        RuntimeError: If material setting fails or other errors occur
    """
    return set_link_materials(robot_name, link_materials)


####################################################################33


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
