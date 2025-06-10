import xml.etree.ElementTree as ET
import argparse
import sys
import os
from typing import Dict, List, Tuple, Set, Optional, Any
from dataclasses import dataclass
from collections import defaultdict


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

    def list_all_links(self) -> List[str]:
        """List all link names in the URDF."""
        links = self.root.findall(".//link")
        return [link.get("name", "unnamed") for link in links]

    def ask_user_confirmation(
        self, duplicate_groups: Dict[str, List[LinkInfo]]
    ) -> Dict[str, List[str]]:
        """Ask user which duplicates to remove."""
        to_remove = {}

        print("🤔 REMOVAL SELECTION")
        print("=" * 40)
        print("For each group, choose which links to KEEP (others will be removed)")
        print("Press Enter to skip a group, or 'q' to quit\n")

        for group_id, links in duplicate_groups.items():
            print(f"GROUP {group_id}: {len(links)} duplicates")
            for i, link in enumerate(links, 1):
                print(f"  {i}. {link.name}")

            while True:
                choice = input(
                    f"Keep which link(s) from group {group_id}? (1-{len(links)}, Enter to skip): "
                ).strip()

                if choice.lower() == "q":
                    print("Cancelled by user.")
                    return {}

                if choice == "":
                    break

                try:
                    keep_indices = [int(x.strip()) - 1 for x in choice.split(",")]
                    if all(0 <= idx < len(links) for idx in keep_indices):
                        # Mark others for removal
                        links_to_remove = []
                        for i, link in enumerate(links):
                            if i not in keep_indices:
                                links_to_remove.append(link.name)

                        if links_to_remove:
                            to_remove[group_id] = links_to_remove
                            print(f"   ✅ Will remove: {', '.join(links_to_remove)}")
                        break
                    else:
                        print(f"   ❌ Invalid choice. Use numbers 1-{len(links)}")
                except ValueError:
                    print(
                        f"   ❌ Invalid format. Use numbers 1-{len(links)} separated by commas"
                    )

            print()

        return to_remove

    def remove_links_and_update_joints(self, links_to_remove: Set[str]) -> int:
        """Remove specified links and their associated joints."""
        removed_count = 0

        # Remove link elements
        for link in self.root.findall(".//link"):
            if link.get("name") in links_to_remove:
                self.root.remove(link)
                removed_count += 1
                print(f"   🗑️  Removed link: {link.get('name')}")

        # Remove joints that reference removed links
        joints_to_remove = []
        for joint in self.root.findall(".//joint"):
            should_remove = False

            parent = joint.find("parent")
            if parent is not None and parent.get("link") in links_to_remove:
                should_remove = True

            child = joint.find("child")
            if child is not None and child.get("link") in links_to_remove:
                should_remove = True

            if should_remove:
                joints_to_remove.append(joint)

        for joint in joints_to_remove:
            joint_name = joint.get("name", "unnamed")
            self.root.remove(joint)
            print(f"   🔗 Removed joint: {joint_name}")

        return removed_count

    def save_urdf(
        self, output_file: Optional[str] = None, create_backup: bool = True
    ) -> str:
        """Save the cleaned URDF file."""
        if output_file is None:
            if create_backup:
                # Create backup and overwrite original
                backup_file = self.urdf_file + ".backup"
                os.rename(self.urdf_file, backup_file)
                print(f"   💾 Created backup: {backup_file}")
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


def remove_duplicate_links() -> str:
    """
    Find and remove duplicate links from URDF after user confirmation.

    Returns:
        Human-readable string describing what was done

    Raises:
        FileNotFoundError: If URDF file doesn't exist
        RuntimeError: If processing fails
    """
    try:
        file_path = "robots/stable-wheel-legged/robot.urdf"

        # First find duplicates
        remover = URDFDuplicateRemover(file_path)
        duplicate_groups = remover.find_duplicate_groups()

        if not duplicate_groups:
            return "✅ No duplicate links found in the URDF file."

        # Show what will be removed
        print(f"\n🔍 Found {len(duplicate_groups)} groups of duplicate links:")
        total_to_remove = 0
        for group_id, links in duplicate_groups.items():
            keep_link = links[0].name
            remove_links = [link.name for link in links[1:]]
            print(
                f"   Group {group_id}: Keep '{keep_link}', remove {len(remove_links)} duplicates"
            )
            total_to_remove += len(remove_links)

        # Ask for confirmation
        while True:
            choice = (
                input(f"\n🤔 Remove {total_to_remove} duplicate links? (y/n): ")
                .strip()
                .lower()
            )
            if choice in ["y", "yes"]:
                break
            elif choice in ["n", "no"]:
                return "❌ Cancelled by user."
            else:
                print("   Please answer 'y' or 'n'")

        # Remove duplicates (keep first in each group)
        all_links_to_remove = set()
        for links in duplicate_groups.values():
            all_links_to_remove.update(link.name for link in links[1:])

        removed_count = remover.remove_links_and_update_joints(all_links_to_remove)
        remover.save_urdf(create_backup=False)  # Overwrites original without backup

        return f"✅ Successfully removed {removed_count} duplicate links from {os.path.basename(file_path)}"

    except Exception as e:
        raise RuntimeError(f"Failed to process URDF duplicates: {str(e)}")


def main():
    parser = argparse.ArgumentParser(
        description="Remove duplicate links from URDF files"
    )
    parser.add_argument("urdf_file", help="Path to input URDF file")
    parser.add_argument(
        "--output",
        "-o",
        help="Output file (default: overwrite input with .backup created)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show duplicates but don't make changes"
    )

    args = parser.parse_args()

    if not os.path.exists(args.urdf_file):
        print(f"❌ Error: URDF file not found: {args.urdf_file}")
        sys.exit(1)

    try:
        remover = URDFDuplicateRemover(args.urdf_file)

        # Find duplicates
        duplicate_groups = remover.find_duplicate_groups()

        if not duplicate_groups:
            print("✅ No duplicate links found in the URDF file.")
            return

        # Show what will be found and removed
        print(f"\n🔍 Found {len(duplicate_groups)} groups of duplicate links:")
        total_to_remove = 0
        all_links_to_remove = set()

        for group_id, links in duplicate_groups.items():
            keep_link = links[0].name
            remove_links = [link.name for link in links[1:]]
            print(
                f"   Group {group_id}: Keep '{keep_link}', remove {len(remove_links)} duplicates: {', '.join(remove_links)}"
            )
            total_to_remove += len(remove_links)
            all_links_to_remove.update(remove_links)

        if args.dry_run:
            print(
                f"\n🔍 DRY RUN: Would remove {total_to_remove} duplicate links (keeping first from each group)"
            )
            return

        print(
            f"\n🔧 Removing {total_to_remove} duplicate links (keeping first from each group)..."
        )

        # Remove duplicates automatically
        removed_count = remover.remove_links_and_update_joints(all_links_to_remove)

        # Save file
        output_file = remover.save_urdf(args.output, create_backup=True)

        print(f"\n✅ SUCCESS!")
        print(f"   Removed {removed_count} duplicate links")
        print(f"   Saved cleaned URDF to: {output_file}")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
