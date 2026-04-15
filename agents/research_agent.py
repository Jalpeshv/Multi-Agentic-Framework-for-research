# agents/research_agent.py
"""
Research Agent — Clean Architecture.
  • Uses Groq to FIRST generate the best search terms for the topic
  • Then fetches REAL papers from OpenAlex using those terms
  • Then generates PhD-level summary (pure analysis, NO methodology)

Each role (historical / state_of_the_art / ongoing_emerging) produces only
a focused summary + paper list. Methodology is handled by a dedicated agent.
"""

import os
import sys
import json
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

MAX_PROMPT_CHARS = 8000


def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        return "SYSTEM: Output strict JSON only."
    return PROMPT_PATH.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────
#  STEP 0: LLM-assisted query generation
# ─────────────────────────────────────────────────────────────

def _get_search_queries(topic: str, domain: str) -> list[str]:
    """
    Use a fast Groq call to generate 5 targeted academic search queries for OpenAlex.
    Returns queries ordered from most-specific to fallback-broad.
    """
    prompt = (
        f"You are helping find academic papers on: \"{topic}\" (domain: {domain}).\n\n"
        f"Generate 5 OpenAlex search queries that will find REAL published research papers "
        f"specifically about the core technical concepts in this topic.\n\n"
        f"Rules:\n"
        f"- Use precise technical CS/AI vocabulary (e.g. 'knowledge graph embedding', 'GNN training', 'graph DBMS')\n"
        f"- First 2 queries: most specific (5-7 keyword terms)\n"
        f"- Next 2 queries: broader but topically accurate (3-5 terms)\n"
        f"- Last query: very broad fallback (2-3 key technical nouns)\n"
        f"- Do NOT use vague terms like 'study', 'research', 'analysis'\n"
        f"- Focus on: algorithms, systems, architectures, benchmarks relevant to the topic\n\n"
        f"Return ONLY a JSON array of 5 strings.\n"
        f"Example: [\"knowledge graph embedding scalable training\", \"graph store SPARQL query optimization\", "
        f"\"graph database indexing RDF\", \"knowledge graph neural network\", \"graph embedding\"]\n"
        f"/no_think"
    )
    try:
        raw = call_groq(
            prompt=prompt,
            system_msg="Output ONLY a valid JSON array of 5 strings. No explanation. No markdown.",
            model="llama-3.1-8b-instant",
            temperature=0.1,
            timeout=15,
        )
        cleaned = strip_think_tags(raw)
        m = re.search(r'\[.*?\]', cleaned, re.DOTALL)
        if m:
            queries = json.loads(m.group(0))
            if isinstance(queries, list) and len(queries) >= 1:
                return [q for q in queries if isinstance(q, str) and len(q) > 4][:5]
    except Exception as e:
        print(f"WARNING: [search-queries] LLM query gen failed: {e}", file=sys.stderr)

    # Fallback: extract meaningful words from topic
    stop = {"through", "using", "with", "the", "a", "an", "of", "for", "in", "and", "or", "to",
            "by", "on", "at", "is", "are", "was", "that", "this", "handling", "context"}
    words = [w for w in topic.lower().split() if w not in stop and len(w) > 3]
    return [
        " ".join(words[:5]),
        " ".join(words[:3]),
        f"{domain} {' '.join(words[:2])}",
    ]


def _is_likely_off_topic(title: str, domain: str) -> bool:
    """
    Heuristic: if a paper title looks like it belongs to a completely different
    scientific domain, skip it. Prevents bioinformatics/particle physics/medical papers
    from polluting CS results.
    """
    title_lower = title.lower()
    # Domain-specific noise patterns to exclude for CS/AI topics
    if domain.lower() in ("computer science", "ai & machine learning", "artificial intelligence", "machine learning"):
        noise_patterns = [
            "protein", "genome", "dna", "rna", "cell", "cancer", "tumor",
            "drug", "clinical", "patient", "medical", "covid", "vaccine",
            "particle physics", "quantum gravity", "galaxy", "astronomy",
            "earthquake", "seismic", "weather", "climate", "wind speed",
            "slam3", "visual-inertial", "3d scene", "speech recognition toolkit",
            "structure building and analysis",  # ChimeraX-style
        ]
        for pattern in noise_patterns:
            if pattern in title_lower:
                return True
    return False


