# Takes assembly data and runs it through onshape-to-robot, stores it in data/ and returns logs + the new zip file
import os
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
from dotenv import load_dotenv, find_dotenv
from onshape.src.config import Config
from onshape.src.robot_builder import RobotBuilder
from onshape.src.exporter_urdf import ExporterURDF


def run_onshape_to_robot(robot_name: str):
    """
    This is the entry point of the export script, i.e the "onshape-to-robot" command.
    Takes a robot directory path and processes it to generate URDF files.
    Returns a tuple of (success: bool, logs: str, error_message: str)
    """
    load_dotenv(find_dotenv(usecwd=True))

    # Capture stdout and stderr to return as logs
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    logs = ""
    error_message = ""

    try:
        print("🚀 Starting OnShape to Robot conversion...")
        
        # Retrieving robot path
        if not robot_name:
            raise Exception("ERROR: you must provide the robot directory")

        robot_path: str = robot_name
        print(f"📁 Processing robot directory: {robot_path}")

        # Step 1: Loading configuration
        print("📋 Loading configuration...")
        try:
            config = Config(robot_path)
            print(f"✅ Loaded configuration for output format: {config.output_format}")
        except SystemExit as e:
            error_message = f"SystemExit during Config loading: {e}"
            print(f"❌ {error_message}")
            return False, f"Config loading failed with SystemExit: {e}", error_message
        except Exception as e:
            error_message = f"Config loading failed: {e}"
            print(f"❌ {error_message}")
            return False, f"Config loading error: {e}", error_message

        # Step 2: Building exporter
        print("🏗️ Creating exporter...")
        try:
            if config.output_format == "urdf":
                exporter = ExporterURDF(config)
                print("✅ URDF exporter created successfully")
            else:
                raise Exception(f"Unsupported output format: {config.output_format}")
        except SystemExit as e:
            error_message = f"SystemExit during exporter creation: {e}"
            print(f"❌ {error_message}")
            return False, f"Exporter creation failed with SystemExit: {e}", error_message
        except Exception as e:
            error_message = f"Exporter creation failed: {e}"
            print(f"❌ {error_message}")
            return False, f"Exporter creation error: {e}", error_message

        # Step 3: Building robot
        print("🤖 Building robot model...")
        try:
            robot_builder = RobotBuilder(config)
            robot = robot_builder.robot
            print("✅ Robot model built successfully")
        except SystemExit as e:
            error_message = f"SystemExit during robot building: {e}"
            print(f"❌ {error_message}")
            return False, f"Robot building failed with SystemExit: {e}", error_message
        except Exception as e:
            error_message = f"Robot building failed: {e}"
            print(f"❌ {error_message}")
            return False, f"Robot building error: {e}", error_message

        # Step 4: Applying processors
        print("⚙️ Applying processors...")
        try:
            for i, processor in enumerate(config.processors):
                print(f"  Processing step {i+1}/{len(config.processors)}: {type(processor).__name__}")
                processor.process(robot)
            print("✅ All processors applied successfully")
        except SystemExit as e:
            error_message = f"SystemExit during processor application: {e}"
            print(f"❌ {error_message}")
            return False, f"Processor application failed with SystemExit: {e}", error_message
        except Exception as e:
            error_message = f"Processor application failed: {e}"
            print(f"❌ {error_message}")
            return False, f"Processor application error: {e}", error_message

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
            error_message = f"SystemExit during URDF writing: {e}"
            print(f"❌ {error_message}")
            return False, f"URDF writing failed with SystemExit: {e}", error_message
        except Exception as e:
            error_message = f"URDF writing failed: {e}"
            print(f"❌ {error_message}")
            return False, f"URDF writing error: {e}", error_message

        # Step 6: Post-import commands
        print("🚀 Running post-import commands...")
        try:
            for command in config.post_import_commands:
                print(f"  * Running command: {command}")
                os.system(command)
            print("✅ All post-import commands completed")
        except SystemExit as e:
            error_message = f"SystemExit during post-import commands: {e}"
            print(f"❌ {error_message}")
            return False, f"Post-import commands failed with SystemExit: {e}", error_message
        except Exception as e:
            error_message = f"Post-import commands failed: {e}"
            print(f"❌ {error_message}")
            return False, f"Post-import commands error: {e}", error_message

        print("🎉 Robot processing completed successfully!")
        logs = "Conversion completed successfully with detailed error tracking"
        return True, logs, ""

    except SystemExit as e:
        error_message = f"Unexpected SystemExit: {e}"
        print(f"❌ {error_message}")
        return False, f"Process terminated with SystemExit: {e}", error_message
    except Exception as e:
        error_message = str(e)
        print(f"❌ Unexpected error: {error_message}")
        import traceback
        traceback.print_exc()
        return False, f"Unexpected error: {error_message}", error_message
