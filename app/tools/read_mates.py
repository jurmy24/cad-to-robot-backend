#!/usr/bin/env python3
"""
Simple function to read mate names from robot JSON files.
This can be used as a tool by an LLM to understand what mates exist in a robot.
"""

import json
from pathlib import Path
from collections import Counter
from agents import function_tool


def read_mates(robot_name: str) -> str:
    """
    Read mate names from the robot files as defined by the OnShape API.

    This tool analyzes the robot assembly files to extract mate information including:
    - List of all unique mate names found
    - File-by-file breakdown showing which mates are in each file
    - Any inconsistencies or issues found
    - Analysis of naming conventions (e.g., which mates have "dof_" prefix)

    Args:
        robot_name: The name of the robot to read mates from (e.g., "stable-wheel-legged")

    Returns:
        Formatted string containing comprehensive mate analysis including counts,
        inconsistencies, and recommendations for proper naming conventions.

    Raises:
        FileNotFoundError: If no JSON files can be found in the robot directory
        RuntimeError: If parsing fails or other errors occur
    """

    try:
        robot_dir = f"robots/{robot_name}"
        robot_path = Path(robot_dir)
        matevalues_file = robot_path / "matevalues_data.json"
        features_file = robot_path / "features_data.json"
        assembly_file = robot_path / "assembly_data.json"

        # Load files
        matevalues_data = None
        features_data = None
        assembly_data = None
        errors = []

        try:
            with open(matevalues_file, "r") as f:
                matevalues_data = json.load(f)
        except FileNotFoundError:
            errors.append(f"matevalues_data.json not found")
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in matevalues_data.json: {str(e)}")

        try:
            with open(features_file, "r") as f:
                features_data = json.load(f)
        except FileNotFoundError:
            errors.append(f"features_data.json not found")
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in features_data.json: {str(e)}")

        try:
            with open(assembly_file, "r") as f:
                assembly_data = json.load(f)
        except FileNotFoundError:
            errors.append(f"assembly_data.json not found")
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in assembly_data.json: {str(e)}")

        # If we couldn't load any files, raise error
        if not any([matevalues_data, features_data, assembly_data]):
            raise FileNotFoundError(
                f"Could not load any JSON files from {robot_dir}. Errors: {'; '.join(errors)}"
            )

        # Extract mate names from each file
        matevalues_names = []
        features_names = []
        assembly_names = []

        # Extract from matevalues_data.json
        if matevalues_data:
            for mate in matevalues_data.get("mateValues", []):
                if "mateName" in mate:
                    matevalues_names.append(mate["mateName"])

        # Extract from features_data.json
        if features_data:
            for feature in features_data.get("features", []):
                message = feature.get("message", {})
                if (
                    message.get("featureType") == "mate"
                    and "name" in message
                    and message["name"] not in ["Fastened 1"]
                ):  # Skip non-dof mates
                    features_names.append(message["name"])

        # Extract from assembly_data.json
        if assembly_data:
            root_assembly = assembly_data.get("rootAssembly", {})
            for feature in root_assembly.get("features", []):
                feature_data = feature.get("featureData", {})
                if "name" in feature_data and (
                    feature_data["name"].startswith("dof_")
                    or feature_data["name"] == "Planar 1"
                ):
                    assembly_names.append(feature_data["name"])

        # Count occurrences
        matevalues_counts = Counter(matevalues_names)
        features_counts = Counter(features_names)
        assembly_counts = Counter(assembly_names)

        # Get all unique names
        all_unique_names = (
            set(matevalues_counts.keys())
            | set(features_counts.keys())
            | set(assembly_counts.keys())
        )
        sorted_mate_names = sorted(list(all_unique_names))

        # Build formatted output
        output = [f"ROBOT MATE NAMES ({len(sorted_mate_names)} total):"]
        output.append("=" * 50)

        if sorted_mate_names:
            output.append("\nAll Unique Mate Names:")
            for i, name in enumerate(sorted_mate_names, 1):
                output.append(f"{i:2d}. {name}")
        else:
            output.append("\nNo mate names found.")

        # File breakdown
        output.append(f"\nFile Breakdown:")
        output.append(f"  matevalues_data.json: {len(matevalues_names)} mates")
        if matevalues_names:
            output.append(f"    {', '.join(matevalues_names)}")

        output.append(f"  features_data.json: {len(features_names)} mates")
        if features_names:
            output.append(f"    {', '.join(features_names)}")

        output.append(f"  assembly_data.json: {len(assembly_names)} mates")
        if assembly_names:
            output.append(f"    {', '.join(assembly_names)}")

        # Check for inconsistencies
        issues = []

        # Check for duplicates within files
        for counts in [matevalues_counts, features_counts, assembly_counts]:
            if any(count > 1 for count in counts.values()):
                issues.append("Some mate names appear multiple times within files")
                break

        # Check for missing mates across files
        missing_in_matevalues = all_unique_names - set(matevalues_counts.keys())
        missing_in_features = all_unique_names - set(features_counts.keys())
        missing_in_assembly = all_unique_names - set(assembly_counts.keys())

        if missing_in_matevalues or missing_in_features or missing_in_assembly:
            issues.append("Mate names are not consistent across all files")

        # Check for count mismatches
        count_mismatches = {}
        for name in all_unique_names:
            counts = [
                matevalues_counts.get(name, 0),
                features_counts.get(name, 0),
                assembly_counts.get(name, 0),
            ]
            if len(set(counts)) > 1:  # Not all counts are the same
                count_mismatches[name] = counts

        if count_mismatches:
            issues.append("Some mates have different counts across files")

        # Add issues section if any found
        if issues:
            output.append(f"\nIssues Found:")
            for issue in issues:
                output.append(f"  ⚠️  {issue}")

        # Add errors section if any files couldn't be loaded
        if errors:
            output.append(f"\nFile Loading Issues:")
            for error in errors:
                output.append(f"  ⚠️  {error}")

        return "\n".join(output)

    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to read mate names: {str(e)}")


@function_tool(
    name_override="read_mates_tool",
    description_override="Read and analyze mate names from robot assembly JSON files to understand what mates exist in a robot assembly.",
)
def read_mates_tool(robot_name: str) -> str:
    """
    Function tool wrapper for read_mates that can be used by OpenAI agents.

    Args:
        robot_name: The name of the robot to read mates from (e.g., "stable-wheel-legged")

    Returns:
        Formatted string containing comprehensive mate analysis
    """
    return read_mates(robot_name)


if __name__ == "__main__":
    # Simple command line interface for testing
    import sys

    if len(sys.argv) > 1:
        robot_name = sys.argv[1]
    else:
        robot_name = "stable-wheel-legged"  # default robot name

    try:
        result = read_mates(robot_name)
        print(result)
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
