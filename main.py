import os
import json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class CADtoURDFAgent:
    def __init__(self, data_folder="folding-mechanism"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.data_folder = data_folder
        self.data_path = Path("data") / data_folder
        
        # Load system prompts
        self.system_prompts = self.load_system_prompts()
        
        # Initialize conversation history
        self.conversation_history = [
            {"role": "system", "content": self.system_prompts}
        ]
        
        print(f"CAD to URDF Agent initialized with data from: {self.data_path}")
        print(f"Available files: {list(self.data_path.glob('*'))}")
    
    def load_system_prompts(self):
        """Load system prompts from system_prompts.txt"""
        try:
            with open("system_prompts.txt", "r") as f:
                return f.read().strip()
        except FileNotFoundError:
            return "You are a CAD to URDF conversion assistant."
    
    def load_data_file(self, filename):
        """Load a specific data file from the current data folder"""
        file_path = self.data_path / filename
        
        if not file_path.exists():
            return f"File {filename} not found in {self.data_folder}"
        
        if filename.endswith('.json'):
            try:
                with open(file_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                return f"Error loading JSON file {filename}: {e}"
        
        elif filename.endswith('.urdf'):
            try:
                with open(file_path, 'r') as f:
                    return f.read()
            except Exception as e:
                return f"Error loading URDF file {filename}: {e}"
        
        else:
            try:
                with open(file_path, 'r') as f:
                    return f.read()
            except Exception as e:
                return f"Error loading file {filename}: {e}"
    
    def get_available_files(self):
        """Get list of available files in the current data folder"""
        if not self.data_path.exists():
            return []
        return [f.name for f in self.data_path.iterdir() if f.is_file()]
    
    def chat(self, message):
        """Send a message to the agent and get a response"""
        # Add user message to conversation history
        self.conversation_history.append({"role": "user", "content": message})
        
        try:
            # Create completion using OpenAI
            response = self.client.chat.completions.create(
                model="o4-mini",
                messages=self.conversation_history,
                temperature=0.7,
            )
            
            # Extract the assistant's response
            assistant_response = response.choices[0].message.content
            
            # Add assistant response to conversation history
            self.conversation_history.append({"role": "assistant", "content": assistant_response})
            
            return assistant_response
            
        except Exception as e:
            error_msg = f"Error communicating with OpenAI: {e}"
            print(error_msg)
            return error_msg
    
    def analyze_assembly(self):
        """Analyze the current assembly data"""
        files = self.get_available_files()
        
        analysis = {
            "available_files": files,
            "assembly_data": None,
            "features_data": None,
            "mate_values": None,
            "urdf_content": None
        }
        
        # Load key files if available
        if "assembly_data.json" in files:
            analysis["assembly_data"] = self.load_data_file("assembly_data.json")
        
        if "features_data.json" in files:
            analysis["features_data"] = self.load_data_file("features_data.json")
        
        if "matevalues_data.json" in files:
            analysis["mate_values"] = self.load_data_file("matevalues_data.json")
        
        if "robot.urdf" in files:
            analysis["urdf_content"] = self.load_data_file("robot.urdf")
        
        return analysis


if __name__ == "__main__":
    # Initialize the agent with folding-mechanism data
    agent = CADtoURDFAgent("folding-mechanism")
    
    # Show initial analysis
    analysis = agent.analyze_assembly()
    print(f"\nFound {len(analysis['available_files'])} files in data folder")
    
    # Start with a welcome message
    welcome_message = """Hello! I'm ready to help convert your CAD assembly to URDF. 
I can analyze the folding-mechanism assembly and help fix common issues like:
- Renaming mates to proper 'dof_' format for joints
- Removing duplicate links in URDF files
- General assembly analysis and troubleshooting

What would you like me to help you with today?"""
    
    print(f"\nAgent: {welcome_message}")
    
    # Interactive loop (optional - can be removed for programmatic use)
    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ['quit', 'exit', 'bye']:
                break
            
            response = agent.chat(user_input)
            print(f"\nAgent: {response}")
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break