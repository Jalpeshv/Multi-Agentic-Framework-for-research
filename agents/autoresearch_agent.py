# agents/autoresearch_agent.py
"""
Autoresearch Agent — Hybrid Architecture.
  • ORCHESTRATOR calls (code generation) → OpenRouter (cloud, high intelligence)

Stays on OpenRouter because code generation requires maximum quality.
"""

import os
import sys
import time
import subprocess
import shutil
import json
import re
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from agents.llm_client import _get_openrouter_client as _get_groq_client, strip_think_tags, _call_openrouter_api

AUTORESEARCH_ROOT = PROJECT_ROOT / "autoresearch"
TRAIN_FILE = AUTORESEARCH_ROOT / "train.py"
RESULTS_FILE = AUTORESEARCH_ROOT / "results.tsv"
LOG_FILE = AUTORESEARCH_ROOT / "run.log"
PROGRAM_FILE = AUTORESEARCH_ROOT / "program.md"

# Use google/gemini-2.5-flash — best value on OpenRouter ($0.30/M, 1M context)
MODEL = "google/gemini-2.5-flash"

def _extract_python_code(text: str) -> str:
    """Correctly extract Python code from markdown blocks."""
    text = strip_think_tags(text)
    match = re.search(r'```python\s*([\s\S]+?)\s*```', text)
    if match: return match.group(1)
    match = re.search(r'```\s*([\s\S]+?)\s*```', text)
    if match: return match.group(1)
    # If no blocks, assume raw code if it looks like python
    if "def " in text or "import " in text: return text
    return ""

