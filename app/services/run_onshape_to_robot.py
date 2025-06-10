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
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Retrieving robot path
            if not robot_name:
                raise Exception("ERROR: you must provide the robot directory")

            robot_path: str = robot_name
            print(f"Processing robot directory: {robot_path}")

            # Loading configuration
            config = Config(robot_path)
            print(f"Loaded configuration for output format: {config.output_format}")

            # Building exporter beforehand, so that the configuration gets checked
            if config.output_format == "urdf":
                exporter = ExporterURDF(config)
            else:
                raise Exception(f"Unsupported output format: {config.output_format}")

            print("Building robot...")
            # Building the robot
            robot_builder = RobotBuilder(config)
            robot = robot_builder.robot

            # Can be used for debugging
            # pickle.dump(robot, open("robot.pkl", "wb"))
            # robot = pickle.load(open("robot.pkl", "rb"))

            print("Applying processors...")
            # Applying processors
            for processor in config.processors:
                processor.process(robot)

            output_path = (
                config.output_directory
                + "/"
                + config.output_filename
                + "."
                + exporter.ext
            )
            print(f"Writing URDF to: {output_path}")

            exporter.write_xml(robot, output_path)

            print("Running post-import commands...")
            for command in config.post_import_commands:
                print(f"* Running command: {command}")
                os.system(command)

            print("Robot processing completed successfully!")

        # Get captured logs
        logs = stdout_capture.getvalue() + stderr_capture.getvalue()
        return True, logs, ""

    except Exception as e:
        # Get captured logs including error
        logs = stdout_capture.getvalue() + stderr_capture.getvalue()
        error_message = str(e)
        print(f"ERROR: {e}")
        return False, logs, error_message
