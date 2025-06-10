import xml.etree.ElementTree as ET
import os
from typing import Dict, Optional
from dataclasses import dataclass


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
            print(f"   ❌ Link not found: {link_name}")
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


def set_link_materials(
    robot_name: str, material_changes: Dict[str, MaterialInfo]
) -> str:
    """Set materials for specific links in the URDF file.

    Args:
        robot_name: Name of the robot (e.g. "stable-wheel-legged")
        material_changes: Dictionary mapping link names to MaterialInfo objects

    Example:
        material_changes = {
            "back_left_axle": MaterialInfo(rgba="0.8 0.2 0.2 1.0", name="red_material"),
            "front_right_wheel": MaterialInfo(rgba="0.2 0.8 0.2 1.0", name="green_material")
        }
        result = set_link_materials("stable-wheel-legged", material_changes)

    Returns:
        Human-readable string describing what was done

    Raises:
        FileNotFoundError: If URDF file doesn't exist
        RuntimeError: If processing fails
    """
    try:
        file_path = f"robots/{robot_name}/robot.urdf"
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"URDF file not found: {file_path}")

        modifier = URDFMaterialModifier(file_path)
        success_count = 0

        for link_name, material_info in material_changes.items():
            if modifier.set_link_material(link_name, material_info):
                success_count += 1
                print(f"   ✅ Set material for link: {link_name}")

        if success_count == 0:
            return "❌ No materials were set successfully."

        modifier.save_urdf()
        return f"✅ Successfully set materials for {success_count} links in {os.path.basename(file_path)}"

    except Exception as e:
        raise RuntimeError(f"Failed to set materials: {str(e)}")


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Set materials for links in URDF files"
    )
    parser.add_argument(
        "robot_name", help="Name of the robot (e.g. stable-wheel-legged)"
    )
    parser.add_argument("--link", "-l", required=True, help="Link name to modify")
    parser.add_argument(
        "--rgba", required=True, help="RGBA color values (space-separated)"
    )
    parser.add_argument("--name", help="Optional material name")

    args = parser.parse_args()

    try:
        material_info = MaterialInfo(rgba=args.rgba, name=args.name)
        material_changes = {args.link: material_info}

        result = set_link_materials(args.robot_name, material_changes)
        print(result)

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
