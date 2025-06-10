import os
import json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import json

from typing_extensions import TypedDict, Any

from agents import Agent, Runner, FunctionTool, RunContextWrapper, function_tool

# Import all augmented tools
from augmented_tools.read_mates import read_mates
from augmented_tools.read_urdf import read_urdf
from augmented_tools.rename_mates import rename_mates
from augmented_tools.remove_duplicate_links import remove_duplicate_links
from augmented_tools.set_material import set_material, set_multiple_materials

load_dotenv()

@function_tool
async def read_json_files(folder_name: str) -> str:
    """Read all JSON files from the given data folder.
    
    Args:
        folder_name: Name of the folder under data/ to read from
        
    Returns:
        JSON string containing filenames mapped to their contents
    """
    data_path = Path("data") / folder_name
    if not data_path.exists():
        return json.dumps({})
        
    json_files = {}
    for file_path in data_path.glob("*.json"):
        try:
            with open(file_path, 'r') as f:
                json_files[file_path.name] = json.load(f)
        except json.JSONDecodeError as e:
            json_files[file_path.name] = f"Error loading JSON: {e}"
            
    return json.dumps(json_files, indent=2)


def load_system_prompt() -> str:
    """Load the system prompt from system_prompts.txt"""
    try:
        with open("system_prompts.txt", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are a CAD to URDF conversion assistant."

# Update agent with system prompt
system_prompt = load_system_prompt()
prompt = system_prompt + "\n\n" + "The folder name to perform conversion on is: folding-mechanism"

# Create agent with all available tools
agent = Agent(
    name="CADtoURDFAgent",
    tools=[
        read_mates,
        read_urdf,
        rename_mates,
        remove_duplicate_links,
        set_material,
        set_multiple_materials
    ],  
    model="o4-mini",
)


if __name__ == "__main__":
    result = Runner.run_sync(agent, prompt)
    print(result.final_output)