import os
import sys
import shutil
import subprocess
from dotenv import load_dotenv

load_dotenv()

def test_paperbanana():
    # Check key
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        print("FAIL: No GEMINI_API_KEY or GOOGLE_API_KEY found.")
        return

    # Map key if needed
    if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

    # Check command
    cmd_path = shutil.which("paperbanana")
    if not cmd_path:
        print("FAIL: 'paperbanana' command not found in PATH.")
        return

    print(f"PASS: Key found. Command found at {cmd_path}.")
    
    # Try generation?
    # We can try a simple generation task
    print("Running generation test (simple)...")
    
    input_text = "This is a test architecture with a Client, Server, and Database."
    input_file = "test_pb_input.txt"
    with open(input_file, "w") as f:
        f.write(input_text)
        
    try:
        cmd = ["paperbanana", "generate", "--input", input_file, "--caption", "Test Diagram"]
        result = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())
        
        if result.returncode == 0:
            print("PASS: Generation successful.")
            print("Output:\n", result.stdout)
        else:
            print("FAIL: Generation failed.")
            print("Stderr:\n", result.stderr)
            print("Stdout:\n", result.stdout)
            
    except Exception as e:
        print(f"FAIL: Exception running subprocess: {e}")
    finally:
        if os.path.exists(input_file):
            os.remove(input_file)

if __name__ == "__main__":
    test_paperbanana()
