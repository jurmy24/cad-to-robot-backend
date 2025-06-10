#!/usr/bin/env python3

from app.services.run_onshape_to_robot import run_onshape_to_robot
import os

if __name__ == "__main__":
    robot_name = "folding-mechanism"
    robot_path = f"data/{robot_name}"
    
    print(f"🤖 Running OnShape to Robot conversion for: {robot_path}")
    print("=" * 60)
    print("This may take a while...")
    print("=" * 60)
    
    # Make sure we're in the right directory
    print(f"Current working directory: {os.getcwd()}")
    
    try:
        success, logs, error_message = run_onshape_to_robot(robot_path)
        
        print("\n" + "=" * 60)
        if success:
            print("✅ OnShape to Robot conversion completed successfully!")
        else:
            print(f"❌ OnShape to Robot conversion failed!")
            if error_message:
                print(f"Error: {error_message}")
        
        print("\nConversion logs:")
        print("-" * 40)
        print(logs)
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Exception during conversion: {str(e)}")
        import traceback
        traceback.print_exc() 