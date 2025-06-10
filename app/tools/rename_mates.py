#!/usr/bin/env python3
"""
Script to rename mates consistently across three JSON files:
- matevalues_data.json (contains "mateName" field)
- features_data.json (contains "name" field in mate features)
- assembly_data.json (contains "name" field in features)

All three files reference the same mates but potentially in different orders.
This script ensures consistent renaming across all files.

Enhanced to handle duplicate mate names properly.
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from collections import Counter


class MateRenamer:
    def __init__(self, robot_dir: str):
        self.robot_dir = Path(robot_dir)
        self.matevalues_file = self.robot_dir / "matevalues_data.json"
        self.features_file = self.robot_dir / "features_data.json"
        self.assembly_file = self.robot_dir / "assembly_data.json"

        # Data holders
        self.matevalues_data = None
        self.features_data = None
        self.assembly_data = None

        # Mate name collections (now as lists to preserve duplicates)
        self.matevalues_names = []
        self.features_names = []
        self.assembly_names = []

        # Mate name counters
        self.matevalues_counts = Counter()
        self.features_counts = Counter()
        self.assembly_counts = Counter()

    def load_files(self):
        """Load all three JSON files"""
        try:
            with open(self.matevalues_file, "r") as f:
                self.matevalues_data = json.load(f)
            print(f"✓ Loaded {self.matevalues_file}")

            with open(self.features_file, "r") as f:
                self.features_data = json.load(f)
            print(f"✓ Loaded {self.features_file}")

            with open(self.assembly_file, "r") as f:
                self.assembly_data = json.load(f)
            print(f"✓ Loaded {self.assembly_file}")

        except FileNotFoundError as e:
            print(f"❌ Error: File not found - {e}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ Error: Invalid JSON - {e}")
            sys.exit(1)

    def extract_mate_names(self):
        """Extract all mate names from the three files, preserving duplicates"""
        # Extract from matevalues_data.json
        if self.matevalues_data:
            for mate in self.matevalues_data.get("mateValues", []):
                if "mateName" in mate:
                    name = mate["mateName"]
                    self.matevalues_names.append(name)
                    self.matevalues_counts[name] += 1

        # Extract from features_data.json
        if self.features_data:
            for feature in self.features_data.get("features", []):
                message = feature.get("message", {})
                if (
                    message.get("featureType") == "mate"
                    and "name" in message
                    and message["name"] not in ["Fastened 1"]
                ):  # Skip non-dof mates
                    name = message["name"]
                    self.features_names.append(name)
                    self.features_counts[name] += 1

        # Extract from assembly_data.json
        if self.assembly_data:
            root_assembly = self.assembly_data.get("rootAssembly", {})
            for feature in root_assembly.get("features", []):
                feature_data = feature.get("featureData", {})
                if "name" in feature_data and (
                    feature_data["name"].startswith("dof_")
                    or feature_data["name"] == "Planar 1"
                ):
                    name = feature_data["name"]
                    self.assembly_names.append(name)
                    self.assembly_counts[name] += 1

        print(
            f"Found {len(self.matevalues_names)} mate instances ({len(self.matevalues_counts)} unique) in matevalues_data.json"
        )
        print(
            f"Found {len(self.features_names)} mate instances ({len(self.features_counts)} unique) in features_data.json"
        )
        print(
            f"Found {len(self.assembly_names)} mate instances ({len(self.assembly_counts)} unique) in assembly_data.json"
        )

    def check_for_duplicates(self):
        """Check for and report duplicate mate names"""
        all_counts = [
            self.matevalues_counts,
            self.features_counts,
            self.assembly_counts,
        ]
        file_names = [
            "matevalues_data.json",
            "features_data.json",
            "assembly_data.json",
        ]

        has_duplicates = False
        for counts, file_name in zip(all_counts, file_names):
            duplicates = {name: count for name, count in counts.items() if count > 1}
            if duplicates:
                has_duplicates = True
                print(f"⚠️  Duplicate mate names in {file_name}:")
                for name, count in duplicates.items():
                    print(f"   '{name}' appears {count} times")

        if has_duplicates:
            print(
                f"\n🔍 Note: When duplicate mate names exist, renaming will affect ALL instances with the same name."
            )
            print(
                f"   If you need to rename duplicates individually, you'll need to first make them unique in Onshape."
            )

        return has_duplicates

    def analyze_mate_names(self):
        """Analyze and compare mate names across files"""
        all_unique_names = (
            set(self.matevalues_counts.keys())
            | set(self.features_counts.keys())
            | set(self.assembly_counts.keys())
        )

        print(f"\n📊 Analysis:")
        print(f"Total unique mate names across all files: {len(all_unique_names)}")

        # Check for consistency
        missing_in_matevalues = all_unique_names - set(self.matevalues_counts.keys())
        missing_in_features = all_unique_names - set(self.features_counts.keys())
        missing_in_assembly = all_unique_names - set(self.assembly_counts.keys())

        if missing_in_matevalues:
            print(f"⚠️  Missing in matevalues_data.json: {missing_in_matevalues}")
        if missing_in_features:
            print(f"⚠️  Missing in features_data.json: {missing_in_features}")
        if missing_in_assembly:
            print(f"⚠️  Missing in assembly_data.json: {missing_in_assembly}")

        # Check for count mismatches
        count_mismatches = []
        for name in all_unique_names:
            counts = [
                self.matevalues_counts.get(name, 0),
                self.features_counts.get(name, 0),
                self.assembly_counts.get(name, 0),
            ]
            if len(set(counts)) > 1:  # Not all counts are the same
                count_mismatches.append((name, counts))

        if count_mismatches:
            print(f"⚠️  Count mismatches between files:")
            for name, (mv_count, feat_count, asm_count) in count_mismatches:
                print(
                    f"   '{name}': matevalues={mv_count}, features={feat_count}, assembly={asm_count}"
                )

        if not (
            missing_in_matevalues
            or missing_in_features
            or missing_in_assembly
            or count_mismatches
        ):
            print("✅ All mate names and counts are consistent across files!")

        return sorted(all_unique_names)

    def display_current_names(self):
        """Display current mate names with counts"""
        self.check_for_duplicates()
        all_names = self.analyze_mate_names()

        print(f"\n📋 Current mate names:")
        for i, name in enumerate(all_names, 1):
            mv_count = self.matevalues_counts.get(name, 0)
            feat_count = self.features_counts.get(name, 0)
            asm_count = self.assembly_counts.get(name, 0)

            count_info = ""
            if max(mv_count, feat_count, asm_count) > 1:
                count_info = f" (appears {max(mv_count, feat_count, asm_count)}x)"

            print(f"{i:2d}. {name}{count_info}")

        return all_names

    def create_rename_mapping(self, current_names: List[str]) -> Dict[str, str]:
        """Interactive creation of rename mapping"""
        rename_map = {}

        print(f"\n🔄 Create rename mapping:")
        print("Enter new names for each mate (press Enter to keep current name):")
        print(
            "Note: If a mate name appears multiple times, ALL instances will be renamed."
        )

        for name in current_names:
            max_count = max(
                self.matevalues_counts.get(name, 0),
                self.features_counts.get(name, 0),
                self.assembly_counts.get(name, 0),
            )

            prompt = f"Rename '{name}'"
            if max_count > 1:
                prompt += f" ({max_count} instances)"
            prompt += " to: "

            new_name = input(prompt).strip()
            if new_name and new_name != name:
                rename_map[name] = new_name
                if max_count > 1:
                    print(f"  '{name}' → '{new_name}' ({max_count} instances)")
                else:
                    print(f"  '{name}' → '{new_name}'")
            else:
                print(f"  '{name}' (no change)")

        return rename_map

    def load_rename_mapping_from_file(self, mapping_file: str) -> Dict[str, str]:
        """Load rename mapping from a JSON file"""
        try:
            with open(mapping_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Error: Mapping file '{mapping_file}' not found")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ Error: Invalid JSON in mapping file - {e}")
            sys.exit(1)

    def save_rename_mapping(self, rename_map: Dict[str, str], output_file: str):
        """Save rename mapping to a file for future use"""
        with open(output_file, "w") as f:
            json.dump(rename_map, f, indent=2)
        print(f"💾 Rename mapping saved to {output_file}")

    def apply_renames(self, rename_map: Dict[str, str]):
        """Apply renames to all three files"""
        if not rename_map:
            print("No renames to apply.")
            return

        print(f"\n🔄 Applying {len(rename_map)} renames...")

        rename_counts = {
            file: Counter() for file in ["matevalues", "features", "assembly"]
        }

        # Apply to matevalues_data.json
        if self.matevalues_data:
            for mate in self.matevalues_data.get("mateValues", []):
                if mate.get("mateName") in rename_map:
                    old_name = mate["mateName"]
                    new_name = rename_map[old_name]
                    mate["mateName"] = new_name
                    rename_counts["matevalues"][old_name] += 1

        # Apply to features_data.json
        if self.features_data:
            for feature in self.features_data.get("features", []):
                message = feature.get("message", {})
                if (
                    message.get("featureType") == "mate"
                    and message.get("name") in rename_map
                ):
                    old_name = message["name"]
                    new_name = rename_map[old_name]
                    message["name"] = new_name
                    rename_counts["features"][old_name] += 1

        # Apply to assembly_data.json
        if self.assembly_data:
            root_assembly = self.assembly_data.get("rootAssembly", {})
            for feature in root_assembly.get("features", []):
                feature_data = feature.get("featureData", {})
                if feature_data.get("name") in rename_map:
                    old_name = feature_data["name"]
                    new_name = rename_map[old_name]
                    feature_data["name"] = new_name
                    rename_counts["assembly"][old_name] += 1

        # Report what was renamed
        for old_name, new_name in rename_map.items():
            mv_count = rename_counts["matevalues"][old_name]
            feat_count = rename_counts["features"][old_name]
            asm_count = rename_counts["assembly"][old_name]

            print(f"  '{old_name}' → '{new_name}':")
            print(f"    matevalues: {mv_count} instances")
            print(f"    features: {feat_count} instances")
            print(f"    assembly: {asm_count} instances")

    def create_backups(self):
        """Create backup copies of all files"""
        backup_suffix = ".backup"

        files_to_backup = [self.matevalues_file, self.features_file, self.assembly_file]

        for file_path in files_to_backup:
            backup_path = file_path.with_suffix(file_path.suffix + backup_suffix)
            backup_path.write_text(file_path.read_text())
            print(f"📁 Created backup: {backup_path}")

    def save_files(self):
        """Save all modified files"""
        try:
            with open(self.matevalues_file, "w") as f:
                json.dump(self.matevalues_data, f, indent=2)
            print(f"💾 Saved {self.matevalues_file}")

            with open(self.features_file, "w") as f:
                json.dump(self.features_data, f, indent=2)
            print(f"💾 Saved {self.features_file}")

            with open(self.assembly_file, "w") as f:
                json.dump(self.assembly_data, f, indent=2)
            print(f"💾 Saved {self.assembly_file}")

            print("✅ All files saved successfully!")

        except Exception as e:
            print(f"❌ Error saving files: {e}")
            sys.exit(1)


# FOR THE AI AGENT
def rename_mates(robot_name: str, rename_mapping: Dict[str, str]) -> str:
    """
    External function that can be called by an AI agent to rename mates.

    Args:
        rename_mapping (Dict[str, str]): Mapping of old_name -> new_name

    Returns:
        Formatted string with rename operation results and onshape-to-robot conversion output

    Raises:
        FileNotFoundError: If robot JSON files are not found
        ValueError: If invalid mate names are provided
        RuntimeError: If renaming operation fails
    """
    import io
    import sys
    import os

    if not rename_mapping:
        raise ValueError("No rename mapping provided")

    try:
        # Initialize renamer
        robot_dir = f"robots/{robot_name}"
        renamer = MateRenamer(robot_dir)

        # Load files
        renamer.load_files()

        # Extract mate names
        renamer.extract_mate_names()

        # Validate that the names to be renamed actually exist
        all_existing_names = (
            set(renamer.matevalues_counts.keys())
            | set(renamer.features_counts.keys())
            | set(renamer.assembly_counts.keys())
        )

        invalid_names = set(rename_mapping.keys()) - all_existing_names
        if invalid_names:
            raise ValueError(f"Mate names not found: {list(invalid_names)}")

        # Calculate total instances that will be affected
        total_instances = 0
        changes_summary = []

        for old_name, new_name in rename_mapping.items():
            mv_count = renamer.matevalues_counts.get(old_name, 0)
            feat_count = renamer.features_counts.get(old_name, 0)
            asm_count = renamer.assembly_counts.get(old_name, 0)

            max_instances = max(mv_count, feat_count, asm_count)
            total_instances += max_instances

            changes_summary.append(
                f"  '{old_name}' → '{new_name}' ({max_instances} instances)"
            )

        # Show what will be renamed and ask for user approval
        print(f"\n📋 Rename Summary:")
        for change in changes_summary:
            print(change)
        print(f"\nTotal instances to be renamed: {total_instances}")

        confirm = (
            input(
                f"\nProceed with renaming {len(rename_mapping)} mate names ({total_instances} instances)? (y/N): "
            )
            .strip()
            .lower()
        )
        if confirm != "y":
            return "OPERATION CANCELLED: User did not approve the rename operation."

        # Apply renames
        renamer.apply_renames(rename_mapping)

        # Save files
        renamer.save_files()

        # Build result message
        output = [f"MATE RENAME OPERATION COMPLETED"]
        output.append("=" * 40)
        output.append(
            f"Renamed {len(rename_mapping)} mate names ({total_instances} total instances)"
        )
        output.append("")
        output.append("Changes made:")
        output.extend(changes_summary)
        output.append("")
        output.append("Files updated:")
        output.append("  - matevalues_data.json")
        output.append("  - features_data.json")
        output.append("  - assembly_data.json")

        # Now run the onshape-to-robot converter
        output.append("")
        output.append("=" * 40)
        output.append("RUNNING ONSHAPE-TO-ROBOT CONVERTER")
        output.append("=" * 40)

        # Capture stdout to get all print statements from the conversion
        old_stdout = sys.stdout
        captured_stdout = io.StringIO()
        sys.stdout = captured_stdout

        try:
            # Import and run the main function from main.py
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__ + "/..")))

            # Run the converter with the robot directory
            # STARTING POINT
            import os
            from dotenv import load_dotenv, find_dotenv
            from onshape.src.config import Config
            from onshape.src.robot_builder import RobotBuilder
            from onshape.src.exporter_urdf import ExporterURDF

            """
            This is the entry point of the export script, i.e the "onshape-to-robot" command.
            """
            load_dotenv(find_dotenv(usecwd=True))

            try:
                # Retrieving robot path
                if not robot_dir:
                    raise Exception("ERROR: you must provide the robot directory")

                # Loading configuration
                config = Config(robot_dir)

                # Building exporter beforehand, so that the configuration gets checked
                if config.output_format == "urdf":
                    exporter = ExporterURDF(config)
                else:
                    raise Exception(
                        f"Unsupported output format: {config.output_format}"
                    )

                # Building the robot
                robot_builder = RobotBuilder(config)
                robot = robot_builder.robot

                # Can be used for debugging
                # pickle.dump(robot, open("robot.pkl", "wb"))
                # robot = pickle.load(open("robot.pkl", "rb"))

                # Applying processors
                for processor in config.processors:
                    processor.process(robot)

                exporter.write_xml(
                    robot,
                    config.output_directory
                    + "/"
                    + config.output_filename
                    + "."
                    + exporter.ext,
                )

                for command in config.post_import_commands:
                    print((f"* Running command: {command}"))
                    os.system(command)
            except Exception as e:
                print((f"ERROR: {e}"))
                raise e
            # ENDING POINT

            # Get the captured output
            converter_output = captured_stdout.getvalue()

        except Exception as converter_error:
            converter_output = (
                f"ERROR during onshape-to-robot conversion: {str(converter_error)}"
            )

        finally:
            # Restore stdout
            sys.stdout = old_stdout

        # Add converter output to the result
        if converter_output.strip():
            output.append("")
            output.append("Onshape-to-robot conversion output:")
            output.append("-" * 40)
            output.extend(converter_output.strip().split("\n"))
        else:
            output.append("Onshape-to-robot conversion completed (no output captured)")

        return "\n".join(output)

    except FileNotFoundError as e:
        raise FileNotFoundError(f"Robot files not found: {str(e)}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON in robot files: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Failed to rename mates: {str(e)}")


def main():
    parser = argparse.ArgumentParser(
        description="Rename mates consistently across JSON files"
    )
    parser.add_argument("robot_dir", help="Directory containing the robot JSON files")
    parser.add_argument(
        "--mapping-file", "-m", help="JSON file containing rename mapping"
    )
    parser.add_argument("--save-mapping", "-s", help="Save rename mapping to file")
    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Show what would be renamed without making changes",
    )
    parser.add_argument(
        "--create-backup", action="store_true", help="Create backup files"
    )
    parser.add_argument(
        "--show-duplicates",
        action="store_true",
        help="Only show duplicate analysis and exit",
    )
    parser.add_argument(
        "--prepend-dof",
        action="store_true",
        help="Automatically prepend 'dof_' to all mate names that don't already start with 'dof_'",
    )

    args = parser.parse_args()

    # Check for conflicting arguments
    if args.prepend_dof and args.mapping_file:
        print(
            "❌ Error: Cannot use --prepend-dof with --mapping-file. Choose one option."
        )
        sys.exit(1)

    # Initialize renamer
    renamer = MateRenamer(args.robot_dir)

    # Load files
    renamer.load_files()

    # Extract mate names
    renamer.extract_mate_names()

    # If only showing duplicates, do that and exit
    if args.show_duplicates:
        renamer.check_for_duplicates()
        renamer.analyze_mate_names()
        return

    # Display current state
    current_names = renamer.display_current_names()

    # Get rename mapping
    if args.mapping_file:
        rename_map = renamer.load_rename_mapping_from_file(args.mapping_file)
    elif args.prepend_dof:
        # Automatically create mapping to prepend 'dof_' to names that don't already have it
        rename_map = {}
        for name in current_names:
            if not name.startswith("dof_"):
                rename_map[name] = f"dof_{name}"

        if rename_map:
            print(f"\n🤖 Auto-generating rename mapping to prepend 'dof_':")
            for old_name, new_name in rename_map.items():
                max_count = max(
                    renamer.matevalues_counts.get(old_name, 0),
                    renamer.features_counts.get(old_name, 0),
                    renamer.assembly_counts.get(old_name, 0),
                )
                count_info = f" ({max_count} instances)" if max_count > 1 else ""
                print(f"  '{old_name}' → '{new_name}'{count_info}")
        else:
            print("✅ All mate names already start with 'dof_'. No changes needed.")
    else:
        rename_map = renamer.create_rename_mapping(current_names)

    # Save mapping if requested
    if args.save_mapping:
        renamer.save_rename_mapping(rename_map, args.save_mapping)

    if not rename_map:
        print("No renames specified. Exiting.")
        return

    # Show what will be renamed
    print(f"\n📋 Rename Summary:")
    total_instances = 0
    for old_name, new_name in rename_map.items():
        instances = max(
            renamer.matevalues_counts.get(old_name, 0),
            renamer.features_counts.get(old_name, 0),
            renamer.assembly_counts.get(old_name, 0),
        )
        total_instances += instances
        print(f"  '{old_name}' → '{new_name}' ({instances} instances)")

    print(f"\nTotal instances to be renamed: {total_instances}")

    if args.dry_run:
        print("\n🔍 Dry run - no changes made.")
        return

    # Confirm changes
    if (
        not args.mapping_file and not args.prepend_dof
    ):  # Only ask for confirmation in interactive mode
        confirm = (
            input(
                f"\nProceed with renaming {len(rename_map)} mate names ({total_instances} instances)? (y/N): "
            )
            .strip()
            .lower()
        )
        if confirm != "y":
            print("Cancelled.")
            return
    elif args.prepend_dof:
        # For --prepend-dof, show a simpler confirmation
        confirm = (
            input(
                f"\nProceed with prepending 'dof_' to {len(rename_map)} mate names? (y/N): "
            )
            .strip()
            .lower()
        )
        if confirm != "y":
            print("Cancelled.")
            return

    # Create backups unless disabled
    if args.create_backup:
        renamer.create_backups()

    # Apply renames
    renamer.apply_renames(rename_map)

    # Save files
    renamer.save_files()

    print(
        f"\n🎉 Successfully renamed {len(rename_map)} mate names ({total_instances} instances) across all files!"
    )
