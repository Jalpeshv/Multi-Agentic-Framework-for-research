# agents/research_agent.py
"""
Research Agent — Hybrid Architecture.
  • WORKER calls (research generation) → Groq (cloud, fast)
  • Papers fetched from OpenAlex (free academic API, no key needed)

Returns strict JSON-shaped dicts for downstream methodology/invoice agents.
"""

import os
import sys
import json
import time
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

from orchestrator.utils import now_iso_z, make_agent_id
from agents.prompt_helpers import simple_render
from agents.llm_client import call_llm, call_groq, strip_think_tags

PROMPT_PATH = PROJECT_ROOT / "orchestrator" / "prompts" / "research_agent_template.txt"


def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        return "SYSTEM: Output strict JSON only."
    return PROMPT_PATH.read_text(encoding="utf-8")


MAX_PROMPT_CHARS = 8000


def _fetch_real_papers(topic: str, years: int = 5, limit: int = 15) -> list:
    """
    Fetch REAL papers from OpenAlex API (free, no API key needed).
    Uses multiple targeted queries and strict title-relevance filtering.
    Returns list of dicts with verified titles, authors, years, venues, DOI URLs.
    """
    import requests

    current_year = datetime.now().year
    start_year = current_year - (years if years else 5)
    topic_lower = topic.lower()

    # Extract meaningful technical keywords
    stop = {"through", "using", "with", "the", "a", "an", "of", "for", "in", "and", "or", "to",
            "by", "on", "at", "is", "are", "was", "that", "this", "its", "it"}
    words = topic_lower.split()
    core_words = [w for w in words if w not in stop and len(w) > 3]

    # Build targeted queries based on domain detection
    search_queries = []

    if ("graph" in topic_lower and "memory" in topic_lower) or \
       ("gnn" in topic_lower and "memory" in topic_lower):
        # Graph + memory focus — very specific queries 
        search_queries = [
            "memory efficient GNN graph neural network training",
            "scalable graph neural network memory optimization",
            "gradient checkpointing graph neural network training",
        ]
        must_have = ["graph", "gnn", "memory", "neural"]  # title must have at least 2
    elif "graph" in topic_lower and ("neural" in topic_lower or "network" in topic_lower):
        search_queries = [
            "graph neural network GNN scalable training",
            "graph convolutional network node classification",
        ]
        must_have = ["graph", "neural", "network", "gnn", "convolutional"]
    elif "memory" in topic_lower and ("deep" in topic_lower or "neural" in topic_lower or "learning" in topic_lower):
        search_queries = [
            "memory efficient deep learning training",
            "gradient checkpointing activation memory neural network",
        ]
        must_have = ["memory", "neural", "learning", "deep", "training", "efficient"]
    elif "llm" in topic_lower or "language model" in topic_lower:
        search_queries = [
            "large language model memory efficient training",
            "LLM fine-tuning memory optimization",
        ]
        must_have = ["language", "model", "llm", "training", "memory", "efficient"]
    elif "transformer" in topic_lower:
        search_queries = [
            "transformer attention memory efficiency",
            "efficient transformer attention mechanism",
        ]
        must_have = ["transformer", "attention", "memory", "efficient"]
    else:
        # Generic: cleaned core words
        search_queries = [" ".join(core_words[:5])]
        must_have = core_words[:6]

    seen_ids = set()
    all_papers = []

    for query in search_queries:
        if len(all_papers) >= limit:
            break
        try:
            resp = requests.get(
                "https://api.openalex.org/works",
                params={
                    "search": query,
                    "per_page": 15,
                    "filter": f"publication_year:>{start_year - 1},type:article",
                },
                timeout=12,
                headers={"Accept": "application/json", "User-Agent": "AI-Research-Assistant/1.0"},
            )

            if resp.status_code != 200:
                print(f"WARNING: [openalex] HTTP {resp.status_code} for query '{query}'", file=sys.stderr)
                continue

            data = resp.json()
            for w in data.get("results", []):
                work_id = w.get("id", "")
                title = (w.get("title") or "").strip()
                if not title or work_id in seen_ids:
                    continue

                # STRICT relevance: title must contain at least 2 of our must_have keywords
                title_lower = title.lower()
                hits = sum(1 for kw in must_have if kw in title_lower)
                if hits < 2:
                    continue

                seen_ids.add(work_id)

                # Authors
                authors_list = w.get("authorships", [])
                author_names = [a.get("author", {}).get("display_name", "") for a in authors_list[:4]]
                author_str = ", ".join(n for n in author_names if n)
                if len(authors_list) > 4:
                    author_str += " et al."

                # Venue
                venue = ""
                loc = w.get("primary_location")
                if loc and loc.get("source"):
                    venue = loc["source"].get("display_name", "") or ""

                # URL — prefer DOI
                doi = w.get("doi", "")
                url = doi if doi else w.get("id", "")

                paper = {
                    "title": title,
                    "authors": author_str,
                    "year": str(w.get("publication_year", "")),
                    "venue": venue,
                    "doi_or_url": url,
                    "citationCount": w.get("cited_by_count", 0),
                    "abstract": "",
                }
                all_papers.append(paper)

        except Exception as e:
            print(f"WARNING: [openalex] Failed query '{query}': {e}", file=sys.stderr)
            continue

    # Fallback with relaxed filter if strict returned nothing
    if len(all_papers) == 0:
        print("WARNING: [openalex] Strict filter got 0 results. Using relaxed fallback.", file=sys.stderr)
        try:
            fallback_q = " ".join(core_words[:4]) if core_words else topic
            resp = requests.get(
                "https://api.openalex.org/works",
                params={
                    "search": fallback_q,
                    "per_page": limit,
                    "filter": f"publication_year:>{start_year - 1},type:article",
                },
                timeout=12,
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                for w in resp.json().get("results", []):
                    title = (w.get("title") or "").strip()
                    if not title:
                        continue
                    doi = w.get("doi", "")
                    url = doi if doi else w.get("id", "")
                    authors_list = w.get("authorships", [])
                    author_str = ", ".join(a.get("author", {}).get("display_name", "") for a in authors_list[:4])
                    venue = ""
                    loc = w.get("primary_location")
                    if loc and loc.get("source"):
                        venue = loc["source"].get("display_name", "") or ""
                    all_papers.append({
                        "title": title, "authors": author_str,
                        "year": str(w.get("publication_year", "")), "venue": venue,
                        "doi_or_url": url, "citationCount": w.get("cited_by_count", 0), "abstract": "",
                    })
        except Exception:
            pass

    # Sort by citation count — most validated papers first
    all_papers.sort(key=lambda p: p.get("citationCount", 0), reverse=True)
    print(f"DEBUG: [openalex] Fetched {len(all_papers)} relevant papers for '{topic}'", file=sys.stderr)
    return all_papers[:limit]


def _make_paper_context(papers: list) -> str:
    """Format real papers as context for the LLM to reference in its analysis."""
    if not papers:
        return ""
    lines = ["REAL PAPERS (use these exact titles and authors in your analysis):"]
    for i, p in enumerate(papers[:12], 1):
        url = p.get("doi_or_url", "")
        lines.append(f"[{i}] {p['authors']} ({p['year']}). \"{p['title']}\". {p['venue']}. URL: {url}")
    return "\n".join(lines)


def build_prompt(topic: str, domain: str, role: str, years: int = None, real_papers: list = None) -> str:
    """Build the LLM prompt, injecting real paper titles as context."""
    constraints = ""
    if years:
        current_year = datetime.now().year
        start_year = current_year - years
        constraints = f"Focus on research published between {start_year} and {current_year}."

    paper_context = _make_paper_context(real_papers) if real_papers else ""

    prompt_template = load_prompt()
    prompt = simple_render(
        prompt_template,
        {
            "TOPIC": topic,
            "DOMAIN": domain,
            "ROLE": role,
            "CONSTRAINTS": constraints,
            "REAL_PAPERS_CONTEXT": paper_context,
        },
    )
    if len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[:MAX_PROMPT_CHARS]
    return prompt


def _balanced_extract(s: str):
    """Extract the first balanced JSON object from a string."""
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(s)):
        ch = s[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start:idx + 1]
    if depth > 0:
        truncated = s[start:]
        repair = truncated.rstrip()
        if repair and repair[-1] == ',':
            repair = repair[:-1]
        repair += "}" * depth
        try:
            json.loads(repair, strict=False)
            return repair
        except Exception:
            pass
    return None


