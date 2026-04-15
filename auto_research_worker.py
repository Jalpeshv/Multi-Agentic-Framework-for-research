import os
import sys
import time
import json
import concurrent.futures
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from agents.research_agent import run_research_agent
from agents.methodology_agent import run_methodology_agent
from agents.visualizer_agent import run_visualizer_agent
from agents.invoice_agent import run_invoice_agent

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "autonomous_runs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def print_status(msg):
    print(f"[\033[96mAUTO-RESEARCH\033[0m] {msg}")

def run_agent_headless(fn, *args, timeout_seconds=600, **kwargs):
    """Headless executor with timeout safeguard, similar to our Streamlit fix."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, *args, **kwargs)
        start_time = time.time()
        
        while not future.done():
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                future.cancel()
                return None, f"Timeout after {timeout_seconds}s"
            # Print a dot every 10 seconds to show it's alive
            if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                print(".", end="", flush=True)
                time.sleep(1)
            time.sleep(0.5)
            
        print() # newline
        try:
            return future.result(timeout=0), None
        except Exception as e:
            return None, str(e)

def autonomous_pipeline(topic: str, domain: str, system_category: str):
    """Runs the entire pipeline autonomously for a given topic."""
    import re
    safe_topic = re.sub(r'[^a-zA-Z0-9_\-]', '', topic.replace(' ', '_').lower())[:50]
    run_id = f"{safe_topic}_{int(time.time())}"
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(exist_ok=True)
    
    print_status(f"🚀 Starting Autonomous Research on: '{topic}'")
    print_status(f"📁 Output directory: {run_dir}")

    # ==========================================
    # PHASE 1: RESEARCH
    # ==========================================
    print_status("Phase 1: Deep Research (Gathering Context)...")
    research_outputs = []
    roles = ["historical", "state_of_the_art", "ongoing_emerging"]
    
    for role in roles:
        print(f"  -> Agent [{role}] thinking...", end="", flush=True)
        out, err = run_agent_headless(run_research_agent, topic, domain, role, years=5, timeout_seconds=300)
        
        if err or (out and out.get("status") == "failed"):
            print(f" \033[91mFAILED\033[0m: {err or out.get('error')}")
        else:
            print(" \033[92mSUCCESS\033[0m")
            research_outputs.append(out)
            
    if not research_outputs:
        print_status("\033[91mPipeline aborted: All research agents failed.\033[0m")
        return

    # ==========================================
    # PHASE 2: VISUALIZATION (PAPER BANANA)
    # ==========================================
    print_status("Phase 2: Generating System Architectures (PaperBanana + Fallbacks)...")
    print("  -> Visualizer Agent extracting and designing diagram...", end="", flush=True)
    
    # Karpathy style self-correction loop just for visuals
    max_diagram_attempts = 2
    master_visual = None
    
    for attempt in range(max_diagram_attempts):
        visual_out, vis_err = run_agent_headless(
            run_visualizer_agent, topic, domain, research_outputs, system_category=system_category, timeout_seconds=600
        )
        
        if vis_err or (visual_out and visual_out.get("status") == "failed"):
            print(f"\n  -> \033[93mAttempt {attempt+1} Failed: {vis_err or visual_out.get('error')}. Retrying...\033[0m", end="", flush=True)
            time.sleep(5)
        else:
            print(" \033[92mSUCCESS\033[0m")
            master_visual = visual_out
            break
            
    if not master_visual:
        print_status("\033[93mVisualizer struggled. Proceeding with empty visuals.\033[0m")
        master_visual = {"status": "failed", "error": "Maximum diagram attempts reached."}

    # ==========================================
    # PHASE 3: PHD-GRADE REPORT
    # ==========================================
    print_status("Phase 3: Synthesizing PhD-Grade Report...")
    print("  -> Invoice Agent compiling whitepaper...", end="", flush=True)
    
    report_out, rep_err = run_agent_headless(
        run_invoice_agent, topic, domain, research_outputs, master_visual, timeout_seconds=600
    )
    
    if rep_err or (report_out and report_out.get("status") == "failed"):
        print(f" \033[91mFAILED\033[0m: {rep_err or report_out.get('error')}")
    else:
        print(" \033[92mSUCCESS\033[0m")
        
        # Save output to disk
        md_file = run_dir / "final_report.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(report_out.get("md_content", "No content generated."))
        print_status(f"📄 Report saved to: {md_file}")

    # ==========================================
    # SAVE ASSETS & METADATA
    # ==========================================
    with open(run_dir / "research_data.json", "w", encoding="utf-8") as f:
        json.dump(research_outputs, f, indent=2)
        
    if master_visual and master_visual.get("status") == "ok":
        with open(run_dir / "visual_metadata.json", "w", encoding="utf-8") as f:
            json.dump(master_visual, f, indent=2)
            
        print_status(f"🎨 Diagram outputs available in run directory: {run_dir}")
        for k, path in master_visual.get("image_paths", {}).items():
            print(f"     - {k}: {path}")

    print_status(f"✅ Autonomous Run for '{topic}' Complete!\n")

if __name__ == "__main__":
    print_status("Welcome to the Autonomous Research Worker")
    print_status("Edit the AGENDA list below to add your research topics.")
    print("-" * 60)
    
    # Add your own topics here
    AGENDA = [
        {
            "topic": "Graph Neural Networks for Memory-Efficient Training",
            "domain": "computer science",
            "category": "AI & Machine Learning"
        }
    ]
    
    for item in AGENDA:
        autonomous_pipeline(item["topic"], item["domain"], item["category"])
        time.sleep(10)  # Cooldown between topics

