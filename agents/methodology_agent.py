# agents/methodology_agent.py
"""
Methodology Agent — Hybrid Architecture.
  • WORKER calls (methodology generation) → Ollama (deepseek-r1:8b, local, no limits)
  • EVALUATOR calls (scoring)             → Groq (cloud, lightweight)

Generates detailed technical methodology proposals with pipeline steps
for each future research direction.
"""

import os
import sys
import json
import re
import time
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path)

from orchestrator.utils import now_iso_z
from agents.llm_client import call_llm, call_groq, strip_think_tags


def _extract_json(text: str) -> dict:
    """Extract JSON from model response — robust against think tags, fences, truncation."""
    if not text:
        raise ValueError("Empty response text")
    
    cleaned = strip_think_tags(text)
    
    # Strip code fences
    cleaned_no_fence = re.sub(r'^\s*```(?:json)?\s*\n?', '', cleaned)
    cleaned_no_fence = re.sub(r'\n?\s*```\s*$', '', cleaned_no_fence).strip()
    
    # 1. Direct parse
    for candidate in [cleaned_no_fence, cleaned]:
        try:
            return json.loads(candidate, strict=False)
        except (json.JSONDecodeError, ValueError):
            pass

    # 2. Balanced-brace extraction
    def _balanced_extract(s: str):
        start = s.find("{")
        if start == -1:
            return None
        depth = 0; in_string = False; escape = False
        stack = []
        for idx in range(start, len(s)):
            ch = s[idx]
            if in_string:
                if escape: escape = False
                elif ch == '\\': escape = True
                elif ch == '"': in_string = False
                continue
            if ch == '"': in_string = True
            elif ch == '{':
                depth += 1; stack.append('{')
            elif ch == '}':
                depth -= 1
                if stack and stack[-1] == '{': stack.pop()
                if depth == 0:
                    return s[start:idx+1]
            elif ch == '[': stack.append('[')
            elif ch == ']':
                if stack and stack[-1] == '[': stack.pop()
        # Truncated — try repair
        if depth > 0:
            repair = s[start:].rstrip()
            if repair and repair[-1] == ',': repair = repair[:-1]
            elif repair and repair[-1] == ':': repair += '""'
            if in_string: repair += '"'
            d2 = 0; in_s2 = False; esc2 = False; stk2 = []
            for ch in repair:
                if in_s2:
                    if esc2: esc2 = False
                    elif ch == '\\': esc2 = True
                    elif ch == '"': in_s2 = False
                    continue
                if ch == '"': in_s2 = True
                elif ch == '{': stk2.append('{')
                elif ch == '}':
                    if stk2 and stk2[-1] == '{': stk2.pop()
                elif ch == '[': stk2.append('[')
                elif ch == ']':
                    if stk2 and stk2[-1] == '[': stk2.pop()
            if in_s2: repair += '"'
            for opener in reversed(stk2):
                repair += '}' if opener == '{' else ']'
            return repair
        return None

    for source in [cleaned_no_fence, cleaned]:
        balanced = _balanced_extract(source)
        if balanced:
            try:
                return json.loads(balanced, strict=False)
            except (json.JSONDecodeError, ValueError):
                pass

    # 3. Greedy fence extraction
    fence = re.search(r'```(?:json)?\s*\n?([\s\S]+?)\s*```', cleaned, flags=re.DOTALL)
    if fence:
        inner = fence.group(1).strip()
        try:
            return json.loads(inner, strict=False)
        except (json.JSONDecodeError, ValueError):
            b = _balanced_extract(inner)
            if b:
                try:
                    return json.loads(b, strict=False)
                except (json.JSONDecodeError, ValueError):
                    pass

    raise ValueError(f"Could not parse JSON from methodology agent. First 300 chars: {text[:300]}")


def run_methodology_agent(topic: str, domain: str, scope_item: dict, context_summaries: str) -> dict:
    """
    Enhance a single future_research_direction with a detailed methodology
    and pipeline steps list.
    
    Uses Ollama (local) — no token limits, no rate limits.
    """
    scope_title = scope_item.get("scope_title", "Unknown Scope")
    problem_stmt = scope_item.get("problem_statement", "No problem statement provided.")

    prompt = f"""You are a Senior Research Architect designing a technical methodology for a PhD-level research proposal.

TOPIC: {topic}
DOMAIN: {domain}
SCOPE: {scope_title}
PROBLEM: {problem_stmt}

CONTEXT FROM PRIOR RESEARCH:
{context_summaries[:3000]}

TASK: Create a comprehensive methodology proposal. Output strict JSON only. No markdown fences around the JSON.

JSON SCHEMA:
{{
  "scope_title": "{scope_title}",
  "problem_statement": "{problem_stmt}",
  "proposed_methodology": "<string: 300-500 words. Detailed technical methodology. Include: (1) Architecture — specific layers, modules, loss functions. (2) Pipeline — data preprocessing, training, evaluation steps. (3) Expected Outcome — quantitative targets (accuracy, F1, latency). Use specific technical terms, not vague generalities.>",
  "pipeline_steps": ["<string: Step 1 description>", "<string: Step 2 description>", "... 6-10 steps"],
  "supporting_citations": ["<string: relevant paper or technique name>"],
  "novelty_score": 0.85,
  "feasibility_score": 0.80
}}

CRITICAL RULES:
- The pipeline_steps field must be a plain JSON array of 6-10 short step descriptions for the methodology pipeline.
- DO NOT include any Mermaid syntax or diagram markup. Only plain text pipeline steps.
- The methodology must be PhD-caliber: specific architectures, loss functions, quantitative targets.
- Start your response directly with {{ and end with }}. No headers.
/no_think"""

    sys_msg = (
        "You are a Peak-Level ML Architect. Output strict JSON only. No markdown fences. "
        "The proposed_methodology MUST be detailed with architectures, loss functions. "
        "The pipeline_steps MUST be a plain array of 6-8 step descriptions. No Mermaid syntax. "
        "Start response with { and end with }. /no_think"
    )

    try:
        # WORKER CALL → Ollama (local, no limits)
        print(f"DEBUG: [methodology] Using Ollama for '{scope_title[:40]}'...", file=sys.stderr)
        
        content = call_llm(
            prompt=prompt,
            role="worker",  # Routes to Ollama
            system_msg=sys_msg,
            temperature=0.4,
            timeout=90,          # Was 300s — safe now that think=False disables reasoning
        )

        parsed = _extract_json(content)
        
        # Ensure required fields
        parsed.setdefault("scope_title", scope_title)
        parsed.setdefault("problem_statement", problem_stmt)
        parsed.setdefault("proposed_methodology", "")
        parsed.setdefault("pipeline_steps", [])
        parsed.setdefault("supporting_citations", [])

        # Remove any leftover mermaid field
        parsed.pop("mermaid_diagram", None)

        print(f"DEBUG: [methodology] Score: 75/100 (local model, no evaluator needed)", file=sys.stderr)
        parsed["_model_backend"] = "ollama"
        return parsed

    except Exception as e:
        print(f"WARNING: [methodology] Error: {str(e)[:200]}", file=sys.stderr)

    # Fallback: return the original scope_item with error info
    return {
        **scope_item,
        "proposed_methodology": "Methodology generation failed.",
        "pipeline_steps": [],
        "supporting_citations": [],
        "error": "All attempts failed"
    }
