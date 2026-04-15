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
from agents.autoresearch_agent import run_autoresearch
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
st.markdown("**Scholar-ready research & PhD-grade reports — powered by multi-agent AI.**")

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
    
    st.markdown("---")
    st.subheader("Experimental Features")
    enable_autoresearch = st.checkbox("🔍 Enable Autonomous Code Experiment (AutoResearch)", value=False, help="Runs the iterative self-improving code experiment loop.")
    ar_minutes = 5
    if enable_autoresearch:
        ar_minutes = st.slider("Experiment Duration (Minutes)", 1, 60, 5)

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
            st.subheader(f"1. Researching: {topic} (Last {years_back} Years)")
            research_bar = st.progress(0)
            status_box = st.status("Launching 3 research agents in PARALLEL...", expanded=True)
            
            status_box.write("**All 3 agents launching with Groq (cloud, ~3s each)**")
            status_box.write("Ollama fallback only if Groq hits rate limits.")
            
            # Launch research agents with 3s stagger to avoid Groq 30 RPM limit
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
            futures = {}
            for i, role in enumerate(roles):
                if i > 0:
                    time.sleep(3)  # Stagger to stay under Groq RPM limit
                f = pool.submit(
                    run_research_agent, topic.strip(), domain.strip(), role, years_back
                )
                futures[f] = role
            
            # Collect results as they complete (gracefully handle timeouts)
            completed = 0
            try:
                for future in concurrent.futures.as_completed(futures, timeout=120):
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
            status_box.update(label=f"Research Phase Complete ({len(research_outputs)}/{len(roles)} agents)", state="complete", expanded=False)

            # --- PHASE 1.5: METHODOLOGY ENHANCEMENT (ALL IN PARALLEL) ---
            if research_outputs:
                st.subheader("1.5. Enhancing Methodologies with Specialist Agent")
                
                # Prepare context from all agents
                context_summaries = ""
                for r in research_outputs:
                    role = r.get('role', 'Agent').title()
                    summary = r.get('summary', '')
                    context_summaries += f"\n--- INSIGHTS FROM {role} AGENT ---\n{summary}\n"

                gemini_box = st.status("Designing ALL methodologies in parallel...", expanded=True)
                methodology_bar = st.progress(0)
                
                # Collect all scope items first
                all_scope_tasks = []
                for r_out in research_outputs:
                    scopes = r_out.get('future_research_directions', [])[:2]
                    for scope_item in scopes:
                        all_scope_tasks.append((r_out, scope_item))
                
                total_scopes = len(all_scope_tasks)
                gemini_box.write(f"**Launching {total_scopes} methodology agents in parallel...**")
                
                # Launch methodology agents with stagger for Groq RPM limit
                meth_pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(total_scopes, 2))
                meth_futures = {}
                for i, (r_out, scope_item) in enumerate(all_scope_tasks):
                    if i > 0:
                        time.sleep(2)  # Stagger for Groq RPM
                    f = meth_pool.submit(
                        run_methodology_agent, topic.strip(), domain.strip(),
                        scope_item, context_summaries
                    )
                    meth_futures[f] = (r_out, scope_item)
                
                # Initialize result storage
                results_by_agent = {}  # r_out id -> list of enhanced scopes
                for r_out in research_outputs:
                    results_by_agent[id(r_out)] = []
                
                completed_scopes = 0
                try:
                    for future in concurrent.futures.as_completed(meth_futures, timeout=120):
                        r_out, scope_item = meth_futures[future]
                        label = scope_item.get('scope_title', 'Scope')
                        completed_scopes += 1
                        if total_scopes > 0:
                            methodology_bar.progress(completed_scopes / total_scopes)
                        
                        try:
                            enhanced_scope = future.result(timeout=0)
                            if not enhanced_scope:
                                enhanced_scope = {**scope_item, "error": "empty result"}
                                gemini_box.warning(f"⚠️ '{label}' returned empty")
                            else:
                                gemini_box.write(f"✅ '{label}' complete")
                        except Exception as e:
                            gemini_box.warning(f"⚠️ '{label}' failed: {e}")
                            enhanced_scope = {**scope_item, "error": str(e)}
                        
                        results_by_agent[id(r_out)].append(enhanced_scope)
                except TimeoutError:
                    unfinished = sum(1 for f in meth_futures if not f.done())
                    for f in meth_futures:
                        if not f.done():
                            f.cancel()
                    gemini_box.warning(f"⚠️ {unfinished} methodology agent(s) timed out. Continuing with completed ones.")
                    methodology_bar.progress(1.0)
                
                meth_pool.shutdown(wait=False)
                
                # Assign results back
                for r_out in research_outputs:
                    r_out["future_scope_methodologies"] = results_by_agent.get(id(r_out), [])
                
                gemini_box.update(label="Methodologies Designed", state="complete", expanded=False)
            
            # --- PHASE 1.8: AUTORESEARCH EXPERIMENT (Optional) ---
            if 'enable_autoresearch' not in locals(): enable_autoresearch = False # Fallback
            if enable_autoresearch:
                st.subheader(f"1.8. Running Autonomous Experiment ({ar_minutes} mins)")
                ar_status = st.status("Initializing Autoresearch (iterative optimization)...", expanded=True)
                
                # Check if already in outputs (idempotency for reruns if structured)
                # But here we run it fresh if requested
                
                ar_result, ar_err = _run_agent_safe(
                    run_autoresearch, 
                    topic=topic.strip(), 
                    domain=domain.strip(),
                    duration_minutes=ar_minutes,
                    timeout_seconds=(ar_minutes * 60) + 120
                )
                
                if ar_err:
                    ar_status.error(f"Autoresearch failed: {ar_err}")
                elif ar_result.get("status") == "failed" or "crash" in str(ar_result).lower() or ar_result.get("summary") is None:
                    ar_status.error(f"Autoresearch ended with errors or crashed during execution.")
                else:
                    ar_status.write("✅ Experiment complete.")
                    ar_status.update(label="Autoresearch Complete", state="complete", expanded=False)
                    
                    # Synthesize result into a format 'research_outputs' likes
                    ar_summary_block = {
                        "role": "experimental_validation",
                        "topic": topic,
                        "summary": f"### Autonomous Experiment Results\n\n**Goal**: {topic}\n\n**Outcome**:\n{ar_result.get('summary', 'No summary provided.')}\n\n**Technical Log**:\nSee attached experiment logs.",
                        "future_research_directions": [],
                        "citations": [],
                        "top_papers": [],
                        "future_scope_methodologies": [{
                            "scope_title": "Automated Optimization Findings",
                            "problem_statement": "Experimental validation of core concepts.",
                            "proposed_methodology": ar_result.get('summary', 'See logs.')
                        }],
                        "_autoresearch_score": 100 if ar_result.get("status") == "success" else 50
                    }
                    research_outputs.append(ar_summary_block)
                    st.success(f"Autoresearch added to pipeline results.")

            # Save to Cache
            st.session_state['research_outputs'] = research_outputs

            # --- PHASE 2: VISUALIZATION ---
        if research_outputs:
            if 'master_visual' in st.session_state and st.session_state['master_visual']:
                master_visual = st.session_state['master_visual']
                st.info("Loaded Diagrams from Cache")
            else:
                st.subheader("2. Generating System Architecture Diagram")
                viz_status = st.status("🎨 Generating diagrams...", expanded=True)
                viz_status.write("PaperBanana pipeline (1 iteration) + Pillow fallback...")
                
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
            
            if master_visual.get("status") == "ok":
                score_str = ""
                if master_visual.get("_autoresearch_score", -1) > -1:
                    score_str = f" **(Academic Context Peer-Review Score: {master_visual.get('_autoresearch_score')}/100)**"
                
                st.success(f"✅ {master_visual.get('source_label', 'Architecture diagram generated.')}{score_str}")
                if master_visual.get("warning"):
                    st.warning(master_visual.get("warning"))
                
                # Display ALL diagrams in tabs
                all_diagrams = master_visual.get("all_diagrams", {})
                arch_path = master_visual.get("image_path", all_diagrams.get("architecture", ""))
                wf_path = all_diagrams.get("workflow", "")
                methods_path = all_diagrams.get("methods", "")
                
                tab_names = ["📐 Architecture"]
                if wf_path and os.path.exists(wf_path): tab_names.append("🔄 Workflow")
                if methods_path and os.path.exists(methods_path): tab_names.append("🧪 Methods")
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
                
                if methods_path and os.path.exists(methods_path):
                    with viz_tabs[tab_idx]:
                        st.image(methods_path, caption="Key Methods & Techniques", use_container_width=True)
                    tab_idx += 1
                    
                if "llm_generated_prompt" in master_visual:
                    with viz_tabs[tab_idx]:
                        st.markdown("#### 🧠 Auto-Generated Peak-Detail Diagram Prompt")
                        st.info("A dedicated agent synthesized all your research specifically into this elite-level, hyper-detailed architectural description, serving as the master prompt for generating the diagram.", icon="✨")
                        st.markdown(f"```text\n{master_visual['llm_generated_prompt']}\n```")
                    tab_idx += 1
                
                # Methodology flowcharts (image-based, no mermaid)
                methodology_images = master_visual.get("methodology_images", [])
                if methodology_images:
                    st.markdown("#### Methodology Flowcharts")
                    for mi in methodology_images:
                        mpath = mi.get("path", "")
                        mtitle = mi.get("title", "Methodology")
                        if mpath and os.path.exists(mpath):
                            st.image(mpath, caption=mtitle, use_container_width=True)
                
                # Image download buttons
                image_paths = master_visual.get("image_paths", {})
                # Also include workflow and methods for download
                if wf_path and os.path.exists(wf_path):
                    image_paths["workflow_png"] = wf_path
                if methods_path and os.path.exists(methods_path):
                    image_paths["methods_png"] = methods_path
                
                if image_paths:
                    st.markdown("#### 📥 Download Diagrams")
                    dl_cols = st.columns(min(len(image_paths), 5))
                    for i, (fmt, path) in enumerate(image_paths.items()):
                        if os.path.exists(path):
                            with open(path, "rb") as f:
                                img_data = f.read()
                            ext = os.path.splitext(path)[1].lstrip('.')
                            dl_cols[i % min(len(image_paths), 5)].download_button(
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
                st.subheader("3. Generating PhD-Grade Report")
                report_status = st.status("Compiling whitepaper...", expanded=True)
                report_status.write("**Synthesizing** research into PhD-grade report via Groq...")
                
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
                        key = (p.get("title", "") or "").strip().lower()[:70]
                        if key and key not in seen_titles:
                            seen_titles.add(key)
                            all_real_papers.append(p)
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
                    st.info(f"🏅 **Self-Correction Panel**: The Report Synthesis Agent achieved a peer-review score of **{invoice_output['_autoresearch_score']}/100** before finalizing.")
                
                # --- RESULTS UI ---
                tab1, tab2 = st.tabs(["📄 Final Report", "📊 Raw Research Data"])
                
                with tab1:
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

                with tab2:
                    for r in research_outputs:
                        role_label = r.get('role', 'unknown').replace('_', ' ').title()
                        with st.expander(f"🔬 {role_label} — Research Data", expanded=False):
                            if "_autoresearch_score" in r:
                                st.markdown(f"**🏅 Peer-Review Score (Parallel Swarm):** {r['_autoresearch_score']}/100")
                                if "_autoresearch_feedback" in r:
                                    st.markdown(f"**💬 Judge Feedback:** {r['_autoresearch_feedback']}")
                            
                            # Summary
                            if r.get("summary"):
                                st.markdown("#### Summary")
                                st.markdown(r["summary"], unsafe_allow_html=True)
                            
                            # Future Scope Methodologies
                            fsm = r.get("future_scope_methodologies", [])
                            if fsm:
                                st.markdown("#### Future Scope & Proposed Methodologies")
                                for idx, item in enumerate(fsm, 1):
                                    scope = item.get("scope_title", item.get("scope", ""))
                                    methodology = item.get("proposed_methodology", item.get("proposed_solution", ""))
                                    cites = item.get("supporting_citations", [])
                                    st.markdown(f"**{idx}. {scope}**")
                                    st.markdown(methodology)
                                    if cites:
                                        st.markdown(f"*Supporting Citations: {', '.join(cites)}*")
                                    st.markdown("---")
                            
                            # Citations
                            citations = r.get("citations", [])
                            if citations:
                                st.markdown("#### Citations")
                                for c in citations:
                                    label = c.get("label", "")
                                    title = c.get("title", "")
                                    authors = c.get("authors", "")
                                    year = c.get("year", "")
                                    url = c.get("doi_or_url", "")
                                    if url and url.startswith("http"):
                                        st.markdown(f"{label} {authors} ({year}). \"{title}\". [{url}]({url})")
                                    else:
                                        st.markdown(f"{label} {authors} ({year}). \"{title}\". {url}")
                            
                            # Top Papers
                            papers = r.get("top_papers", [])
                            if papers:
                                st.markdown("#### Top Papers")
                                for idx, p in enumerate(papers, 1):
                                    url = p.get("doi_or_url", "")
                                    if url and url.startswith("http"):
                                        st.markdown(f"{idx}. {p.get('authors','')} ({p.get('year','')}). \"{p.get('title','')}\". [{url}]({url})")
                                    else:
                                        st.markdown(f"{idx}. {p.get('authors','')} ({p.get('year','')}). \"{p.get('title','')}\". {url}")

                # --- PHASE 4: AUTONOMOUS EXPERIMENTATION (OPTIONAL) ---
                st.markdown("---")
                st.subheader("4. Autonomous Research Experiment (Beta)")
                
                with st.expander("🚀 Launch Autonomous Validation Loop", expanded=False):
                    st.info("This module runs an autonomous iterative optimization loop. It will research your topic, generate experiments, and produce a validation report.")
                    ar_time = st.slider("Experiment Duration (Minutes)", 1, 60, 5)
                    
                    if st.button("Start Autoresearch Experiment"):
                        ar_status = st.status("Running autonomous experiment...", expanded=True)
                        ar_status.write(f"Initializing `uv run train.py` for {ar_time} minutes...")
                        
                        # Use the safe runner
                        # Note: run_autoresearch signature: (topic, domain, duration_minutes)
                        ar_res, ar_err = _run_agent_safe(
                            run_autoresearch, 
                            topic=topic.strip(), 
                            domain=domain.strip(),
                            duration_minutes=ar_time, 
                            timeout_seconds=(ar_time*60)+120
                        )
                        
                        if ar_err:
                            ar_status.error(f"Experiment failed: {ar_err}")
                        elif ar_res.get("status") == "failed":
                             ar_status.error(f"Experiment failed: {ar_res.get('error')}")
                        else:
                             ar_status.update(label="Experiment Complete ✅", state="complete", expanded=False)
                             st.success("Optimization loop finished!")
                             
                             if ar_res.get("summary"):
                                 st.markdown("### Experiment Results")
                                 st.markdown(ar_res["summary"])
