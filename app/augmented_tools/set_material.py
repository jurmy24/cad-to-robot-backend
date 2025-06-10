#!/usr/bin/env python3
"""
Set materials for links in URDF files as a function_tool.
"""

import xml.etree.ElementTree as ET
import json
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass
from agents import function_tool
import json

@dataclass
class MaterialInfo:
    """Information about a material to be set.

    Example:
        MaterialInfo(rgba="0.8 0.2 0.2 1.0", name="red_material")
        MaterialInfo(rgba="0.2 0.8 0.2 1.0")  # Without material name
    """
    rgba: str  # RGBA color values as space-separated string (e.g. "0.8 0.2 0.2 1.0")
    name: Optional[str] = None  # Optional material name (e.g. "red_material")


class URDFMaterialModifier:
    def __init__(self, urdf_file: str):
        self.urdf_file = urdf_file
        self.tree = ET.parse(urdf_file)
        self.root = self.tree.getroot()

    def set_link_material(self, link_name: str, material_info: MaterialInfo) -> bool:
        """Set the material for a specific link."""
        # Find the link
        link = self.root.find(f".//link[@name='{link_name}']")
        if link is None:
            return False

        # Find or create visual element
        visual = link.find("visual")
        if visual is None:
            visual = ET.SubElement(link, "visual")
            # Copy geometry from collision if it exists
            collision = link.find("collision")
            if collision is not None:
                geometry = collision.find("geometry")
                if geometry is not None:
                    visual.append(ET.fromstring(ET.tostring(geometry)))

        # Find or create material element
        material = visual.find("material")
        if material is None:
            material = ET.SubElement(visual, "material")

        # Set material name if provided
        if material_info.name:
            material.set("name", material_info.name)

        # Find or create color element
        color = material.find("color")
        if color is None:
            color = ET.SubElement(material, "color")

        # Set RGBA values
        color.set("rgba", material_info.rgba)
        return True

    def save_urdf(self, output_file: Optional[str] = None) -> str:
        """Save the modified URDF file."""
        if output_file is None:
            output_file = self.urdf_file

        # Format and save
        self._indent_xml(self.root)
        self.tree.write(output_file, encoding="utf-8", xml_declaration=True)
        return output_file

    def _indent_xml(self, elem, level=0):
        """Add pretty-printing indentation to XML."""
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for elem in elem:
                self._indent_xml(elem, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i


@function_tool
async def set_material(robot_name: str, link_name: str, rgba: str, material_name: Optional[str] = None) -> str:
    """
    Set material/color for a specific link in URDF file.

    This tool modifies the visual appearance of a link by setting its material
    color using RGBA values.

    Args:
        robot_name: Name of the robot (e.g., "folding-mechanism")
        link_name: Name of the link to modify (e.g., "back_left_axle")
        rgba: RGBA color values as space-separated string (e.g., "0.8 0.2 0.2 1.0")
        material_name: Optional name for the material (e.g., "red_material")

    Returns:
        Human-readable string describing what material was set

    Raises:
        FileNotFoundError: If URDF file doesn't exist
        RuntimeError: If material setting fails or other errors occur
    """
    try:
        urdf_file = Path(f"data/{robot_name}/robot.urdf")
        
        if not urdf_file.exists():
            raise FileNotFoundError(f"URDF file not found: {urdf_file}")

        modifier = URDFMaterialModifier(str(urdf_file))
        material_info = MaterialInfo(rgba=rgba, name=material_name)

        success = modifier.set_link_material(link_name, material_info)
        
        if not success:
            return f"❌ Link '{link_name}' not found in {robot_name}/robot.urdf"

        # Create backup
        backup_file = f"{urdf_file}.backup"
        with open(urdf_file, 'r') as src, open(backup_file, 'w') as dst:
            dst.write(src.read())

        # Save modified file
        output_file = modifier.save_urdf()

        # Build result summary
        output = [f"✅ Material set successfully for link '{link_name}'"]
        output.append(f"Robot: {robot_name}")
        output.append(f"RGBA color: {rgba}")
        
        if material_name:
            output.append(f"Material name: {material_name}")
        
        output.append(f"Backup created: {backup_file}")
        output.append(f"Modified URDF: {output_file}")

        return "\n".join(output)

    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to set material: {str(e)}")


@function_tool
async def set_multiple_materials(robot_name: str, material_changes_json: str) -> str:
    """
    Set materials for multiple links in URDF file.

    This tool modifies the visual appearance of multiple links by setting their
    material colors using RGBA values.

    Args:
        robot_name: Name of the robot (e.g., "folding-mechanism")
        material_changes_json: JSON string mapping link names to material info
                              Example: '{"back_left_axle": {"rgba": "0.8 0.2 0.2 1.0", "name": "red_material"}, "front_right_wheel": {"rgba": "0.2 0.8 0.2 1.0"}}'

    Returns:
        Human-readable string describing what materials were set

    Raises:
        FileNotFoundError: If URDF file doesn't exist
        RuntimeError: If material setting fails or other errors occur
    """
    try:
        # Parse the JSON string to dictionary
        try:
            material_changes = json.loads(material_changes_json)
        except json.JSONDecodeError as e:
            return f"❌ Error: Invalid JSON format in material_changes_json: {e}"

        urdf_file = Path(f"data/{robot_name}/robot.urdf")
        
        if not urdf_file.exists():
            raise FileNotFoundError(f"URDF file not found: {urdf_file}")

        modifier = URDFMaterialModifier(str(urdf_file))
        success_count = 0
        failed_links = []

        # Process each material change
        for link_name, material_data in material_changes.items():
            rgba = material_data.get("rgba", "")
            material_name = material_data.get("name")
            
            if not rgba:
                failed_links.append(f"{link_name} (missing rgba)")
                continue
                
            material_info = MaterialInfo(rgba=rgba, name=material_name)
            
            if modifier.set_link_material(link_name, material_info):
                success_count += 1
            else:
                failed_links.append(f"{link_name} (link not found)")

        if success_count == 0:
            return f"❌ No materials were set successfully. Failed: {', '.join(failed_links)}"

        # Create backup
        backup_file = f"{urdf_file}.backup"
        with open(urdf_file, 'r') as src, open(backup_file, 'w') as dst:
            dst.write(src.read())

        # Save modified file
        output_file = modifier.save_urdf()

        # Build result summary
        output = [f"✅ Materials set successfully for {success_count} links"]
        output.append(f"Robot: {robot_name}")
        
        output.append(f"\nMaterial changes applied:")
        for link_name, material_data in material_changes.items():
            if link_name not in [link.split(' ')[0] for link in failed_links]:
                rgba = material_data.get("rgba", "")
                material_name = material_data.get("name", "")
                name_part = f", name='{material_name}'" if material_name else ""
                output.append(f"  {link_name}: rgba='{rgba}'{name_part}")

        if failed_links:
            output.append(f"\nFailed to set materials for:")
            for failed in failed_links:
                output.append(f"  {failed}")
        
        output.append(f"\nBackup created: {backup_file}")
        output.append(f"Modified URDF: {output_file}")

        return "\n".join(output)

    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to set materials: {str(e)}") 