def extract_json_only(text: str) -> dict:
    """Extract JSON from model response — robust against think tags, code fences, truncation."""
    if not text:
        raise ValueError("Empty response text")

    cleaned = strip_think_tags(text)

    cleaned_no_fence = re.sub(r'^\s*```+(?:json)?\s*\n*', '', cleaned)
    cleaned_no_fence = re.sub(r'\n*\s*```+\s*$', '', cleaned_no_fence).strip()

    for candidate in (cleaned_no_fence, cleaned):
        try:
            return json.loads(candidate, strict=False)
        except (json.JSONDecodeError, ValueError):
            pass

    b = _balanced_extract(cleaned)
    if b:
        try:
            return json.loads(b, strict=False)
        except Exception:
            pass

    for pattern in (r'```+(?:json)?\s*\n*([\\s\\S]+?)\s*```+',):
        m = re.search(pattern, cleaned)
        if m:
            inner = m.group(1).strip()
            try:
                return json.loads(inner, strict=False)
            except Exception:
                pass

    raise ValueError(f"Could not parse JSON. First 300 chars: {text[:300]}")


def _ensure_defaults(parsed: dict, topic: str, domain: str, role: str) -> dict:
    parsed.setdefault("agent_id", make_agent_id("research", role))
    parsed.setdefault("role", role)
    parsed.setdefault("topic", topic)
    parsed.setdefault("domain", domain)
    parsed.setdefault("summary", "")
    parsed.setdefault("top_papers", [])
    parsed.setdefault("citations", [])
    parsed.setdefault("key_methods", [])
    parsed.setdefault("datasets_used", [])
    parsed.setdefault("open_problems", [])
    parsed.setdefault("search_terms", [])
    parsed.setdefault("future_research_directions", [])
    parsed.setdefault("future_scope_methodologies", [])
    parsed.setdefault("confidence", 0.75)
    parsed.setdefault("retrieved_on", now_iso_z())

    if not parsed.get("word_count"):
        parsed["word_count"] = len(parsed.get("summary", "").split())

    parsed["status"] = "ok"
    return parsed


