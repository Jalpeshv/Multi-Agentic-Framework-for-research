# app/streamlit_app.py
import streamlit as st
import os
import time
from datetime import datetime
import sys
import traceback
import concurrent.futures
from pathlib import Path
from dotenv import load_dotenv

# --- FIX PYTHON PATH ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- FORCE LOAD .ENV FIRST ---
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path)

# --- IMPORT AGENTS ---
from agents.research_agent import run_research_agent
from agents.invoice_agent import run_invoice_agent
from agents.methodology_agent import run_methodology_agent
from agents.visualizer_agent import run_visualizer_agent
from orchestrator.pipeline_validator import PipelineValidator
import streamlit.components.v1 as components

st.set_page_config(page_title="AI Research Assistant", layout="wide")

# --- SAFE AGENT RUNNER (prevents connection drops on long calls) ---
def _run_agent_safe(fn, *args, timeout_seconds=600, **kwargs):
    """
    Run an agent function in a background thread and POLL for completion.
    
    CRITICAL: We cannot call future.result(timeout=N) because that blocks
    the main thread and prevents Streamlit from processing WebSocket
    ping/pong frames, causing "Connection error" after ~60-120s.
    
    Instead, we poll every 0.5s with time.sleep() which yields control
    back to Streamlit's event loop so WebSocket stays alive.
    
    Returns (result, error_string).
    """
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn, *args, **kwargs)
    
    deadline = time.time() + timeout_seconds
    poll_interval = 0.5  # Check every 500ms — keeps WebSocket alive
    
    while not future.done():
        if time.time() > deadline:
            future.cancel()
            pool.shutdown(wait=False)
            return None, f"Agent timed out after {timeout_seconds}s"
        time.sleep(poll_interval)
    
    pool.shutdown(wait=False)
    
    try:
        result = future.result(timeout=0)  # Already done, just get it
        return result, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

def render_clean_markdown(markdown_text):
    """Render markdown, stripping any leftover mermaid blocks."""
    import re
    if not markdown_text or not markdown_text.strip():
        return
    # Strip any mermaid code blocks that slipped through
    cleaned = re.sub(r'```mermaid\n.*?```', '', markdown_text, flags=re.DOTALL)
    st.markdown(cleaned.strip(), unsafe_allow_html=True)

OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

st.title("🎓 AI Research Assistant")
st.markdown("**Generate comprehensive research reports using multi-agent AI.**")

# Inject Custom CSS for Justified Text and Headings
css_path = PROJECT_ROOT / "app" / "templates" / "custom_styles.html"
if css_path.exists():
    st.markdown(css_path.read_text(encoding="utf-8"), unsafe_allow_html=True)