def run_autoresearch(topic: str, domain: str = None, duration_minutes: int = 5) -> Dict[str, Any]:
    """
    Implements the autonomous research loop described in program.md.
    1. Reads train.py
    2. Suggests modification (LLM)
    3. Runs experiment
    4. Evaluates & Logs
    
    This function acts as the 'Autonomous Researcher' agent for one or more iterations 
    within the given time budget.
    """
    
    if not AUTORESEARCH_ROOT.exists():
        return {"status": "failed", "error": "autoresearch folder missing"}

    client = _get_groq_client()  # Returns an OpenRouter API key
    if not client:
        return {"status": "failed", "error": "No OPENROUTER_API_KEY"}

    # Check for uv
    if shutil.which("uv") is None:
         return {"status": "failed", "error": "'uv' tool not found in PATH. Please install uv."}

    # 1. Initialize Context
    baseline_bpb = 999.0
    has_baseline = False
    
    if not RESULTS_FILE.exists():
        RESULTS_FILE.write_text("commit\tval_bpb\tmemory_gb\tstatus\tdescription\n", encoding="utf-8")
    else:
        # Read baseline from last keep
        lines = RESULTS_FILE.read_text(encoding="utf-8").strip().split('\n')
        for line in lines[1:]:
            parts = line.split('\t')
            if len(parts) >= 4 and parts[3] == 'keep':
                 try: 
                     val = float(parts[1])
                     if val > 0: 
                        baseline_bpb = val
                        has_baseline = True
                 except: pass

    # Read program guidelines
    try:
        guidelines = PROGRAM_FILE.read_text(encoding="utf-8", errors="replace") if PROGRAM_FILE.exists() else "Minimize val_bpb."
    except Exception as e:
        guidelines = "Minimize val_bpb."
        print(f"DEBUG: Error reading program.md: {e}", file=sys.stderr)
    
    # Read current code
    if not TRAIN_FILE.exists():
        return {"status": "failed", "error": "train.py missing"}
    
    try:
        current_code = TRAIN_FILE.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"status": "failed", "error": f"Error reading train.py: {e}"}
    
    # If no baseline, force first run to be baseline (no modification)
    force_baseline_run = not has_baseline

    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    experiment_log = []
    iteration = 0
    final_program_update = ""

    print(f"DEBUG: Starting AutoResearch Loop. Baseline BPB: {baseline_bpb}", file=sys.stderr)

    while time.time() < end_time:
        iteration += 1
        remaining = int(end_time - time.time())
        # If we need to run a 5-min training job, checking for <60s might be too tight, but let's stick to it.
        if remaining < 60: break 

        print(f"DEBUG: Iteration {iteration}. Remaining: {remaining}s", file=sys.stderr)

        # Decide whether to optimize or run baseline
        new_code = current_code
        description = "baseline_run"
        
        if not force_baseline_run:
            # A. GENERATE IDEA & CODE
            prompt = f"""
{guidelines}

CURRENT FOCUS: {topic}
CURRENT BASELINE VAL_BPB: {baseline_bpb}

Here is the current `train.py`:
`python
{current_code}
`

TASK:
1. Propose a mathematically rigorously-justified, PEAK PhD-level architectural improvement to radically lower val_bpb.
2. Consider advanced deep learning optimizations (custom learning rate schedules, novel activation functions, specialized attention variants, structural re-parameterizations).
3. Output the FULL updated `train.py` code. DO NOT omit any imports or boilerplate. Provide complete, runnable code.
4. Briefly explain the theoretical mechanism and expected gradient/optimization advantages in a structured python docstring at the top.

Your code must be flawless, robust, and mathematically deep. Output only valid Python syntax. /no_think"""
            try:
                raw_output = _call_openrouter_api(
                    api_key=client,
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": "You are an autonomous AI writing performant PyTorch code."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                )
                generated_code = _extract_python_code(raw_output)
                
                if "Description:" in raw_output:
                    description = raw_output.split("Description:")[1].split("\n")[0].strip()
                else:
                    description = f"experiment_{iteration}"
                
                if not generated_code or len(generated_code) < 100:
                    print(f"DEBUG: LLM generation failed/empty.", file=sys.stderr)
                    experiment_log.append(f"Run {iteration}: LLM Generation Failed")
                    continue
                
                new_code = generated_code
                
            except Exception as e:
                experiment_log.append(f"LLM Error: {e}")
                # Wait a bit before retry to avoid rapid loop on API error
                time.sleep(10)
                continue
        else:
             print("DEBUG: Executing baseline run (no changes).", file=sys.stderr)
             description = "baseline_initialization"



        # B. APPLY CHANGE
        # Backup
        backup_code = current_code
        TRAIN_FILE.write_text(new_code, encoding="utf-8")
        
        # C. RUN EXPERIMENT
        # Run uv run train.py
        # Timeout is 5 mins (300s) hard limit
        
        run_status = "crash"
        val_bpb = 0.0
        mem_gb = 0.0
        
        try:
            # We enforce a slightly shorter timeout than the loop remaining time
            cmd_timeout = min(300, remaining - 10)
            
            # On windows, we might need full path to uv or python if not in path
            # Assuming 'uv' is in path as per user
            
            proc = subprocess.run(
                "uv run train.py",
                cwd=str(AUTORESEARCH_ROOT),
                shell=True,
                capture_output=True,
                text=True,
                timeout=cmd_timeout
            )
            
            stdout = proc.stdout
            stderr = proc.stderr
            LOG_FILE.write_text(stdout + "\nSTDERR:\n" + stderr, encoding="utf-8")
            
            if proc.returncode != 0:
                run_status = "crash"
                experiment_log.append(f"Run {iteration}: CRASH ({description})")
            else:
                # Parse metrics
                # Expected format: val_bpb: 0.1234
                bpb_match = re.search(r"val_bpb:\s*([\d\.]+)", stdout)
                if bpb_match:
                    val_bpb = float(bpb_match.group(1))
                    run_status = "keep" if val_bpb < baseline_bpb else "discard"
                else:
                    run_status = "crash" # No metric found
                    
                # Parse memory
                mem_match = re.search(r"peak_vram_mb:\s*([\d\.]+)", stdout)
                if mem_match:
                    mem_gb = float(mem_match.group(1)) / 1024.0

        except subprocess.TimeoutExpired:
            run_status = "crash"
            experiment_log.append(f"Run {iteration}: TIMEOUT ({description})")
        except Exception as e:
            run_status = "crash"
            experiment_log.append(f"Run {iteration}: EXEC ERROR {e}")

        # D. DECIDE & LOG
        log_line = f"iter{iteration}\t{val_bpb:.6f}\t{mem_gb:.1f}\t{run_status}\t{description}\n"
        with open(RESULTS_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
            
        if run_status == "keep":
            baseline_bpb = val_bpb
            current_code = new_code
            experiment_log.append(f"Run {iteration}: SUCCESS {val_bpb:.4f} ({description}) - KEPT")
            final_program_update = f"Optimized {topic}: New Baseline {val_bpb:.4f}"
            force_baseline_run = False # Success, we have a baseline
        else:
            # Revert
            TRAIN_FILE.write_text(backup_code, encoding="utf-8")
            if force_baseline_run:
                 experiment_log.append(f"Run {iteration}: BASELINE FAILED {val_bpb:.4f} ({description})")
                 # If baseline fails, we might adhere to a fail state, but we'll try to continue or loop?
                 # If baseline crashes, we can't do much. 
            else:
                 experiment_log.append(f"Run {iteration}: REJECTED {val_bpb:.4f} ({description})")

    # Generate Report
    summary = f"### Autonomous Optimization Report\n\n"
    summary += f"**Topic**: {topic}\n"
    summary += f"**Final Best Val BPB**: {baseline_bpb}\n\n"
    summary += "**Experiment Log**:\n"
    for log in experiment_log:
        summary += f"- {log}\n"
    
    summary += "\n**Results.tsv Tail**:\n"
    try:
        summary += "```tsv\n" + "\n".join(RESULTS_FILE.read_text().splitlines()[-5:]) + "\n```"
    except: pass

    return {
        "status": "success",
        "summary": summary,
        "program_path": str(PROGRAM_FILE),
        "results_path": str(RESULTS_FILE)
    }







