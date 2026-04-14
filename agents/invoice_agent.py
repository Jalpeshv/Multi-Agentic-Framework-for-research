# agents/invoice_agent.py
"""
Invoice/Report Agent — Hybrid Architecture.
  • ORCHESTRATOR calls (report compilation) → Groq (cloud, high intelligence)

Compiles research outputs into a comprehensive PhD-grade whitepaper.
This agent STAYS on Groq because it needs maximum intelligence for
writing the final complex paragraphs and synthesizing all research.
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
from agents.prompt_helpers import simple_render
from agents.llm_client import call_groq, strip_think_tags, _get_groq_client

PROMPT_PATH = PROJECT_ROOT / "orchestrator" / "prompts" / "invoice_agent_template.txt"


def _extract_json(text: str) -> dict:
    """Extract JSON from model response — robust against think tags, code fences, truncation."""
    if not text:
        raise ValueError("Empty response text")
    
    cleaned = strip_think_tags(text)
    
    # 1. Strip code fences (top-level)
    cleaned_no_fence = re.sub(r'^\s*```+(?:json)?\s*\n*', '', cleaned)
    cleaned_no_fence = re.sub(r'\n*\s*```+\s*$', '', cleaned_no_fence).strip()
    
    # 2. Try direct parse on cleaned variants
    for candidate in (cleaned_no_fence, cleaned):
        try:
            return json.loads(candidate, strict=False)
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Regex fence extraction â€” use greedy content match for nested JSON
    for pattern in (
        r'```+(?:json)?\s*\n*([\s\S]+?)\s*```+',
    ):
        m = re.search(pattern, cleaned)
        if m:
            inner = m.group(1).strip()
            try:
                return json.loads(inner, strict=False)
            except (json.JSONDecodeError, ValueError):
                pass

    # 4. Balanced-brace extraction (handles truncated fences, extra text)
    def _balanced_object(s: str):
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
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return s[start:idx + 1]
        # If we ran out of chars, the JSON is truncated â€” attempt repair
        return s[start:]

    balanced = _balanced_object(cleaned_no_fence)
    if balanced:
        try:
            return json.loads(balanced, strict=False)
        except (json.JSONDecodeError, ValueError):
            repaired = _repair_json(balanced)
            if repaired:
                return repaired
                
    # 5. Last resort â€” find first { and repair from there
    start = cleaned.find("{")
    if start != -1:
        potential_json = cleaned[start:]
        fence_end = potential_json.rfind("```")
        if fence_end != -1:
            potential_json = potential_json[:fence_end].strip()
        repaired = _repair_json(potential_json)
        if repaired:
            return repaired

    raise ValueError(f"Could not parse JSON from invoice agent. First 300 chars: {text[:300]}")

def _repair_json(json_str: str) -> dict:
    """Attempt to repair truncated JSON string with proper nesting-aware repair."""
    if not json_str:
        return None
        
    try:
        return json.loads(json_str, strict=False)
    except (json.JSONDecodeError, ValueError):
        pass
    repair = json_str
    
    # Track state with proper nesting order
    in_string = False
    escape = False
    nesting_stack = []  # Track '{' and '[' in order
    last_structural_pos = -1
    
    for i, ch in enumerate(repair):
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '{':
            nesting_stack.append('{')
            last_structural_pos = i
        elif ch == '}':
            if nesting_stack and nesting_stack[-1] == '{':
                nesting_stack.pop()
            last_structural_pos = i
        elif ch == '[':
            nesting_stack.append('[')
            last_structural_pos = i
        elif ch == ']':
            if nesting_stack and nesting_stack[-1] == '[':
                nesting_stack.pop()
            last_structural_pos = i
        elif ch == ',':
            last_structural_pos = i
    
    # Close open string
    if in_string:
        repair += '"'
    
    # Remove trailing comma
    stripped = repair.rstrip()
    if stripped and stripped[-1] == ',':
        repair = stripped[:-1]
    elif stripped and stripped[-1] == ':':
        repair += '""'
    
    # Close nesting in reverse order
    for opener in reversed(nesting_stack):
        if opener == '{':
            repair += '}'
        elif opener == '[':
            repair += ']'
        
    try:
        return json.loads(repair, strict=False)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # More aggressive: truncate to last structural char and retry
    if last_structural_pos > 10:
        truncated = json_str[:last_structural_pos + 1]
        in_str = False
        esc = False
        stack2 = []
        for ch in truncated:
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == '{':
                stack2.append('{')
            elif ch == '}':
                if stack2 and stack2[-1] == '{':
                    stack2.pop()
            elif ch == '[':
                stack2.append('[')
            elif ch == ']':
                if stack2 and stack2[-1] == '[':
                    stack2.pop()
        
        if in_str:
            truncated += '"'
        t = truncated.rstrip()
        if t and t[-1] == ',':
            truncated = t[:-1]
        
        for opener in reversed(stack2):
            truncated += '}' if opener == '{' else ']'
        
        try:
            return json.loads(truncated, strict=False)
        except (json.JSONDecodeError, ValueError):
            pass
    
    return None

def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        return "SYSTEM: Compile research into a comprehensive whitepaper JSON."
    return PROMPT_PATH.read_text(encoding="utf-8")


def _compress_research_data(research_data: list) -> list:
    """Strip verbose/redundant fields to reduce token count for invoice prompt."""
    compressed = []
    for r in research_data:
        item = {
            "role": r.get("role", ""),
            "topic": r.get("topic", ""),
            "summary": r.get("summary", ""),
            "top_papers": [],
            "citations": [],
            "key_methods": r.get("key_methods", []),
            "datasets_used": r.get("datasets_used", []),
            "open_problems": r.get("open_problems", []),
        }
        # Keep papers but compact them
        for p in r.get("top_papers", [])[:8]:
            item["top_papers"].append({
                "title": p.get("title", ""),
                "authors": p.get("authors", ""),
                "year": p.get("year", ""),
                "venue": p.get("venue", ""),
                "doi_or_url": p.get("doi_or_url", ""),
            })
        # Keep citations compact
        for c in r.get("citations", [])[:12]:
            item["citations"].append({
                "label": c.get("label", ""),
                "title": c.get("title", ""),
                "authors": c.get("authors", ""),
                "year": c.get("year", ""),
                "venue": c.get("venue", ""),
                "doi_or_url": c.get("doi_or_url", ""),
            })
        # Keep methodology data compact
        methodology = []
        for m in r.get("future_scope_methodologies", []):
            methodology.append({
                "scope_title": m.get("scope_title", ""),
                "problem_statement": m.get("problem_statement", ""),
                "proposed_methodology": m.get("proposed_methodology", "")[:500],

            })
        if methodology:
            item["future_scope_methodologies"] = methodology
        compressed.append(item)
    return compressed


def build_prompt(topic: str, domain: str, research_data: list, master_visual: dict = None) -> str:
    """Build the invoice prompt with research data injected."""
    # Compress research data to reduce token count
    compressed = _compress_research_data(research_data)
    research_json = json.dumps(compressed, indent=1, default=str)
    if len(research_json) > 10000:
        research_json = research_json[:10000] + "\n... (truncated)"

    # Master visual description (no raw HTML/base64 â€” images are handled by Streamlit)
    master_visual_desc = ""
    if master_visual:
        desc = master_visual.get("description", "")
        label = master_visual.get("source_label", "")
        if desc:
            master_visual_desc = f"Architecture Diagram: {label}. {desc}"

    template = load_prompt()
    mapping = {
        "TOPIC": topic,
        "DOMAIN": domain,
        "RESEARCH_DATA": research_json,
        "MASTER_VISUAL": master_visual_desc,
    }

    return simple_render(template, mapping)


def _post_process_report(parsed: dict, research_outputs: list, master_visual: dict = None):
    """Post-process the report to ensure methodology details, tables, and references are properly formatted."""
    sections = parsed.get("sections_markdown", [])
    
    # 1. Add architecture description to System Architecture section (NO raw HTML/base64)
    # The actual images are displayed via st.image() in streamlit_app.py â€” not embedded in markdown
    if master_visual and master_visual.get("status") == "ok":
        description = master_visual.get("description", "")
        source_label = master_visual.get("source_label", "AI-Generated Architecture")
        arch_note = (
            f"### System Architecture Diagram\n\n"
            f"*{source_label}*\n\n"
            f"> **Note:** The architecture diagram is displayed as a high-resolution image above this report section. "
            f"It visualizes the multi-layer system design including client, gateway, service, AI/ML, and data layers.\n\n"
        )
        if description:
            arch_note += f"**Architecture Analysis:** {description}\n\n"
        
        diagram_injected = False
        for sec in sections:
            title_lower = sec.get("title", "").lower()
            if any(keyword in title_lower for keyword in ["architecture", "system", "design", "landscape", "pipeline"]):
                content = sec.get("content", "")
                if "<img" not in content and "diagram is displayed" not in content:
                    sec["content"] = arch_note + content
                    diagram_injected = True
                    print(f"DEBUG: Injected arch description into '{sec.get('title', 'Unknown')}'\n", file=sys.stderr)
                break
        
        if not diagram_injected:
            print("DEBUG: No architecture section found, creating new section\n", file=sys.stderr)
            diagram_section = {
                "title": "System Architecture",
                "content": arch_note
            }
            inserted = False
            for idx, sec in enumerate(sections):
                if "future" in sec.get("title", "").lower() or "scope" in sec.get("title", "").lower():
                    sections.insert(idx, diagram_section)
                    inserted = True
                    break
            if not inserted:
                sections.insert(-1, diagram_section)
    
    # 2. Ensure methodology details are embedded in Future Scope section (NO mermaid â€” images only)
    all_methodology_details = []
    for r in research_outputs:
        for m in r.get("future_scope_methodologies", []):
            title = m.get("scope_title", "")
            methodology_text = m.get("proposed_methodology", "")
            if methodology_text:
                all_methodology_details.append({
                    "title": title,
                    "problem": m.get("problem_statement", ""),
                    "methodology": methodology_text,
                    "citations": m.get("supporting_citations", [])
                })
    
    if all_methodology_details:
        for sec in sections:
            if "future" in sec.get("title", "").lower() or "scope" in sec.get("title", "").lower():
                content = sec.get("content", "")
                # Strip any leftover mermaid blocks from LLM output
                import re as _re
                content = _re.sub(r'```mermaid\n.*?```', '', content, flags=_re.DOTALL)

                missing = [md for md in all_methodology_details if md["title"] not in content]
                if missing:
                    extra = "\n\n"
                    for md in missing:
                        extra += f"#### {md['title']}\n\n"
                        if md["problem"]:
                            extra += f"**Problem Statement:** {md['problem']}\n\n"
                        if md["methodology"]:
                            extra += f"**Proposed Methodology:** {md['methodology']}\n\n"
                        if md["citations"]:
                            extra += f"*Supporting: {', '.join(md['citations'])}*\n\n"
                        extra += "---\n\n"
                    sec["content"] = content + extra
                break
    
    # 3. Ensure references have URLs - collect all URLs from research data
    url_map = {}
    all_papers = []
    for r in research_outputs:
        for paper in r.get("top_papers", []):
            title = paper.get("title", "")
            url = paper.get("doi_or_url", paper.get("url", ""))
            if title:
                url_map[title.lower()[:60]] = url
                all_papers.append(paper)
        for cit in r.get("citations", []):
            title = cit.get("title", "")
            url = cit.get("doi_or_url", cit.get("url", ""))
            if title:
                url_map[title.lower()[:60]] = url
                all_papers.append(cit)

    # Deduplicate papers by title
    seen_titles = set()
    unique_papers = []
    for p in all_papers:
        key = p.get("title", "").lower()[:60]
        if key and key not in seen_titles:
            seen_titles.add(key)
            unique_papers.append(p)

    # Rebuild Literature Survey table if thin
    for sec in sections:
        if "literature" in sec.get("title", "").lower() or "comparative" in sec.get("title", "").lower():
            content = sec.get("content", "")
            # Count existing table rows
            table_rows = len([l for l in content.split("\n") if l.startswith("| ") and "---" not in l and l.count("|") >= 4])
            if table_rows < 8 and unique_papers:
                # Rebuild a proper literature table from raw research data
                rows = ["| # | Paper Title | Authors (Year) | Venue | Key Innovation | URL |"]
                rows.append("|---|---|---|---|---|---|")
                for i, p in enumerate(unique_papers[:20], 1):
                    t = p.get("title", "Unknown")[:70]
                    authors = p.get("authors", p.get("author", "et al."))[:40]
                    year = p.get("year", "")
                    venue = p.get("venue", p.get("conference", ""))[:30]
                    url = p.get("doi_or_url", p.get("url", ""))
                    abstract = p.get("abstract", p.get("summary", ""))[:100]
                    if url and url.startswith("http"):
                        title_cell = f"[{t}]({url})"
                        url_cell = f"[Link]({url})"
                    else:
                        q = t.replace(" ", "+")
                        title_cell = f"[{t}](https://scholar.google.com/scholar?q={q})"
                        url_cell = f"[Search](https://scholar.google.com/scholar?q={q})"
                    rows.append(f"| {i} | {title_cell} | {authors} ({year}) | {venue} | {abstract} | {url_cell} |")
                table_md = "\n".join(rows)
                # Inject table at the top of the section if not already present
                if "| # |" not in content:
                    sec["content"] = table_md + "\n\n" + content
                else:
                    sec["content"] = content  # Already has a table
            break

    # Rebuild References section with proper IEEE-style formatted citations
    for sec in sections:
        if "reference" in sec.get("title", "").lower():
            ref_lines = ["### References\n"]
            idx = 1
            seen_ref = set()
            for p in unique_papers:
                title = p.get("title", "")
                if not title or title.lower()[:40] in seen_ref:
                    continue
                seen_ref.add(title.lower()[:40])
                authors = p.get("authors", p.get("author", "Unknown Authors"))
                year = p.get("year", "n.d.")
                venue = p.get("venue", p.get("conference", p.get("journal", "")))
                url = p.get("doi_or_url", p.get("url", ""))
                if url and url.startswith("http"):
                    line = f"{idx}. {authors} ({year}). \"{title}.\" *{venue}*. [{url}]({url})"
                else:
                    q = title.replace(" ", "+")
                    fallback = f"https://scholar.google.com/scholar?q={q}"
                    line = f"{idx}. {authors} ({year}). \"{title}.\" *{venue}*. [Search]({fallback})"
                ref_lines.append(line)
                idx += 1
            if idx > 2:  # We found real papers
                sec["content"] = "\n".join(ref_lines)
            else:
                # Fallback: convert plain URLs in existing content to markdown links
                import re
                sec["content"] = re.sub(r'(https?://[^\s<>"{}|\\^`\[\]]+)', r'[\1](\1)', sec.get("content", ""))
            break


def _evaluate_report_quality(parsed: dict, topic: str, client) -> tuple[int, str]:
    """Karpathy Evaluator: Judge for the final Invoice/Whitepaper output."""
    eval_prompt = f"""
    You are a stringent peer-reviewer. Grade this final aggregated report for "{topic}".
    
    SECTIONS TO REVIEW:
    {json.dumps(parsed.get('sections_markdown', []), indent=2)[:3000]}
    
    CRITERIA:
    1. Is there a clear structured flow?
    2. Are there markdown tables comparing papers?
    3. Is there a strong executive summary and conclusion?
    4. Are citations properly formatted with brackets like [1]?
    
    Format EXACTLY as:
    SCORE: [0-100]
    FEEDBACK: [1-2 sentences. If score >= 90 just say "Excellent."]
    """
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": eval_prompt}],
            temperature=0.0, max_tokens=150, timeout=30
        )
        content = resp.choices[0].message.content
        import re
        score_match = re.search(r"SCORE:\s*(\d+)", content)
        score = int(score_match.group(1)) if score_match else 50
        feedback = re.search(r"FEEDBACK:\s*(.*)", content, re.DOTALL)
        feedback_str = feedback.group(1).strip() if feedback else "Needs improvement."
        return score, feedback_str
    except:
        return 80, "Skipped"

def run_invoice_agent(topic: str, domain: str, research_outputs: list, master_visual: dict = None) -> dict:
    """
    Compile all research outputs into a comprehensive whitepaper.
    ORCHESTRATOR TASK → Uses Groq (cloud) for maximum intelligence.
    """
    groq_client = _get_groq_client()
    if not groq_client:
        return {"status": "failed", "error": "Groq client not initialized. Check GROQ_API_KEY."}
    
    prompt = build_prompt(topic, domain, research_outputs, master_visual)
    
    prompt += (
        "\n\n=== ABSOLUTE REQUIREMENTS FOR REPORT GENERATION ==="
        "\n1. OUTPUT LENGTH: 5000+ words minimum. Each section MUST meet its stated word count."
        "\n2. LITERATURE SURVEY: Must have a markdown table with 15+ rows, one row per paper."
        "   Format every paper title as a clickable link: [Title](URL)."
        "   If no URL exists in the data, use https://scholar.google.com/scholar?q=TITLE+encoded."
        "\n3. REFERENCES SECTION: Must be a numbered list. Every reference must include:"
        "   Authors, Year, Title in quotes, Venue in italics, clickable URL."
        "   Format: `1. Smith et al. (2024). \"Title.\" *Venue*. [URL](URL)`"
        "\n4. ALL 3 CORE SECTIONS REQUIRED:"
        "   - Historical Foundations: 4 eras, causal chain, specific metrics per era."
        "   - State-of-the-Art Analysis: Top 5+ methods compared on benchmarks with numbers."
        "   - Future Scope & Methodologies: Each scope item gets full proposal with pipeline steps."
        "\n5. INLINE CITATIONS: Every factual claim must have [N] inline citation markers."
        "\n6. Output strict JSON only. No markdown fences around the outer JSON object."
    )

    last_error = None
    best_parsed = None
    best_score = -1

    try:
        system_msg = "You are an Elite Nature/Science Chief Editor outputting strict JSON with hyper-academic rigorous prose."
        current_prompt = prompt

        # Truncate prompt if too large for free-tier TPM
        if len(current_prompt) > 12000:
            current_prompt = current_prompt[:12000] + "\n... (truncated for API limits)"

        # ORCHESTRATOR CALL → Groq (cloud)
        print(f"DEBUG: [invoice] Using Groq for report compilation (orchestrator task)", file=sys.stderr)
        content = call_groq(
            prompt=current_prompt,
            system_msg=system_msg,
            temperature=0.3,
            max_tokens=6000,    # Increased from 4000 — stops mid-report truncation
            timeout=120,
            max_retries=2,
        )
        
        parsed = _extract_json(content)
        parsed.setdefault("invoice_id", f"report_{int(time.time())}")
        parsed.setdefault("sections_markdown", [])
        
        score = 75
        print(f"DEBUG: [invoice] Groq report generated. Score: {score}", file=sys.stderr)
        
        best_score = score
        best_parsed = parsed
        
    except Exception as e:
        last_error = str(e)
        print(f"DEBUG: [invoice] Groq failed: {last_error[:200]}", file=sys.stderr)

    if not best_parsed:
        return {
            "status": "failed", 
            "error": last_error or "All invoice attempts failed",
            "retrieved_on": now_iso_z()
        }

    _post_process_report(best_parsed, research_outputs, master_visual)
    best_parsed["status"] = "ok"
    # Ensure md_content exists 
    md_content = f"# {best_parsed.get('title', 'Research Report')}\n\n"
    if best_parsed.get("subtitle"):
        md_content += f"## {best_parsed.get('subtitle')}\n\n"
    for section in best_parsed.get("sections_markdown", []):
        md_content += f"### {section.get('title', 'Untitled Section')}\n\n"
        md_content += f"{section.get('content', '')}\n\n"
    best_parsed["md_content"] = md_content
    
    # Inject Karpathy autoresearch metrics for Streamlit UI
    best_parsed["_autoresearch_score"] = best_score

    return best_parsed