# ─────────────────────────────────────────────────────────────
#  STEP 1: OpenAlex paper fetch
# ─────────────────────────────────────────────────────────────

def _fetch_real_papers(topic: str, domain: str, years: int = 5, limit: int = 15) -> list:
    """
    Fetch REAL papers from OpenAlex using LLM-optimized search queries.
    Filters out off-topic papers using domain-aware heuristics.
    """
    import requests

    current_year = datetime.now().year
    start_year = current_year - (years if years else 5)

    # Get LLM-optimized search queries
    search_queries = _get_search_queries(topic, domain)
    print(f"DEBUG: [openalex] Queries: {search_queries}", file=sys.stderr)

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
                    "per_page": 10,
                    "filter": f"publication_year:>{start_year - 1},type:article",
                },
                timeout=12,
                headers={"Accept": "application/json", "User-Agent": "AI-Research-Assistant/1.0"},
            )

            if resp.status_code != 200:
                print(f"WARNING: [openalex] HTTP {resp.status_code}", file=sys.stderr)
                continue

            for w in resp.json().get("results", []):
                work_id = w.get("id", "")
                title = (w.get("title") or "").strip()
                if not title or work_id in seen_ids:
                    continue
                seen_ids.add(work_id)

                # Skip off-topic papers (bioinformatics, physics, medical for CS topics)
                if _is_likely_off_topic(title, domain):
                    print(f"DEBUG: [openalex] Skipping off-topic: {title[:50]}", file=sys.stderr)
                    continue

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

                doi = w.get("doi", "")
                url = doi if doi else w.get("id", "")

                all_papers.append({
                    "title": title,
                    "authors": author_str,
                    "year": str(w.get("publication_year", "")),
                    "venue": venue,
                    "doi_or_url": url,
                    "citationCount": w.get("cited_by_count", 0),
                    "abstract": "",
                })

        except Exception as e:
            print(f"WARNING: [openalex] Failed: {e}", file=sys.stderr)
            continue

    # Sort by citation count
    all_papers.sort(key=lambda p: p.get("citationCount", 0), reverse=True)
    print(f"DEBUG: [openalex] Fetched {len(all_papers)} relevant papers for '{topic}'", file=sys.stderr)
    return all_papers[:limit]


# ─────────────────────────────────────────────────────────────
#  STEP 2: Context string for LLM
# ─────────────────────────────────────────────────────────────