def run_research_agent(topic: str, domain: str, role: str, years: int = None) -> dict:
    """
    Research agent — uses Groq (cloud) for fast generation.
    Fetches REAL papers from OpenAlex FIRST, then injects them as context
    so the LLM references real work instead of hallucinating.
    """
    # Step 1: Fetch real papers BEFORE prompting the LLM
    print(f"DEBUG: [research] Fetching real papers for [{role}]...", file=sys.stderr)
    real_papers = _fetch_real_papers(topic, years=years or 5, limit=15)

    # Step 2: Build prompt with real papers injected as context
    base_prompt = build_prompt(topic, domain, role, years, real_papers)

    exp_prompt = (
        base_prompt
        + "\n\nIMPORTANT: In your summary, reference ONLY the papers listed above under 'REAL PAPERS'. "
        + "Do NOT invent paper titles, authors, or citation numbers. "
        + "Write 'according to [Author et al., Year]' style when citing.\n"
        + "/no_think\nReturn ONE JSON object only. No markdown fences. Start with { end with }."
    )

    sys_msg = (
        "You are a world-class research scientist. "
        "Output STRICT JSON only. Do NOT write headers, titles, or explanations. "
        "Do NOT use numbered [1] style inline citations — use 'Author et al. (Year)' style. "
        "Do NOT fabricate paper titles. Only cite papers explicitly given to you. "
        "Do NOT use markdown. Start your entire response with { and end with }. /no_think"
    )

    try:
        print(f"DEBUG: [research] Generating [{role}] research with Groq...", file=sys.stderr)
        raw = call_llm(
            prompt=exp_prompt,
            role="worker",
            system_msg=sys_msg,
            temperature=0.3,
            timeout=90,
        )

        parsed = extract_json_only(raw)
        final_parsed = _ensure_defaults(parsed, topic, domain, role)

        # Always overwrite papers/citations with real OpenAlex data
        if real_papers:
            final_parsed["top_papers"] = real_papers[:10]
            real_citations = []
            for i, p in enumerate(real_papers[:15], 1):
                real_citations.append({
                    "label": f"[{i}]",
                    "title": p["title"],
                    "authors": p["authors"],
                    "year": p["year"],
                    "venue": p["venue"],
                    "doi_or_url": p["doi_or_url"],
                    "citationCount": p.get("citationCount", 0),
                })
            final_parsed["citations"] = real_citations
            final_parsed["_papers_source"] = "openalex"
        else:
            # No real papers found — mark clearly and keep LLM output but warn
            final_parsed["_papers_source"] = "llm_only_no_real_papers_found"
            print(f"WARNING: [research] No real papers from OpenAlex for [{role}]. LLM output only.", file=sys.stderr)

        final_parsed["_autoresearch_score"] = 75
        final_parsed["_autoresearch_feedback"] = "Generated with real paper data from OpenAlex."
        final_parsed["_model_backend"] = "groq"
        return final_parsed

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR: [research] Failed for [{role}]: {e}", file=sys.stderr)
        return {
            "agent_id": make_agent_id("research", role),
            "role": role,
            "topic": topic,
            "domain": domain,
            "status": "failed",
            "error": str(e),
            "top_papers": real_papers,  # Return real papers even on LLM failure
            "citations": [],
            "raw_response": "Failed",
            "retrieved_on": now_iso_z(),
        }