else:
    st.markdown("""
    <style>
    div.stMarkdown p { text-align: justify; }
    h1, h2, h3 { color: #444; border-bottom: 2px solid #ddd; }
    </style>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.header("Research Inputs")
    topic = st.text_input("Topic", value="", placeholder="e.g. Quantum Error Correction")
    domain = st.selectbox("Domain", ["computer science", "physics", "biology", "economics", "other"])
    if domain == "other": domain = st.text_input("Custom Domain", value="other")
    
    # Years Filter
    years_back = st.slider("Include papers from last X years", min_value=1, max_value=20, value=5)
    
    # System Design Category
    system_category = st.selectbox(
        "System Category",
        [
            "General / Web App",
            "AI & Machine Learning",
            "Fintech & Payments",
            "DevOps & CI/CD Infrastructure",
            "Real-World Case Study",
            "Data Engineering & Big Data",
        ],
        index=0,
        help="Select a system design category to shape the architecture diagrams and research focus."
    )
    
    # Max papers per agent (prevents Groq TPM crash with too many papers)
    max_papers = st.slider("Max Papers per Agent", min_value=3, max_value=8, value=5,
                           help="Limit papers to stay within Groq free-tier token limits. Lower = faster & more reliable.")
    
    st.markdown("---")
    generate_btn = st.button("Start Research Pipeline", type="primary")
    
    if st.button("Clear Cache & Reset"):
        if 'research_outputs' in st.session_state:
            del st.session_state['research_outputs']
        if 'invoice_output' in st.session_state:
            del st.session_state['invoice_output']
        if 'master_visual' in st.session_state:
            del st.session_state['master_visual']
        st.rerun()

# --- MAIN LOGIC ---
if generate_btn or ('research_outputs' in st.session_state and st.session_state['research_outputs']):
    if not topic.strip():
        st.error("Please enter a topic.")
    else:
        # Check cache
        if 'research_outputs' in st.session_state and st.session_state['research_outputs']:
            research_outputs = st.session_state['research_outputs']
            st.info("Loaded Research from Cache (Click 'Clear Cache' to redo)")
        else:
            research_outputs = []
            errors = []
            roles = ["historical", "state_of_the_art", "ongoing_emerging"]
            
            # --- PHASE 1: RESEARCH (ALL 3 AGENTS IN PARALLEL) ---
            st.subheader(f"Researching: {topic}")
            research_bar = st.progress(0)
            status_box = st.status("Running research agents...", expanded=True)
            
            # Launch research agents with 3s stagger to avoid Groq 30 RPM limit
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
            futures = {}
            for i, role in enumerate(roles):
                if i > 0:
                    time.sleep(8)  # Stagger to stay under OpenRouter RPM limit
                f = pool.submit(
                    run_research_agent, topic.strip(), domain.strip(), role, years_back, max_papers
                )
                futures[f] = role
            
            # Collect results as they complete (gracefully handle timeouts)
            completed = 0
            try:
                for future in concurrent.futures.as_completed(futures, timeout=600):
                    role = futures[future]
                    role_name = role.replace("_", " ").title()
                    completed += 1
                    research_bar.progress(completed / len(roles))
                    
                    try:
                        out = future.result(timeout=0)
                        if out and out.get("status") != "failed":
                            score_info = f" (Score: {out.get('_autoresearch_score', 'N/A')}/100)" if '_autoresearch_score' in out else ""
                            status_box.write(f"✅ {role_name} complete.{score_info}")
                            research_outputs.append(out)
                        else:
                            err_msg = out.get('error', 'Unknown') if out else 'Empty'
                            status_box.error(f"❌ {role_name} failed: {err_msg}")
                            errors.append(out or {"status": "failed", "error": err_msg, "role": role})
                    except Exception as e:
                        status_box.error(f"❌ {role_name} error: {e}")
                        errors.append({"status": "failed", "error": str(e), "role": role})
            except TimeoutError:
                # Some agents didn't finish in time — cancel them and keep what we have
                unfinished = [futures[f] for f in futures if not f.done()]
                for f in futures:
                    if not f.done():
                        f.cancel()
                status_box.warning(f"⚠️ Timed out waiting for: {', '.join(unfinished)}. Continuing with {len(research_outputs)} completed agents.")
                research_bar.progress(1.0)
            
            pool.shutdown(wait=False)

            # --- PHASE 1 VALIDATION ---
            valid, msg = PipelineValidator.validate_phase1_research(research_outputs)
            if not valid:
                st.error(f"❌ Phase 1 Validation Failed: {msg}")
                # st.stop()  # Disabled strict halt per user request
                
            status_box.update(label=f"Research Phase Complete ({len(research_outputs)}/{len(roles)} agents)", state="complete", expanded=False)

            # --- PHASE 2: MASTER METHODOLOGY DESIGN (EXACTLY ONE) ---
            if research_outputs:
                st.subheader("Designing Master Methodology")
                gemini_box = st.status("Reviewing open gaps and generating methodology...", expanded=True)
                
                # Prepare context from all agents
                context_summaries = ""
                all_open_problems = []
                for r in research_outputs:
                    role = r.get('role', 'Agent').title()
                    summary = r.get('summary', '')
                    context_summaries += f"\n--- INSIGHTS FROM {role} AGENT ---\n{summary}\n"
                    opts = r.get('open_problems', [])
                    if opts:
                        all_open_problems.extend(opts)

                try:
                    # Call EXACTLY ONCE
                    master_meth = _run_agent_safe(
                        run_methodology_agent, 
                        topic.strip(), domain.strip(),
                        all_open_problems, context_summaries,
                        timeout_seconds=300
                    )
                    
                    if type(master_meth) is tuple:
                        master_meth, _ = master_meth # strip safe wrapper err if returned
                    
                    # --- PHASE 2 VALIDATION ---
                    v2_valid, v2_msg = PipelineValidator.validate_phase2_methodology(master_meth)
                    if not v2_valid:
                        st.error(f"❌ Phase 2 Validation Failed: {v2_msg}")
                        # st.stop()  # Disabled strict halt
                        
                    gemini_box.write(f"✅ '{master_meth.get('scope_title', 'Master Methodology')}' complete")
                    
                    # Consolidate into the first dict so it exists downstream naturally without looping
                    research_outputs[0]["future_scope_methodologies"] = [master_meth]
                    # Clear out others
                    for idx in range(1, len(research_outputs)):
                        research_outputs[idx]["future_scope_methodologies"] = []
                        
                except Exception as e:
                    gemini_box.warning(f"⚠️ Methodology failed: {e}")
                    st.error(f"❌ Phase 2 Validation System Exit: {e}")
                    # st.stop()
                    
                gemini_box.update(label="Methodologies Designed", state="complete", expanded=False)
            


            # Save to Cache
            st.session_state['research_outputs'] = research_outputs

            # --- PHASE 2: VISUALIZATION ---
        if research_outputs:
            if 'master_visual' in st.session_state and st.session_state['master_visual']:
                master_visual = st.session_state['master_visual']
                st.info("Loaded Diagrams from Cache")
            else:
                st.subheader("Generating Architecture Diagram")
                viz_status = st.status("🎨 Generating diagrams...", expanded=True)
                
                # Use polling-based runner — keeps WebSocket alive
                pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = pool.submit(
                    run_visualizer_agent, topic.strip(), domain.strip(), research_outputs,
                    system_category=system_category
                )
                
                viz_start = time.time()
                viz_timeout = 300  # 5 min max
                last_status_update = 0
                
                while not future.done():
                    elapsed = int(time.time() - viz_start)
                    if elapsed > viz_timeout:
                        future.cancel()
                        break
                    # Update status every 15s so user sees it's alive
                    if elapsed - last_status_update >= 15:
                        mins = elapsed // 60
                        secs = elapsed % 60
                        viz_status.write(f"⏳ Working... ({mins}m {secs}s elapsed)")
                        last_status_update = elapsed
                    time.sleep(0.5)  # Yield to Streamlit event loop
                
                pool.shutdown(wait=False)
                
                if future.done() and not future.cancelled():
                    try:
                        master_visual = future.result(timeout=0)
                    except Exception as e:
                        master_visual = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
                else:
                    master_visual = {"status": "failed", "error": f"Timed out after {viz_timeout}s"}
                
                if not master_visual:
                    master_visual = {"status": "failed", "error": "Empty result from visualizer"}
                
                viz_status.update(
                    label="Diagram Generation " + ("Complete ✅" if master_visual.get("status") == "ok" else "Done (with warnings)"),
                    state="complete",
                    expanded=False
                )
                st.session_state['master_visual'] = master_visual
                
                # --- PHASE 3 VALIDATION ---
                v3_valid, v3_msg = PipelineValidator.validate_phase3_visuals(master_visual)
                if not v3_valid:
                    st.error(f"❌ Phase 3 Validation Failed: {v3_msg}")
                    # st.stop()
            if master_visual.get("status") == "ok":
                score_str = ""
                if master_visual.get("_autoresearch_score", -1) > -1:
                    score_str = f" **(Academic Context Peer-Review Score: {master_visual.get('_autoresearch_score')}/100)**"
                
                st.success(f"✅ {master_visual.get('source_label', 'Architecture diagram generated.')}{score_str}")
                if master_visual.get("warning"):
                    st.warning(master_visual.get("warning"))
                
                # Display diagrams in tabs (Architecture + Workflow only)
                all_diagrams = master_visual.get("all_diagrams", {})
                arch_path = master_visual.get("image_path", all_diagrams.get("architecture", ""))
                wf_path = all_diagrams.get("workflow", "")
                
                tab_names = ["📐 Architecture"]
                if wf_path and os.path.exists(wf_path): tab_names.append("🔄 Workflow")
                if "llm_generated_prompt" in master_visual: tab_names.append("🎯 Diagram Agent Prompt")

                viz_tabs = st.tabs(tab_names)
                
                tab_idx = 0
                with viz_tabs[tab_idx]:
                    if arch_path and os.path.exists(arch_path):
                        st.image(arch_path, caption="System Architecture — Peak Detailed", use_container_width=True)
                tab_idx += 1
                
                if wf_path and os.path.exists(wf_path):
                    with viz_tabs[tab_idx]:
                        st.image(wf_path, caption="Research Pipeline Workflow", use_container_width=True)
                    tab_idx += 1
                    
                if "llm_generated_prompt" in master_visual:
                    with viz_tabs[tab_idx]:
                        st.markdown("#### 🧠 Auto-Generated Diagram Prompt")
                        st.markdown(f"```text\n{master_visual['llm_generated_prompt']}\n```")
                    tab_idx += 1
                
                # Image download buttons
                image_paths = master_visual.get("image_paths", {})
                if wf_path and os.path.exists(wf_path):
                    image_paths["workflow_png"] = wf_path
                
                if image_paths:
                    st.markdown("#### 📥 Download Diagrams")
                    dl_cols = st.columns(min(len(image_paths), 3))
                    for i, (fmt, path) in enumerate(image_paths.items()):
                        if os.path.exists(path):
                            with open(path, "rb") as f:
                                img_data = f.read()
                            ext = os.path.splitext(path)[1].lstrip('.')
                            dl_cols[i % min(len(image_paths), 3)].download_button(
                                label=f"⬇️ {fmt.upper().replace('_', ' ')}",
                                data=img_data,
                                file_name=f"{topic.strip().replace(' ','_')}_{fmt}.{ext}",
                                mime=f"image/{ext}",
                                key=f"dl_img_{fmt}",
                            )
            elif master_visual.get("error"):
                st.error(f"Diagram Error: {master_visual['error']}")
            else:
                st.warning(f"Diagram Status: {master_visual.get('status', 'unknown')}")

        # --- PHASE 3: REPORT ---
        if research_outputs:
            master_visual = st.session_state.get('master_visual', {})
            if 'invoice_output' in st.session_state:
                invoice_output = st.session_state['invoice_output']
                st.info("Loaded Report from Cache")
            else:
                st.subheader("Generating Report")
                report_status = st.status("Compiling report...", expanded=True)
                
                # Polling-based approach to keep WebSocket alive
                inv_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                inv_future = inv_pool.submit(run_invoice_agent, topic, domain, research_outputs, master_visual)
                
                inv_start = time.time()
                inv_timeout = 600
                inv_last_update = 0
                
                while not inv_future.done():
                    elapsed = int(time.time() - inv_start)
                    if elapsed > inv_timeout:
                        inv_future.cancel()
                        break
                    if elapsed - inv_last_update >= 15:
                        mins = elapsed // 60
                        secs = elapsed % 60
                        report_status.write(f"⏳ Generating report... ({mins}m {secs}s elapsed)")
                        inv_last_update = elapsed
                    time.sleep(0.5)
                
                inv_pool.shutdown(wait=False)
                
                if inv_future.done() and not inv_future.cancelled():
                    try:
                        invoice_output = inv_future.result(timeout=0)
                    except Exception as e:
                        invoice_output = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
                else:
                    invoice_output = {"status": "failed", "error": f"Timed out after {inv_timeout}s"}
                
                if not invoice_output:
                    invoice_output = {"status": "failed", "error": "empty result"}
                
                # Retry once if failed
                if invoice_output.get("status") == "failed":
                    report_status.write(f"⚠️ First attempt failed ({str(invoice_output.get('error', 'unknown'))[:100]}), retrying...")
                    time.sleep(3)
                    invoice_output, inv_err2 = _run_agent_safe(
                        run_invoice_agent, topic, domain, research_outputs, master_visual,
                        timeout_seconds=300
                    )
                    if inv_err2 or not invoice_output:
                        invoice_output = {"status": "failed", "error": inv_err2 or "empty result"}
                
                st.session_state['invoice_output'] = invoice_output
                report_status.update(
                    label="Report Generation " + ("Complete ✅" if invoice_output.get("status") != "failed" else "Failed ❌"),
                    state="complete" if invoice_output.get("status") != "failed" else "error",
                    expanded=False
                )
                
                # --- PHASE 4 VALIDATION ---
                v4_valid, v4_msg = PipelineValidator.validate_phase4_report(invoice_output)
                if not v4_valid:
                    st.error(f"❌ Phase 4 Validation Failed: {v4_msg}")
                    # Allow fallback to catch it, don't hard stop if fallback exists
            
            # Fallback: Generate a structured native report with the correct 7-section layout
            if invoice_output.get("status") == "failed":
                st.warning("⚠️ Full Report Generation Failed (likely due to API limits). Generating Native Detailed Report...")

                safe_topic = "".join([c for c in topic if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_') or "report"
                generated_ts = datetime.now().strftime('%Y-%m-%d %H:%M')

                import re as _re

                def _clean(text):
                    """Strip LLM hallucination artifacts from summary text."""
                    if not text:
                        return ""
                    # Remove [1], [2,3], [1-4] style fake inline citations
                    text = _re.sub(r'\s*\[\d+(?:[,\-]\d+)*\]', '', text)
                    # Remove 'Access Full Paper' links
                    text = _re.sub(r'Access (?:Full )?Paper', '', text, flags=_re.IGNORECASE)
                    # Collapse multiple blank lines
                    text = _re.sub(r'\n{3,}', '\n\n', text)
                    text = _re.sub(r'  +', ' ', text)
                    return text.strip()

                # ─── Collect ALL real papers (deduplicated) ───
                all_real_papers = []
                seen_titles = set()
                for r in research_outputs:
                    for p in r.get("top_papers", []) + r.get("citations", []):
                        if isinstance(p, dict):
                            title = p.get("title", "") or ""
                            count = p.get("citationCount", 0) or 0
                            paper_obj = p
                        else:
                            title = str(p)
                            count = 0
                            paper_obj = {"title": title, "citationCount": count}
                            
                        key = title.strip().lower()[:70]
                        if key and key not in seen_titles:
                            seen_titles.add(key)
                            all_real_papers.append(paper_obj)
                # Sort by citation count descending
                all_real_papers.sort(key=lambda p: p.get("citationCount", 0) or 0, reverse=True)

                # ─── Collect all methodology outputs ───
                all_methodologies = []
                for r in research_outputs:
                    for m in r.get("future_scope_methodologies", []):
                        if m.get("scope_title") and not m.get("error"):
                            all_methodologies.append(m)

                sections = []

                # ─── SECTIONS 1-3: Pure academic analysis per role ───
                role_order = ["historical", "state_of_the_art", "ongoing_emerging"]
                role_labels = {
                    "historical": "Historical Foundations",
                    "state_of_the_art": "State of the Art & SOTA",
                    "ongoing_emerging": "Ongoing Emerging Trends",
                }
                for role_key in role_order:
                    for r in research_outputs:
                        if role_key in r.get("role", "").lower():
                            summ = _clean(r.get("summary", ""))
                            if summ:
                                sections.append({
                                    "title": role_labels.get(role_key, role_key.title()),
                                    "content": summ
                                })
                            break

                # ─── SECTION 4: Literature Review (single reasoned narrative) ───
                lit_review_lines = [
                    "This literature review synthesizes the key academic works retrieved from the OpenAlex database "
                    f"for the topic **\"{topic}\"**. The papers below represent verified, peer-reviewed research "
                    f"from {datetime.now().year - 5} onwards, sorted by academic impact (citation count).\n"
                ]
                if all_real_papers:
                    lit_review_lines.append(
                        f"A total of **{len(all_real_papers)} papers** were identified across the historical, "
                        "state-of-the-art, and emerging trends research phases. The literature reveals several "
                        "key research threads:\n"
                    )
                    # Group papers by year for narrative structure
                    by_year = {}
                    for p in all_real_papers:
                        yr = str(p.get("year", "Unknown"))
                        by_year.setdefault(yr, []).append(p)
                    for yr in sorted(by_year.keys(), reverse=True)[:4]:
                        papers_in_yr = by_year[yr]
                        lit_review_lines.append(
                            f"**{yr}** — {len(papers_in_yr)} paper(s) including: "
                            + "; ".join(
                                f"*{p.get('title', '')[:60]}* ({p.get('authors', '').split(',')[0]})"
                                for p in papers_in_yr[:3]
                            ) + "."
                        )
                    lit_review_lines.append(
                        "\nThe following section provides a comparative survey table of all retrieved papers."
                    )
                else:
                    lit_review_lines.append("*(No verified papers were retrieved from OpenAlex for this topic.)*")

                sections.append({"title": "Literature Review", "content": "\n".join(lit_review_lines)})

                # ─── SECTION 5: Comparative Literature Survey Table ───
                if all_real_papers:
                    lit_table = "| # | Paper Title | Authors | Year | Venue | Citations | DOI/Link |\n"
                    lit_table += "|---|---|---|---|---|---|---|\n"
                    for i, p in enumerate(all_real_papers[:30], 1):
                        title_cell = (p.get("title", "") or "")[:75].replace("|", "\\|").replace("<scp>", "").replace("</scp>", "")
                        authors_cell = (p.get("authors", "") or "")[:45].replace("|", "\\|")
                        year_cell = str(p.get("year", "") or "")
                        venue_cell = (p.get("venue", "") or "")[:30].replace("|", "\\|")
                        cited_cell = str(p.get("citationCount", "") or "")
                        url = (p.get("doi_or_url", "") or "").strip()
                        if url.startswith("http"):
                            link_cell = f"[DOI]({url})"
                        else:
                            q = title_cell.replace(" ", "+")
                            link_cell = f"[Search](https://scholar.google.com/scholar?q={q})"
                        lit_table += f"| {i} | {title_cell} | {authors_cell} | {year_cell} | {venue_cell} | {cited_cell} | {link_cell} |\n"
                else:
                    lit_table = "*(No verified papers retrieved from OpenAlex for this topic.)*\n"

                sections.append({"title": "Comparative Literature Survey", "content": lit_table})

                # ─── SECTION 6: ONE Unified Methodology (from methodology agents) ───
                if all_methodologies:
                    meth_content = (
                        "> The following research methodology is synthesized from the analysis of all three "
                        "research phases (historical, state-of-the-art, and emerging trends). "
                        "It represents a consolidated, PhD-caliber research design.\n\n"
                    )
                    for idx, m in enumerate(all_methodologies, 1):
                        scope = _clean(m.get("scope_title", f"Methodology {idx}"))
                        prob = _clean(m.get("problem_statement", ""))
                        arch = _clean(m.get("architecture_details", ""))
                        loss = _clean(m.get("loss_function", ""))
                        meth_body = _clean(m.get("proposed_methodology", ""))
                        steps = m.get("pipeline_steps", [])
                        baselines = m.get("baseline_methods", [])
                        datasets = m.get("evaluation_datasets", [])
                        outcomes = m.get("expected_outcomes", {})
                        citations = m.get("supporting_citations", [])

                        meth_content += f"### {idx}. {scope}\n\n"
                        if prob:
                            meth_content += f"**Problem Statement:** {prob}\n\n"
                        if meth_body:
                            meth_content += f"{meth_body}\n\n"
                        if arch:
                            meth_content += f"**Architecture:** {arch}\n\n"
                        if loss:
                            meth_content += f"**Loss Function:** {loss}\n\n"
                        if baselines:
                            meth_content += f"**Baseline Comparisons:** {', '.join(baselines)}\n\n"
                        if datasets:
                            meth_content += f"**Evaluation Datasets:** {', '.join(datasets)}\n\n"
                        if outcomes:
                            targets = " | ".join(f"{k}: {v}" for k, v in outcomes.items() if v)
                            if targets:
                                meth_content += f"**Expected Outcomes:** {targets}\n\n"
                        if steps:
                            meth_content += "**Technical Pipeline Steps:**\n\n"
                            for j, step in enumerate(steps, 1):
                                meth_content += f"{j}. {_clean(str(step))}\n"
                            meth_content += "\n"
                        if citations:
                            meth_content += f"**Supporting Citations:** {', '.join(citations)}\n\n"
                        meth_content += "---\n\n"
                else:
                    # If methodology agents didn't run, synthesize key open problems
                    meth_content = "> Methodology agents did not produce output. Below are the key research directions identified by the analysis agents.\n\n"
                    for r in research_outputs:
                        for direction in r.get("future_research_directions", [])[:3]:
                            scope = direction.get("scope_title", "")
                            prob = direction.get("problem_statement", "")
                            if scope:
                                meth_content += f"### {scope}\n\n{_clean(prob)}\n\n---\n\n"

                sections.append({"title": "Unified Research Methodology", "content": meth_content})

                # ─── SECTION 7: All References (deduplicated, full APA-style) ───
                refs_content = (
                    "> All references below are sourced from the OpenAlex academic database. "
                    "DOI links are provided where available.\n\n"
                )
                for i, p in enumerate(all_real_papers[:35], 1):
                    title = (p.get("title", "") or "").replace("<scp>", "").replace("</scp>", "")
                    authors = p.get("authors", "Unknown Authors")
                    year = p.get("year", "n.d.")
                    venue = p.get("venue", "")
                    url = (p.get("doi_or_url", "") or "").strip()
                    ref = f"**[{i}]** {authors} ({year}). \"{title}.\""
                    if venue:
                        ref += f" *{venue}*."
                    if url.startswith("http"):
                        ref += f" [{url}]({url})"
                    else:
                        q = title.replace(" ", "+")
                        ref += f" [Google Scholar](https://scholar.google.com/scholar?q={q})"
                    refs_content += ref + "\n\n"
                if not all_real_papers:
                    refs_content += "*(No verified references retrieved.)*\n"

                sections.append({"title": "All References", "content": refs_content})

                # ─── Build final report ───
                cover_md = (
                    f"# {topic}\n\n"
                    f"## PhD-Grade Technical Final Report in {domain}\n\n"
                    f"**Generated:** {generated_ts}  \n"
                    f"**Papers Retrieved:** {len(all_real_papers)} (OpenAlex)  \n"
                    f"**Methodologies:** {len(all_methodologies)}\n\n---\n"
                )
                toc_entries = "\n".join(f"{i + 1}. [{s['title']}](#{s['title'].lower().replace(' ', '-').replace('&', '').replace('/', '')})" for i, s in enumerate(sections))
                toc_md = f"## Table of Contents\n\n{toc_entries}"

                invoice_output = {
                    "status": "success",
                    "cover_page_markdown": cover_md,
                    "table_of_contents_markdown": toc_md,
                    "sections_markdown": sections,
                    "_autoresearch_score": 65,
                }
                st.session_state['invoice_output'] = invoice_output

            if invoice_output.get("status") == "failed":
                # Should not happen due to fallback above, but just in case
                st.error("Report generation failed completely.")
                st.json(invoice_output)
            else:
                st.success("Pipeline Finished Successfully!")
                
                # Show Invoice Autoresearch Score
                if "_autoresearch_score" in invoice_output:
                    st.info(f"🏅 **Score**: {invoice_output['_autoresearch_score']}/100")
                
                # --- RESULTS UI ---
                st.markdown("### 📄 Final Research Report")
                
                # Markdown Preview
                cover = invoice_output.get("cover_page_markdown", "")
                toc = invoice_output.get("table_of_contents_markdown", "")
                sections = invoice_output.get("sections_markdown", [])
                
                st.markdown(cover, unsafe_allow_html=True)
                st.markdown("---")
                st.markdown(toc, unsafe_allow_html=True)
                st.markdown("---")
                
                full_md_text = f"{cover}\n\n{toc}\n\n"
                
                for i, sec in enumerate(sections):
                    title = sec.get("title", "")
                    content = sec.get("content", "")
                    st.markdown(f"## {title}")
                    render_clean_markdown(content)
                    st.markdown("---")
                    full_md_text += f"\n## {title}\n{content}\n\n---\n"

                # Auto-Generated Files
                st.divider()
                st.markdown("### 📥 Download Results")
                
                # Calculate safe_topic BEFORE try block to ensure it's available for MD download if PDF fails
                safe_topic = "".join([c for c in topic if c.isalnum() or c in (' ','-','_')]).strip().replace(' ','_')
                if not safe_topic: safe_topic = "report"

                # Generate PDF immediately if possible (stateless download button fix)
                pdf_data = None
                try:
                    from pdf.pdf_generator import convert_markdown_to_pdf
                    
                    pdf_path_out = OUTPUT_DIR / f"{safe_topic}.pdf"
                    md_path_out = OUTPUT_DIR / f"{safe_topic}.md"
                    md_path_out.write_text(full_md_text, encoding="utf-8")
                    
                    convert_markdown_to_pdf(str(md_path_out), str(pdf_path_out))
                    if pdf_path_out.exists():
                        with open(pdf_path_out, "rb") as f:
                            pdf_data = f.read()
                except Exception as e:
                    st.warning(f"PDF Generation skipped: {e}")

                # --- PHASE 5 VALIDATION ---
                if pdf_data is None:  # Check if pdf generated successfully
                     try:
                         # Double check with validator
                         v5_valid, v5_msg = PipelineValidator.validate_phase5_pdf(str(pdf_path_out) if 'pdf_path_out' in locals() else None)
                         if not v5_valid:
                             st.error(f"❌ Phase 5 Validation Failed: {v5_msg}")
                     except Exception as e:
                         pass

                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        label="📄 Download Markdown Report",
                        data=full_md_text,
                        file_name=f"{safe_topic}.md",
                        mime="text/markdown"
                    )
                with col2:
                    if pdf_data:
                        st.download_button(
                            label="📕 Download PDF Report",
                            data=pdf_data,
                            file_name=f"{safe_topic}.pdf",
                            mime="application/pdf"
                        )
                    else:
                        st.button("PDF Unavailable", disabled=True)


