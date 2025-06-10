#!/usr/bin/env python3
"""
Remove duplicate links from URDF files as a function_tool.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional
from dataclasses import dataclass
from collections import defaultdict
from agents import function_tool


@dataclass
class LinkInfo:
    """Information about a link for comparison."""
    name: str
    mesh_files: List[str]
    origins: List[Tuple[str, str]]  # (xyz, rpy) pairs
    materials: List[str]  # RGBA color values
    inertial_mass: Optional[str]


class URDFDuplicateRemover:
    def __init__(self, urdf_file: str):
        self.urdf_file = urdf_file
        self.tree = ET.parse(urdf_file)
        self.root = self.tree.getroot()
        self.robot_name = self.root.get("name", "unknown")

    def extract_link_info(self, link_element: ET.Element) -> LinkInfo:
        """Extract key information from a link element for comparison."""
        name = link_element.get("name", "unnamed")
        mesh_files = []
        origins = []
        materials = []

        # Extract mesh files and origins from visual elements
        for visual in link_element.findall("visual"):
            # Get origin
            origin = visual.find("origin")
            if origin is not None:
                xyz = origin.get("xyz", "0 0 0")
                rpy = origin.get("rpy", "0 0 0")
                origins.append((xyz, rpy))
            else:
                origins.append(("0 0 0", "0 0 0"))

            # Get mesh filename
            geometry = visual.find("geometry")
            if geometry is not None:
                mesh = geometry.find("mesh")
                if mesh is not None:
                    filename = mesh.get("filename", "")
                    if filename:
                        # Extract just the mesh name from package path
                        mesh_name = (
                            filename.split("/")[-1] if "/" in filename else filename
                        )
                        mesh_files.append(mesh_name)

            # Get material color
            material = visual.find("material")
            if material is not None:
                color = material.find("color")
                if color is not None:
                    rgba = color.get("rgba", "")
                    if rgba:
                        materials.append(rgba)

        # Extract mesh files from collision elements too
        for collision in link_element.findall("collision"):
            geometry = collision.find("geometry")
            if geometry is not None:
                mesh = geometry.find("mesh")
                if mesh is not None:
                    filename = mesh.get("filename", "")
                    if filename:
                        mesh_name = (
                            filename.split("/")[-1] if "/" in filename else filename
                        )
                        if mesh_name not in mesh_files:
                            mesh_files.append(mesh_name)

        # Get inertial mass
        inertial_mass = None
        inertial = link_element.find("inertial")
        if inertial is not None:
            mass = inertial.find("mass")
            if mass is not None:
                inertial_mass = mass.get("value")

        return LinkInfo(
            name=name,
            mesh_files=sorted(mesh_files),
            origins=origins,
            materials=sorted(materials),
            inertial_mass=inertial_mass,
        )

    def find_duplicate_groups(self) -> Dict[str, List[LinkInfo]]:
        """Find groups of duplicate links."""
        links = self.root.findall(".//link")
        link_infos = [self.extract_link_info(link) for link in links]

        # Group links by their key characteristics
        groups = defaultdict(list)

        for link_info in link_infos:
            # Create a key based on mesh files, origins, and materials
            # Skip links with no mesh files (they might be purely inertial)
            if not link_info.mesh_files:
                continue

            key = (
                tuple(link_info.mesh_files),
                tuple(link_info.origins),
                tuple(link_info.materials),
            )
            groups[key].append(link_info)

        # Only return groups with duplicates
        return {
            str(i): group for i, group in enumerate(groups.values()) if len(group) > 1
        }

    def get_joint_connections(self) -> Dict[str, List[str]]:
        """Get all joints that reference each link."""
        joint_connections = defaultdict(list)

        for joint in self.root.findall(".//joint"):
            joint_name = joint.get("name", "unnamed")

            parent = joint.find("parent")
            child = joint.find("child")

            if parent is not None:
                parent_link = parent.get("link")
                if parent_link:
                    joint_connections[parent_link].append(f"parent in {joint_name}")

            if child is not None:
                child_link = child.get("link")
                if child_link:
                    joint_connections[child_link].append(f"child in {joint_name}")

        return joint_connections

    def remove_links_and_update_joints(self, links_to_remove: Set[str]) -> int:
        """Remove specified links and update any referencing joints."""
        removed_count = 0

        # Remove link elements
        for link in self.root.findall(".//link"):
            if link.get("name") in links_to_remove:
                self.root.remove(link)
                removed_count += 1

        # Update or remove joints that reference removed links
        joints_to_remove = []
        for joint in self.root.findall(".//joint"):
            parent = joint.find("parent")
            child = joint.find("child")

            parent_link = parent.get("link") if parent is not None else None
            child_link = child.get("link") if child is not None else None

            # If either parent or child is removed, mark joint for removal
            if (parent_link in links_to_remove) or (child_link in links_to_remove):
                joints_to_remove.append(joint)

        # Remove joints that reference removed links
        for joint in joints_to_remove:
            self.root.remove(joint)

        return removed_count

    def save_urdf(self, output_file: Optional[str] = None, create_backup: bool = True) -> str:
        """Save the modified URDF file."""
        if output_file is None:
            output_file = self.urdf_file

        # Create backup if requested
        if create_backup and output_file == self.urdf_file:
            backup_file = f"{self.urdf_file}.backup"
            with open(self.urdf_file, 'r') as src, open(backup_file, 'w') as dst:
                dst.write(src.read())

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
async def remove_duplicate_links(robot_name: str, links_to_remove: Optional[List[str]] = None) -> str:
    """
    Remove duplicate links from URDF files.

    This tool identifies and removes duplicate links that have identical:
    - Mesh files
    - Origins (xyz, rpy)
    - Materials (RGBA colors)

    Args:
        robot_name: Name of the robot (e.g., "folding-mechanism")
        links_to_remove: Optional list of specific link names to remove.
                        If not provided, will automatically detect and remove duplicates,
                        keeping the first occurrence of each duplicate group.

    Returns:
        Human-readable string describing what duplicate links were removed

    Raises:
        FileNotFoundError: If URDF file doesn't exist
        RuntimeError: If processing fails or other errors occur
    """
    try:
        urdf_file = Path(f"data/{robot_name}/robot.urdf")
        
        if not urdf_file.exists():
            raise FileNotFoundError(f"URDF file not found: {urdf_file}")

        remover = URDFDuplicateRemover(str(urdf_file))
        
        if links_to_remove is None:
            # Auto-detect duplicates
            duplicate_groups = remover.find_duplicate_groups()
            
            if not duplicate_groups:
                return f"✅ No duplicate links found in {robot_name}/robot.urdf"

            # Automatically remove duplicates (keep first, remove rest)
            links_to_remove_set = set()
            for group_id, links in duplicate_groups.items():
                # Keep the first link, remove the rest
                for link in links[1:]:  # Skip first link (index 0)
                    links_to_remove_set.add(link.name)

            # Build summary of what will be removed
            output = [f"🔍 Found {len(duplicate_groups)} duplicate groups in {robot_name}/robot.urdf"]
            
            for group_id, links in duplicate_groups.items():
                output.append(f"\nGroup {group_id}: {len(links)} duplicates")
                output.append(f"  Keeping: {links[0].name}")
                output.append(f"  Removing: {', '.join([link.name for link in links[1:]])}")

        else:
            # Use provided list
            links_to_remove_set = set(links_to_remove)
            output = [f"🗑️  Removing specified links from {robot_name}/robot.urdf"]
            output.append(f"Links to remove: {', '.join(links_to_remove)}")

        if not links_to_remove_set:
            return f"✅ No links to remove from {robot_name}/robot.urdf"

        # Get joint connections before removal
        joint_connections = remover.get_joint_connections()
        affected_joints = []
        for link_name in links_to_remove_set:
            if link_name in joint_connections:
                affected_joints.extend(joint_connections[link_name])

        # Remove links and update joints
        removed_count = remover.remove_links_and_update_joints(links_to_remove_set)

        # Save the modified URDF
        output_file = remover.save_urdf(create_backup=True)

        # Build final summary
        output.append(f"\n✅ Successfully removed {removed_count} duplicate links")
        output.append(f"Backup created: {output_file}.backup")
        
        if affected_joints:
            output.append(f"Affected joints: {len(set(affected_joints))}")
            output.append("  " + ", ".join(set(affected_joints)))

        output.append(f"\nModified URDF saved to: {output_file}")

        return "\n".join(output)

    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to remove duplicate links: {str(e)}") 