def _make_paper_context(papers: list) -> str:
    """Format real papers as context for the LLM. The LLM MUST only cite these."""
    if not papers:
        return "(No papers retrieved from OpenAlex for this query.)"
    lines = ["VERIFIED REAL PAPERS — cite ONLY these in your summary:"]
    for i, p in enumerate(papers[:12], 1):
        url = p.get("doi_or_url", "N/A")
        lines.append(
            f"[{i}] {p.get('authors','Unknown')} ({p.get('year','?')}). "
            f"\"{p['title']}\". {p.get('venue','')}. {url}"
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  STEP 3: Prompt builder
# ─────────────────────────────────────────────────────────────

def build_prompt(topic: str, domain: str, role: str, years: int = None, real_papers: list = None) -> str:
    constraints = ""
    if years:
        cy = datetime.now().year
        constraints = f"Focus on research published between {cy - years} and {cy}."

    paper_context = _make_paper_context(real_papers) if real_papers else ""

    prompt = simple_render(
        load_prompt(),
        {
            "TOPIC": topic,
            "DOMAIN": domain,
            "ROLE": role,
            "CONSTRAINTS": constraints,
            "REAL_PAPERS_CONTEXT": paper_context,
        },
    )
    return prompt[:MAX_PROMPT_CHARS]


# ─────────────────────────────────────────────────────────────
#  JSON helpers
# ─────────────────────────────────────────────────────────────

def _balanced_extract(s: str):
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
        repair = s[start:].rstrip().rstrip(",") + "}" * depth
        try:
            json.loads(repair, strict=False)
            return repair
        except Exception:
            pass
    return None


def extract_json_only(text: str) -> dict:
    if not text:
        raise ValueError("Empty response")
    cleaned = strip_think_tags(text)
    for candidate in [
        re.sub(r'^\s*```+(?:json)?\s*\n*', '', re.sub(r'\n*\s*```+\s*$', '', cleaned)).strip(),
        cleaned,
    ]:
        try:
            return json.loads(candidate, strict=False)
        except Exception:
            pass
    b = _balanced_extract(cleaned)
    if b:
        try:
            return json.loads(b, strict=False)
        except Exception:
            pass
    raise ValueError(f"Cannot parse JSON. First 200 chars: {text[:200]}")


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
    parsed.setdefault("confidence", 0.80)
    parsed.setdefault("retrieved_on", now_iso_z())
    if not parsed.get("word_count"):
        parsed["word_count"] = len(parsed.get("summary", "").split())
    parsed["status"] = "ok"
    return parsed


# ─────────────────────────────────────────────────────────────
#  MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────

def run_research_agent(topic: str, domain: str, role: str, years: int = None) -> dict:
    """
    Research agent:
    1. Uses Groq to generate optimal OpenAlex search queries
    2. Fetches real verified papers from OpenAlex
    3. Injects real papers into LLM prompt
    4. LLM generates a pure academic analysis (NO methodology — that's separate)
    5. Real papers overwrite LLM-hallucinated citations
    """
    # Step 1+2: Get real papers using LLM-optimized queries
    print(f"DEBUG: [research] Fetching real papers for [{role}]...", file=sys.stderr)
    real_papers = _fetch_real_papers(topic, domain, years=years or 5, limit=15)

    # Step 3: Build prompt with real papers as context
    base_prompt = build_prompt(topic, domain, role, years, real_papers)
    exp_prompt = (
        base_prompt
        + "\n\nCRITICAL: Only reference papers from the VERIFIED REAL PAPERS list above. "
        + "Do NOT invent paper titles, authors, or citation numbers. "
        + "Use 'Author et al. (Year)' style when citing.\n"
        + "/no_think Return ONE JSON object only. Start with { end with }."
    )

    sys_msg = (
        "You are a world-class research scientist producing a PhD-level analysis. "
        "Output STRICT JSON only. No markdown. No explanation. "
        "ONLY cite papers explicitly given to you. Never fabricate papers. "
        "Use 'Author et al. (Year)' citation style, NOT [1] numbers. "
        "Start with { and end with }. /no_think"
    )

    try:
        print(f"DEBUG: [research] Generating [{role}] with Groq...", file=sys.stderr)
        raw = call_llm(
            prompt=exp_prompt,
            role="worker",
            system_msg=sys_msg,
            temperature=0.3,
            timeout=90,
        )

        parsed = extract_json_only(raw)
        final = _ensure_defaults(parsed, topic, domain, role)

        # Always overwrite papers+citations with real OpenAlex data
        if real_papers:
            final["top_papers"] = real_papers[:10]
            final["citations"] = [
                {
                    "label": f"[{i}]",
                    "title": p["title"],
                    "authors": p["authors"],
                    "year": p["year"],
                    "venue": p["venue"],
                    "doi_or_url": p["doi_or_url"],
                    "citationCount": p.get("citationCount", 0),
                }
                for i, p in enumerate(real_papers[:15], 1)
            ]
            final["_papers_source"] = "openalex"
        else:
            final["_papers_source"] = "llm_only"

        final["_autoresearch_score"] = 75
        final["_autoresearch_feedback"] = "Generated with real paper data from OpenAlex."
        final["_model_backend"] = "groq"
        return final

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR: [research] Failed [{role}]: {e}", file=sys.stderr)
        return {
            "agent_id": make_agent_id("research", role),
            "role": role,
            "topic": topic,
            "domain": domain,
            "status": "failed",
            "error": str(e),
            "top_papers": real_papers,
            "citations": [
                {"label": f"[{i}]", "title": p["title"], "authors": p["authors"],
                 "year": p["year"], "venue": p["venue"], "doi_or_url": p["doi_or_url"],
                 "citationCount": p.get("citationCount", 0)}
                for i, p in enumerate(real_papers[:15], 1)
            ],
            "retrieved_on": now_iso_z(),
        }
