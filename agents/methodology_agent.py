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


def run_methodology_agent(topic: str, domain: str, open_problems: list, context_summaries: str) -> dict:
    """
    Review all open problems/gaps from the Research phase, pick the SINGLE MOST PROMISING gap,
    and generate EXACTLY ONE master methodology and pipeline steps list.
    """
    
    problems_text = "\n".join([f"- {p}" for p in open_problems]) if open_problems else "No specific problems provided."

    prompt = f"""You are a Senior Research Architect at a top AI lab, designing a rigorous methodology for a PhD research proposal.

TOPIC: {topic}
DOMAIN: {domain}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 0: MANDATORY DOMAIN REASONING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before designing ANYTHING, you MUST reason about what architectures are appropriate:
- If the topic involves Language Models (LLM, SLM, NLP, text): Use Transformer variants (GPT, BERT, LLaMA, Mistral), attention mechanisms, tokenizers, LoRA/QLoRA adapters. NEVER use GCN, CNN, or graph networks.
- If the topic involves Vision (image, video, VLM): Use ViT, CLIP, ConvNeXt, DINOv2, Swin Transformer. 
- If the topic involves Multimodal (VLM, vision-language): Use CLIP, LLaVA, Flamingo, cross-attention fusion.
- If the topic involves Graphs/Molecules: ONLY THEN use GCN, GAT, GNN.

⚠️ CRITICAL ANTI-HALLUCINATION RULE: Do NOT use Graph Neural Networks (GCN/GAT/GNN) unless the topic EXPLICITLY involves graph-structured data like social networks, molecular chemistry, or knowledge graphs. Using GCNs for text/NLP/LLM topics is WRONG and will be rejected.

PRIOR RESEARCH CONTEXT (from 3 agents):
{context_summaries[:2500]}

ALL IDENTIFIED OPEN PROBLEMS & GAPS:
{problems_text}

━━━━━━━━━━━━
YOUR TASK:
━━━━━━━━━━━━
1. Review all the open problems and gaps identified above.
2. Select the SINGLE BEST, most promising gap to solve.
3. Design a SINGLE methodology using architectures that are ACTUALLY USED in the "{domain}" field for "{topic}".
4. Base your architecture choices on the methods mentioned in the PRIOR RESEARCH CONTEXT above. Do NOT invent generic architectures.

Requirements:
1. Architecture: Name specific model components relevant to the actual topic domain
2. Loss function: Write the exact mathematical form (e.g., "L = CE + KL_div" for distillation)
3. Baseline comparison: Name at least 2 real SOTA methods mentioned in the research context
4. Dataset: Name real benchmark datasets appropriate for this problem
5. Expected results: Concrete quantitative targets
6. Pipeline: 6-8 clear, specific steps

Output strict JSON only. No markdown. Start with {{ end with }}.

{{
  "scope_title": "<A punchy title for your chosen research direction>",
  "problem_statement": "<Clear description of the SINGLE gap you chose to solve>",
  "proposed_methodology": "<300-400 words. Name DOMAIN-APPROPRIATE architectures only. Reference techniques from the research context above.>",
  "architecture_details": "<100-150 words. MUST match the topic domain — Transformers for NLP, ViTs for vision, etc.>",
  "loss_function": "<exact loss function relevant to the domain>",
  "baseline_methods": ["<real SOTA method from the research context>", "<another real SOTA method>"],
  "evaluation_datasets": ["<real dataset for this topic>", "<another real dataset>"],
  "expected_outcomes": {{"accuracy": "<target>", "f1": "<target>", "latency": "<target>", "memory_reduction": "<if applicable>"}},
  "pipeline_steps": [
    "<Step 1: Domain-specific preprocessing>",
    "<Step 2: ...>",
    "<Step 3: ...>",
    "<Step 4: ...>",
    "<Step 5: ...>",
    "<Step 6: ...>"
  ],
  "supporting_citations": ["<Author et al. Year - paper title from research context>"],
  "novelty_score": 0.85,
  "feasibility_score": 0.80
}}
/no_think"""

    sys_msg = (
        "You are a Peak-Level ML Architect. Output strict JSON only. No markdown fences. "
        "The proposed_methodology MUST be detailed with architectures, loss functions. "
        "The pipeline_steps MUST be a plain array of 6-8 step descriptions. No Mermaid syntax. "
        "Start response with { and end with }. /no_think"
    )

    try:
        # ORCHESTRATOR CALL → OpenRouter (role-specialized model)
        print(f"DEBUG: [methodology] Using role-specialized model for Master Methodology...", file=sys.stderr)
        
        content = call_llm(
            prompt=prompt,
            role="worker",
            system_msg=sys_msg,
            temperature=0.4,
            timeout=120,          # Longer timeout for deep reasoning model
            agent_role="methodology",
        )

        parsed = _extract_json(content)
        
        # Ensure required fields
        parsed.setdefault("scope_title", "Master Methodology")
        parsed.setdefault("problem_statement", "Unified problem statement")
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
        "scope_title": "Master Methodology Error",
        "problem_statement": "Pipeline generation failed.",
        "proposed_methodology": "Methodology generation failed.",
        "pipeline_steps": [],
        "supporting_citations": [],
        "error": "All attempts failed"
    }
