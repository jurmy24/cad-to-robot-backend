#!/usr/bin/env python3
"""
Rename mates consistently across robot JSON files as a function_tool.
"""

import json
import copy
from pathlib import Path
from typing import Dict, List, Any
from collections import Counter
from agents import function_tool


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
        with open(self.matevalues_file, "r") as f:
            self.matevalues_data = json.load(f)

        with open(self.features_file, "r") as f:
            self.features_data = json.load(f)

        with open(self.assembly_file, "r") as f:
            self.assembly_data = json.load(f)

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

    def apply_renames(self, rename_map: Dict[str, str]):
        """Apply rename mapping to all three files"""
        changes_made = {
            "matevalues_data.json": 0,
            "features_data.json": 0,
            "assembly_data.json": 0,
        }

        # Apply to matevalues_data.json
        if self.matevalues_data:
            for mate in self.matevalues_data.get("mateValues", []):
                if "mateName" in mate and mate["mateName"] in rename_map:
                    old_name = mate["mateName"]
                    new_name = rename_map[old_name]
                    mate["mateName"] = new_name
                    changes_made["matevalues_data.json"] += 1

        # Apply to features_data.json
        if self.features_data:
            for feature in self.features_data.get("features", []):
                message = feature.get("message", {})
                if (
                    message.get("featureType") == "mate"
                    and "name" in message
                    and message["name"] in rename_map
                ):
                    old_name = message["name"]
                    new_name = rename_map[old_name]
                    message["name"] = new_name
                    changes_made["features_data.json"] += 1

        # Apply to assembly_data.json
        if self.assembly_data:
            root_assembly = self.assembly_data.get("rootAssembly", {})
            for feature in root_assembly.get("features", []):
                feature_data = feature.get("featureData", {})
                if "name" in feature_data and feature_data["name"] in rename_map:
                    old_name = feature_data["name"]
                    new_name = rename_map[old_name]
                    feature_data["name"] = new_name
                    changes_made["assembly_data.json"] += 1

        return changes_made

    def create_backups(self):
        """Create backup copies of all files"""
        backup_files = []
        for file_path in [self.matevalues_file, self.features_file, self.assembly_file]:
            if file_path.exists():
                backup_path = file_path.with_suffix(file_path.suffix + ".backup")
                backup_path.write_text(file_path.read_text())
                backup_files.append(str(backup_path))
        return backup_files

    def save_files(self):
        """Save all modified files"""
        saved_files = []
        
        if self.matevalues_data:
            with open(self.matevalues_file, "w") as f:
                json.dump(self.matevalues_data, f, indent=2)
            saved_files.append(str(self.matevalues_file))

        if self.features_data:
            with open(self.features_file, "w") as f:
                json.dump(self.features_data, f, indent=2)
            saved_files.append(str(self.features_file))

        if self.assembly_data:
            with open(self.assembly_file, "w") as f:
                json.dump(self.assembly_data, f, indent=2)
            saved_files.append(str(self.assembly_file))

        return saved_files


@function_tool
async def rename_mates(robot_name: str, rename_mapping_json: str) -> str:
    """
    Rename mates consistently across robot JSON files.

    This tool renames mate names in all three robot JSON files:
    - matevalues_data.json (contains "mateName" field)
    - features_data.json (contains "name" field in mate features)
    - assembly_data.json (contains "name" field in features)

    Args:
        robot_name: Name of the robot (e.g., "folding-mechanism")
        rename_mapping_json: JSON string mapping old mate names to new mate names
                            Example: '{"Revolute 1": "dof_revolute_1", "Revolute 2": "dof_arm_joint"}'

    Returns:
        Human-readable string describing what renames were performed

    Raises:
        FileNotFoundError: If robot JSON files don't exist
        RuntimeError: If renaming fails or other errors occur
    """
    try:
        # Parse the JSON string to dictionary
        try:
            rename_mapping = json.loads(rename_mapping_json)
        except json.JSONDecodeError as e:
            return f"❌ Error: Invalid JSON format in rename_mapping_json: {e}"

        robot_dir = f"data/{robot_name}"
        renamer = MateRenamer(robot_dir)

        # Load files
        renamer.load_files()
        
        # Extract current mate names
        renamer.extract_mate_names()

        # Validate that all keys in rename_mapping exist
        all_current_names = (
            set(renamer.matevalues_counts.keys())
            | set(renamer.features_counts.keys())
            | set(renamer.assembly_counts.keys())
        )
        
        missing_names = set(rename_mapping.keys()) - all_current_names
        if missing_names:
            return f"❌ Error: The following mate names to rename were not found: {missing_names}"

        # Create backups
        backup_files = renamer.create_backups()

        # Apply renames
        changes_made = renamer.apply_renames(rename_mapping)

        # Save files
        saved_files = renamer.save_files()

        # Build result summary
        output = ["✅ Mate renaming completed successfully!"]
        output.append(f"Robot: {robot_name}")
        output.append(f"Backups created: {len(backup_files)} files")
        
        total_changes = sum(changes_made.values())
        output.append(f"Total changes made: {total_changes}")
        
        output.append("\nChanges by file:")
        for file_name, count in changes_made.items():
            output.append(f"  {file_name}: {count} renames")

        output.append(f"\nRename mapping applied:")
        for old_name, new_name in rename_mapping.items():
            output.append(f"  '{old_name}' → '{new_name}'")

        output.append(f"\nFiles updated:")
        for file_path in saved_files:
            output.append(f"  {file_path}")

        output.append(f"\nBackup files created:")
        for backup_path in backup_files:
            output.append(f"  {backup_path}")

        return "\n".join(output)

    except FileNotFoundError as e:
        raise FileNotFoundError(f"Robot files not found in data/{robot_name}: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to rename mates: {str(e)}") 