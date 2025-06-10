"""
Augmented tool for running OnShape to Robot URDF conversion.
This tool processes OnShape assembly data and generates URDF files.
"""

import os
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
from dotenv import load_dotenv, find_dotenv
from onshape.src.config import Config
from onshape.src.robot_builder import RobotBuilder
from onshape.src.exporter_urdf import ExporterURDF
from agents import function_tool

@function_tool
async def run_onshape_conversion(robot_name: str) -> str:
    """
    Run OnShape to Robot URDF conversion for the specified robot.
    
    This tool processes OnShape assembly data and generates URDF files.
    It loads the robot configuration, builds the robot model, applies processors,
    and exports the final URDF file.
    
    Args:
        robot_name: Name of the robot directory in data/ (e.g., "folding-mechanism")
        
    Returns:
        str: Detailed status message with conversion results and logs
    """
    
    if not robot_name:
        return "❌ ERROR: Robot name is required"
    
    robot_path = f"data/{robot_name}"
    
    if not os.path.exists(robot_path):
        return f"❌ ERROR: Robot directory '{robot_path}' does not exist"
    
    # Check for required files
    required_files = ["config.json", "assembly_data.json"]
    missing_files = []
    for file in required_files:
        if not os.path.exists(os.path.join(robot_path, file)):
            missing_files.append(file)
    
    if missing_files:
        return f"❌ ERROR: Missing required files in {robot_path}: {', '.join(missing_files)}"
    
    load_dotenv(find_dotenv(usecwd=True))

    # Capture stdout and stderr to return as logs
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    try:
        print(f"🚀 Starting OnShape to Robot conversion for {robot_name}...")
        
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Step 1: Loading configuration
            print("📋 Loading configuration...")
            try:
                config = Config(robot_path)
                print(f"✅ Loaded configuration for output format: {config.output_format}")
            except SystemExit as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ SystemExit during Config loading: {e}", file=sys.__stderr__)
                return f"❌ SystemExit during Config loading: {e}\n\nLogs:\n{logs}"
            except Exception as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ Config loading failed: {e}", file=sys.__stderr__)
                return f"❌ Config loading failed: {e}\n\nLogs:\n{logs}"

            # Step 2: Building exporter
            print("🏗️ Creating exporter...")
            try:
                if config.output_format == "urdf":
                    exporter = ExporterURDF(config)
                    print("✅ URDF exporter created successfully")
                else:
                    raise Exception(f"Unsupported output format: {config.output_format}")
            except SystemExit as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ SystemExit during exporter creation: {e}", file=sys.__stderr__)
                return f"❌ SystemExit during exporter creation: {e}\n\nLogs:\n{logs}"
            except Exception as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ Exporter creation failed: {e}", file=sys.__stderr__)
                return f"❌ Exporter creation failed: {e}\n\nLogs:\n{logs}"

            # Step 3: Building robot
            print("🤖 Building robot model...")
            try:
                robot_builder = RobotBuilder(config)
                robot = robot_builder.robot
                print("✅ Robot model built successfully")
            except SystemExit as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ SystemExit during robot building: {e}", file=sys.__stderr__)
                return f"❌ SystemExit during robot building: {e}\n\nLogs:\n{logs}"
            except Exception as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ Robot building failed: {e}", file=sys.__stderr__)
                return f"❌ Robot building failed: {e}\n\nLogs:\n{logs}"

            # Step 4: Applying processors
            print("⚙️ Applying processors...")
            try:
                for i, processor in enumerate(config.processors):
                    print(f"  Processing step {i+1}/{len(config.processors)}: {type(processor).__name__}")
                    processor.process(robot)
                print("✅ All processors applied successfully")
            except SystemExit as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ SystemExit during processor application: {e}", file=sys.__stderr__)
                return f"❌ SystemExit during processor application: {e}\n\nLogs:\n{logs}"
            except Exception as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ Processor application failed: {e}", file=sys.__stderr__)
                return f"❌ Processor application failed: {e}\n\nLogs:\n{logs}"

            # Step 5: Writing URDF
            print("📝 Writing URDF file...")
            try:
                output_path = (
                    config.output_directory
                    + "/"
                    + config.output_filename
                    + "."
                    + exporter.ext
                )
                print(f"  Output path: {output_path}")
                exporter.write_xml(robot, output_path)
                print("✅ URDF file written successfully")
            except SystemExit as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ SystemExit during URDF writing: {e}", file=sys.__stderr__)
                return f"❌ SystemExit during URDF writing: {e}\n\nLogs:\n{logs}"
            except Exception as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ URDF writing failed: {e}", file=sys.__stderr__)
                return f"❌ URDF writing failed: {e}\n\nLogs:\n{logs}"

            # Step 6: Post-import commands
            print("🚀 Running post-import commands...")
            try:
                for command in config.post_import_commands:
                    print(f"  * Running command: {command}")
                    os.system(command)
                print("✅ All post-import commands completed")
            except SystemExit as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ SystemExit during post-import commands: {e}", file=sys.__stderr__)
                return f"❌ SystemExit during post-import commands: {e}\n\nLogs:\n{logs}"
            except Exception as e:
                logs = stdout_capture.getvalue() + stderr_capture.getvalue()
                print(f"❌ Post-import commands failed: {e}", file=sys.__stderr__)
                return f"❌ Post-import commands failed: {e}\n\nLogs:\n{logs}"

            print("🎉 Robot processing completed successfully!")
        
        # Get captured logs
        logs = stdout_capture.getvalue() + stderr_capture.getvalue()
        print(f"📋 Captured {len(logs)} characters of logs")
        
        return f"""✅ OnShape to Robot conversion completed successfully!

Robot: {robot_name}
Output Path: {output_path}
Configuration Format: {config.output_format}

📋 Conversion Logs:
{logs}

🎉 The URDF file has been generated and is ready for simulation!"""

    except SystemExit as e:
        logs = stdout_capture.getvalue() + stderr_capture.getvalue()
        return f"❌ Unexpected SystemExit: {e}\n\nLogs:\n{logs}"
    except Exception as e:
        # Get captured logs including error
        logs = stdout_capture.getvalue() + stderr_capture.getvalue()
        error_message = str(e)
        
        return f"""❌ OnShape to Robot conversion failed!

Robot: {robot_name}
Error: {error_message}

📋 Error Logs:
{logs}

💡 Please check the robot configuration and assembly data files.""" 