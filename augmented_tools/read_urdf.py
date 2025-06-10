#!/usr/bin/env python3
"""
URDF Reader as a function_tool for the CAD-to-Robot ReAct Agent.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from agents import function_tool


class URDFReader:
    def __init__(self, urdf_file: str):
        self.urdf_file = urdf_file
        self.tree = ET.parse(urdf_file)
        self.root = self.tree.getroot()
        self.robot_name = self.root.get("name", "unknown")

    def get_links_summary(self) -> str:
        """Get a concise summary of all links with key information."""
        links = self.root.findall(".//link")
        output = [f"ROBOT LINKS ({len(links)} total):"]
        output.append("=" * 50)

        for link in links:
            name = link.get("name", "unnamed")
            output.append(f"\nLINK: {name}")

            # Visual information
            visuals = link.findall("visual")
            if visuals:
                for i, visual in enumerate(visuals):
                    suffix = f" (visual {i+1})" if len(visuals) > 1 else ""
                    output.append(f"  Visual{suffix}:")

                    # Origin
                    origin = visual.find("origin")
                    if origin is not None:
                        xyz = origin.get("xyz", "0 0 0")
                        rpy = origin.get("rpy", "0 0 0")
                        output.append(f"    Origin: xyz={xyz}, rpy={rpy}")

                    # Geometry
                    geometry = visual.find("geometry")
                    if geometry is not None:
                        mesh = geometry.find("mesh")
                        if mesh is not None:
                            filename = mesh.get("filename", "unknown")
                            scale = mesh.get("scale", "1 1 1")
                            output.append(
                                f"    Mesh: {filename}"
                                + (f", scale={scale}" if scale != "1 1 1" else "")
                            )

                        box = geometry.find("box")
                        if box is not None:
                            size = box.get("size", "unknown")
                            output.append(f"    Box: size={size}")

                        cylinder = geometry.find("cylinder")
                        if cylinder is not None:
                            radius = cylinder.get("radius", "unknown")
                            length = cylinder.get("length", "unknown")
                            output.append(
                                f"    Cylinder: radius={radius}, length={length}"
                            )

                        sphere = geometry.find("sphere")
                        if sphere is not None:
                            radius = sphere.get("radius", "unknown")
                            output.append(f"    Sphere: radius={radius}")

                    # Material
                    material = visual.find("material")
                    if material is not None:
                        mat_name = material.get("name", "unnamed")
                        color = material.find("color")
                        if color is not None:
                            rgba = color.get("rgba", "unknown")
                            output.append(f"    Material: {mat_name}, color={rgba}")
                        else:
                            output.append(f"    Material: {mat_name}")

            # Collision information
            collisions = link.findall("collision")
            if collisions:
                for i, collision in enumerate(collisions):
                    suffix = f" (collision {i+1})" if len(collisions) > 1 else ""
                    output.append(f"  Collision{suffix}:")

                    # Origin
                    origin = collision.find("origin")
                    if origin is not None:
                        xyz = origin.get("xyz", "0 0 0")
                        rpy = origin.get("rpy", "0 0 0")
                        output.append(f"    Origin: xyz={xyz}, rpy={rpy}")

                    # Geometry
                    geometry = collision.find("geometry")
                    if geometry is not None:
                        mesh = geometry.find("mesh")
                        if mesh is not None:
                            filename = mesh.get("filename", "unknown")
                            output.append(f"    Mesh: {filename}")

                        box = geometry.find("box")
                        if box is not None:
                            size = box.get("size", "unknown")
                            output.append(f"    Box: size={size}")

                        cylinder = geometry.find("cylinder")
                        if cylinder is not None:
                            radius = cylinder.get("radius", "unknown")
                            length = cylinder.get("length", "unknown")
                            output.append(
                                f"    Cylinder: radius={radius}, length={length}"
                            )

                        sphere = geometry.find("sphere")
                        if sphere is not None:
                            radius = sphere.get("radius", "unknown")
                            output.append(f"    Sphere: radius={radius}")

            # Mass properties (brief)
            inertial = link.find("inertial")
            if inertial is not None:
                mass = inertial.find("mass")
                if mass is not None:
                    output.append(f"  Mass: {mass.get('value', 'unknown')}")

        return "\n".join(output)

    def get_joints_summary(self) -> str:
        """Get a concise summary of all joints with key information."""
        joints = self.root.findall(".//joint")
        output = [f"ROBOT JOINTS ({len(joints)} total):"]
        output.append("=" * 50)

        for joint in joints:
            name = joint.get("name", "unnamed")
            joint_type = joint.get("type", "unknown")
            output.append(f"\nJOINT: {name} (type: {joint_type})")

            # Parent and child
            parent = joint.find("parent")
            child = joint.find("child")
            if parent is not None and child is not None:
                parent_link = parent.get("link", "unknown")
                child_link = child.get("link", "unknown")
                output.append(f"  Connection: {parent_link} -> {child_link}")

            # Origin
            origin = joint.find("origin")
            if origin is not None:
                xyz = origin.get("xyz", "0 0 0")
                rpy = origin.get("rpy", "0 0 0")
                output.append(f"  Origin: xyz={xyz}, rpy={rpy}")

            # Axis
            axis = joint.find("axis")
            if axis is not None:
                axis_xyz = axis.get("xyz", "unknown")
                output.append(f"  Axis: {axis_xyz}")

            # Limits
            limit = joint.find("limit")
            if limit is not None:
                lower = limit.get("lower", "none")
                upper = limit.get("upper", "none")
                effort = limit.get("effort", "none")
                velocity = limit.get("velocity", "none")
                output.append(
                    f"  Limits: lower={lower}, upper={upper}, effort={effort}, velocity={velocity}"
                )

        return "\n".join(output)

    def get_summary(self) -> str:
        """Get high-level summary of the robot."""
        links = self.root.findall(".//link")
        joints = self.root.findall(".//joint")
        materials = self.root.findall(".//material")
        meshes = self.root.findall(".//mesh")

        # Count joint types
        joint_types = {}
        for joint in joints:
            jtype = joint.get("type", "unknown")
            joint_types[jtype] = joint_types.get(jtype, 0) + 1

        # Get unique mesh files
        unique_meshes = set()
        for mesh in meshes:
            filename = mesh.get("filename")
            if filename:
                unique_meshes.add(filename.split("/")[-1])

        output = [
            f"ROBOT SUMMARY: {self.robot_name}",
            "=" * 50,
            f"Links: {len(links)}",
            f"Joints: {len(joints)}",
            f"Materials: {len(materials)}",
            f"Unique meshes: {len(unique_meshes)}",
        ]

        if joint_types:
            output.append("\nJoint Types:")
            for jtype, count in sorted(joint_types.items()):
                output.append(f"  {jtype}: {count}")

        if unique_meshes:
            output.append(f"\nMesh Files ({len(unique_meshes)}):")
            for mesh in sorted(unique_meshes):
                output.append(f"  {mesh}")

        return "\n".join(output)


@function_tool
async def read_urdf(robot_name: str, requested_info: str = "summary") -> str:
    """
    Read and analyze URDF file information.

    This tool reformats URDF files into LLM-friendly summaries that preserve 
    all important information while using fewer tokens.

    Args:
        robot_name: Name of the robot (e.g., "folding-mechanism")
        requested_info: Type of information to retrieve:
            - "links": Show all links (name, visual, collision, materials, colors)
            - "joints": Show all joints (name, type, connections, limits)
            - "summary": Show high-level robot summary (default)

    Returns:
        Formatted string containing the requested URDF information

    Raises:
        FileNotFoundError: If URDF file doesn't exist
        RuntimeError: If parsing fails or other errors occur
    """
    try:
        urdf_file = Path(f"data/{robot_name}/robot.urdf")
        
        if not urdf_file.exists():
            raise FileNotFoundError(f"URDF file not found: {urdf_file}")

        reader = URDFReader(str(urdf_file))

        if requested_info.lower() == "links":
            return reader.get_links_summary()
        elif requested_info.lower() == "joints":
            return reader.get_joints_summary()
        elif requested_info.lower() == "summary":
            return reader.get_summary()
        else:
            raise ValueError(
                f"Invalid requested_info: {requested_info}. Must be 'links', 'joints', or 'summary'"
            )

    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to read URDF: {str(e)}") 