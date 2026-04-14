#!/usr/bin/env python3
"""Fix all tables in report_full.tex: proper column widths + remove duplicate headers + add diagrams."""
import re

filepath = r'c:\Users\viken hadavani\ai-research-assistant\report\report_full.tex'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# ===== STEP 1: Remove duplicate third header blocks after \endfoot =====
# Pattern: \endfoot + optional blank + \hline + \textbf{...}\\ + \hline
content = re.sub(
    r'(\\endfoot\r?\n)(?:\r?\n)?\\hline\r?\n\\textbf\{[^\n]+\\\\\\\\\r?\n\\hline\r?\n',
    r'\1',
    content
)

# ===== STEP 2: Fix column widths =====
def replace_nth(text, old, new, n=1):
    idx = -1
    for _ in range(n):
        idx = text.find(old, idx + 1)
        if idx == -1:
            return text
    return text[:idx] + new + text[idx + len(old):]

# Table: Tools {|l|l|p{14.5cm}|} → {|p{2.8cm}|p{2.8cm}|p{8cm}|}
content = replace_nth(content,
    r'\begin{longtable}{|l|l|p{14.5cm}|}',
    r'\begin{longtable}{|p{2.8cm}|p{2.8cm}|p{8cm}|}', 1)

# Table: Session State {|l|l|p{14.5cm}|} → {|p{3cm}|l|p{8.5cm}|}
content = replace_nth(content,
    r'\begin{longtable}{|l|l|p{14.5cm}|}',
    r'\begin{longtable}{|p{3cm}|l|p{8.5cm}|}', 1)

# Table: Groq Limits {|l|c|c|c|p{14.5cm}|} → {|p{2.5cm}|c|c|c|p{5.5cm}|}
content = replace_nth(content,
    r'\begin{longtable}{|l|c|c|c|p{14.5cm}|}',
    r'\begin{longtable}{|p{2.5cm}|c|c|c|p{5.5cm}|}', 1)

# Table: Token Budget same spec → same fix
content = replace_nth(content,
    r'\begin{longtable}{|l|c|c|c|p{14.5cm}|}',
    r'\begin{longtable}{|p{2.5cm}|c|c|c|p{5.5cm}|}', 1)

# Table: Token Consumption same spec → same fix
content = replace_nth(content,
    r'\begin{longtable}{|l|c|c|c|p{14.5cm}|}',
    r'\begin{longtable}{|p{2.5cm}|c|c|c|p{5.5cm}|}', 1)

# Table: Themes {|c|l|l|l|p{14.5cm}|} → {|c|l|l|l|p{5cm}|}
content = replace_nth(content,
    r'\begin{longtable}{|c|l|l|l|p{14.5cm}|}',
    r'\begin{longtable}{|c|l|l|l|p{5cm}|}', 1)

# Table: Diagram Types {|l|c|c|p{14.5cm}|} → {|p{2.8cm}|c|c|p{6cm}|}
content = replace_nth(content,
    r'\begin{longtable}{|l|c|c|p{14.5cm}|}',
    r'\begin{longtable}{|p{2.8cm}|c|c|p{6cm}|}', 1)

# Table: Exp Setup {|l|p{14.5cm}|} → {|p{4cm}|p{9.5cm}|}
content = replace_nth(content,
    r'\begin{longtable}{|l|p{14.5cm}|}',
    r'\begin{longtable}{|p{4cm}|p{9.5cm}|}', 1)

# Table: Agent Scores {|p{14.5cm}|c|c|c|c|} → {|p{4.5cm}|c|c|c|c|}
content = replace_nth(content,
    r'\begin{longtable}{|p{14.5cm}|c|c|c|c|}',
    r'\begin{longtable}{|p{4.5cm}|c|c|c|c|}', 1)

# Table: Pipeline Perf {|p{14.5cm}|c|c|c|c|c|} → {|p{3cm}|c|c|c|c|c|}
content = replace_nth(content,
    r'\begin{longtable}{|p{14.5cm}|c|c|c|c|c|}',
    r'\begin{longtable}{|p{3cm}|c|c|c|c|c|}', 1)

# Table: Report Quality {|p{14.5cm}|c|c|c|c|} → {|p{4cm}|c|c|c|c|}
content = replace_nth(content,
    r'\begin{longtable}{|p{14.5cm}|c|c|c|c|}',
    r'\begin{longtable}{|p{4cm}|c|c|c|c|}', 1)

# Table: Perf Benchmark {|l|c|c|c|c|p{14.5cm}|} → {|p{2.5cm}|c|c|c|c|p{4cm}|}
content = replace_nth(content,
    r'\begin{longtable}{|l|c|c|c|c|p{14.5cm}|}',
    r'\begin{longtable}{|p{2.5cm}|c|c|c|c|p{4cm}|}', 1)

# Table: Baseline Compare {|p{14.5cm}|c|c|c|} → {|p{5cm}|c|c|c|}
content = replace_nth(content,
    r'\begin{longtable}{|p{14.5cm}|c|c|c|}',
    r'\begin{longtable}{|p{5cm}|c|c|c|}', 1)

# ===== STEP 3: Also fix headers inside endfirsthead/endhead to match =====
# The headers use the same column layout, which is fine - column count matches.
# No changes needed there since only the \begin line defines widths.

# ===== STEP 4: Add diagrams =====

# --- Diagram 1: JSON Repair Pipeline Flowchart (after JSON extraction discussion) ---
json_flowchart = r"""
\begin{figure}[H]
\centering
\begin{tikzpicture}[node distance=1.6cm, every node/.style={font=\small}]
\node[rectangle, draw=blue!70, thick, fill=blue!20, text width=2.5cm, minimum height=0.9cm, align=center, rounded corners=4pt] (raw) {Raw LLM Output};
\node[rectangle, draw=orange!70, thick, fill=orange!20, text width=2.5cm, minimum height=0.9cm, align=center, rounded corners=4pt, below of=raw] (s1) {Stage 1: Strip Think Tags};
\node[rectangle, draw=yellow!70!black, thick, fill=yellow!20, text width=2.5cm, minimum height=0.9cm, align=center, rounded corners=4pt, below of=s1] (s2) {Stage 2: Remove Code Fences};
\node[rectangle, draw=red!70, thick, fill=red!20, text width=2.5cm, minimum height=0.9cm, align=center, rounded corners=4pt, below of=s2] (s3) {Stage 3: Balanced Brace Extract};
\node[rectangle, draw=purple!70, thick, fill=purple!20, text width=2.5cm, minimum height=0.9cm, align=center, rounded corners=4pt, below of=s3] (s4) {Stage 4: Truncation Repair};
\node[rectangle, draw=green!70!black, thick, fill=green!30, text width=2.5cm, minimum height=0.9cm, align=center, rounded corners=4pt, right of=s2, node distance=5cm] (ok) {Valid JSON Object};
\draw[-{Stealth[length=2.5mm]}, thick] (raw) -- (s1);
\draw[-{Stealth[length=2.5mm]}, thick] (s1) -- (s2);
\draw[-{Stealth[length=2.5mm]}, thick] (s2) -- (s3);
\draw[-{Stealth[length=2.5mm]}, thick] (s3) -- (s4);
\draw[-{Stealth[length=2.5mm]}, thick, green!70!black] (s1) -- node[above, font=\tiny] {parse OK} (ok);
\draw[-{Stealth[length=2.5mm]}, thick, green!70!black] (s2) -- (ok);
\draw[-{Stealth[length=2.5mm]}, thick, green!70!black] (s3) -- node[above, font=\tiny] {parse OK} ++(2.5,0) |- (ok);
\draw[-{Stealth[length=2.5mm]}, thick, green!70!black] (s4) -- node[below, font=\tiny] {repaired} ++(2.5,0) |- (ok);
\end{tikzpicture}
\caption{4-Stage JSON Extraction and Repair Pipeline}
\label{fig:json_pipeline}
\end{figure}
"""
# Insert after the paragraph discussing the repair pipeline (search for "priority order")
content = content.replace(
    r"and finally falling back to the balanced-brace finite-state extractor which tracks brace depth, string context, and escape sequences to locate the first complete JSON object boundary.",
    r"and finally falling back to the balanced-brace finite-state extractor which tracks brace depth, string context, and escape sequences to locate the first complete JSON object boundary." + "\r\n" + json_flowchart
)

# --- Diagram 2: Tournament Selection Process (after tournament discussion in Ch4) ---
tournament_diagram = r"""
\begin{figure}[H]
\centering
\begin{tikzpicture}[node distance=1.2cm, every node/.style={font=\small}]
\node[rectangle, draw=blue!70, thick, fill=blue!25, text width=2.3cm, minimum height=0.9cm, align=center, rounded corners=4pt] (t1) {Experiment 1\\$T=0.2$};
\node[rectangle, draw=blue!70, thick, fill=blue!25, text width=2.3cm, minimum height=0.9cm, align=center, rounded corners=4pt, right of=t1, node distance=3.2cm] (t2) {Experiment 2\\$T=0.4$};
\node[rectangle, draw=blue!70, thick, fill=blue!25, text width=2.3cm, minimum height=0.9cm, align=center, rounded corners=4pt, right of=t2, node distance=3.2cm] (t3) {Experiment 3\\$T=0.6$};
\node[rectangle, draw=red!70, thick, fill=red!20, text width=8cm, minimum height=0.9cm, align=center, rounded corners=4pt, below=1.5cm of t2] (judge) {LLM-as-Judge: Score each on Depth + Accuracy + Completeness};
\node[rectangle, draw=green!70!black, thick, fill=green!30, text width=3.5cm, minimum height=0.9cm, align=center, rounded corners=4pt, below=1.5cm of judge] (best) {Select Highest Score\\(Best of 3)};
\draw[-{Stealth[length=2.5mm]}, thick, blue!70] (t1) -- node[left, font=\tiny] {Score: 82} (judge);
\draw[-{Stealth[length=2.5mm]}, thick, blue!70] (t2) -- node[right, font=\tiny] {Score: 91} (judge);
\draw[-{Stealth[length=2.5mm]}, thick, blue!70] (t3) -- node[right, font=\tiny] {Score: 87} (judge);
\draw[-{Stealth[length=2.5mm]}, thick, green!70!black] (judge) -- (best);
\end{tikzpicture}
\caption{Tournament-Based Selection: Best-of-3 Experiments with LLM Judge}
\label{fig:tournament}
\end{figure}
"""
# Insert after tournament discussion in Ch4 working example
content = content.replace(
    r"\textbf{Phase 1.5 --- Methodology Enhancement",
    tournament_diagram + r"\textbf{Phase 1.5 --- Methodology Enhancement"
)

# --- Diagram 3: Grouped bar chart for baseline comparison ---
baseline_chart = r"""
\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
    ybar,
    bar width=12pt,
    width=0.9\textwidth,
    height=7cm,
    ylabel={Score / Percentage},
    symbolic x coords={Paper ID,Gap ID,Methodology,Coherence},
    xtick=data,
    x tick label style={font=\small},
    ymin=0, ymax=100,
    nodes near coords,
    nodes near coords style={font=\tiny},
    legend style={at={(0.5,-0.2)}, anchor=north, legend columns=3, font=\small},
    grid=major,
    grid style={gray!30},
    ymajorgrids=true,
    xmajorgrids=false,
]
\addplot[fill=blue!60, draw=blue!80] coordinates {(Paper ID,84) (Gap ID,88) (Methodology,85) (Coherence,90)};
\addlegendentry{Human Expert}
\addplot[fill=orange!60, draw=orange!80] coordinates {(Paper ID,56) (Gap ID,50) (Methodology,52) (Coherence,65)};
\addlegendentry{Single-Model (GPT-4)}
\addplot[fill=green!60!teal, draw=green!80!black] coordinates {(Paper ID,76) (Gap ID,75) (Methodology,78) (Coherence,82)};
\addlegendentry{Our Multi-Agent System}
\end{axis}
\end{tikzpicture}
\caption{Quality Comparison: Human Expert vs. Single-Model vs. Multi-Agent System}
\label{fig:baseline_bar}
\end{figure}
"""
# Insert after baseline comparison table
content = content.replace(
    "The multi-agent system achieves 76\\% of human expert",
    baseline_chart + "\r\nThe multi-agent system achieves 76\\% of human expert"
)

# --- Diagram 4: Research Quality Scores by Topic (grouped bar) ---
topic_scores_chart = r"""
\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
    ybar,
    bar width=10pt,
    width=0.9\textwidth,
    height=7cm,
    ylabel={Quality Score (0--100)},
    symbolic x coords={Transformers,Quantum EC,Auto Vehicles,Protein Fold,Fed Learning},
    xtick=data,
    x tick label style={rotate=20, anchor=east, font=\small},
    ymin=70, ymax=100,
    nodes near coords,
    nodes near coords style={font=\tiny},
    legend style={at={(0.5,-0.25)}, anchor=north, legend columns=3, font=\small},
    grid=major,
    grid style={gray!30},
    ymajorgrids=true,
    xmajorgrids=false,
]
\addplot[fill=blue!50, draw=blue!70] coordinates {(Transformers,87) (Quantum EC,82) (Auto Vehicles,85) (Protein Fold,83) (Fed Learning,86)};
\addlegendentry{Historical}
\addplot[fill=red!50!orange, draw=red!70] coordinates {(Transformers,91) (Quantum EC,88) (Auto Vehicles,93) (Protein Fold,89) (Fed Learning,90)};
\addlegendentry{State-of-the-Art}
\addplot[fill=teal!50, draw=teal!70] coordinates {(Transformers,84) (Quantum EC,79) (Auto Vehicles,86) (Protein Fold,81) (Fed Learning,83)};
\addlegendentry{Emerging}
\end{axis}
\end{tikzpicture}
\caption{Research Agent Quality Scores Across Five Test Topics}
\label{fig:topic_scores}
\end{figure}
"""
# Insert after agent scores key findings
content = content.replace(
    "\\section{Pipeline Performance Metrics}",
    topic_scores_chart + "\r\n\\section{Pipeline Performance Metrics}"
)

# --- Diagram 5: Feature comparison of existing tools vs our system ---
feature_comparison = r"""
\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
    xbar,
    bar width=10pt,
    width=0.85\textwidth,
    height=8cm,
    xlabel={Capability Score (0 = None, 1 = Partial, 2 = Full)},
    symbolic y coords={PDF Export,Temporal Filter,Self-Correction,Report Synthesis,Diagram Gen,Methodology Gen,Quality Scoring,Multi-Agent},
    ytick=data,
    y tick label style={font=\small},
    xmin=0, xmax=2.5,
    legend style={at={(0.5,-0.15)}, anchor=north, legend columns=3, font=\small},
    grid=major,
    grid style={gray!30},
    xmajorgrids=true,
    ymajorgrids=false,
]
\addplot[fill=blue!40, draw=blue!60] coordinates {(0,PDF Export) (1,Temporal Filter) (0,Self-Correction) (0,Report Synthesis) (0,Diagram Gen) (0,Methodology Gen) (0,Quality Scoring) (0,Multi-Agent)};
\addlegendentry{Semantic Scholar}
\addplot[fill=orange!50, draw=orange!70] coordinates {(1,PDF Export) (2,Temporal Filter) (0,Self-Correction) (1,Report Synthesis) (0,Diagram Gen) (0,Methodology Gen) (0,Quality Scoring) (0,Multi-Agent)};
\addlegendentry{Elicit}
\addplot[fill=green!50!teal, draw=green!70!black] coordinates {(2,PDF Export) (2,Temporal Filter) (2,Self-Correction) (2,Report Synthesis) (2,Diagram Gen) (2,Methodology Gen) (2,Quality Scoring) (2,Multi-Agent)};
\addlegendentry{Our System}
\end{axis}
\end{tikzpicture}
\caption{Feature Capability Comparison Across Research Tools}
\label{fig:feature_compare}
\end{figure}
"""
# Insert after existing systems table caption
content = content.replace(
    "\\section{Review of Literature and Findings}",
    feature_comparison + "\r\n\\section{Review of Literature and Findings}"
)

# --- Diagram 6: Pipeline time distribution (horizontal stacked bar as pseudo-pie) ---
time_dist = r"""
\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
    xbar stacked,
    bar width=30pt,
    width=0.9\textwidth,
    height=3.5cm,
    xlabel={Duration (seconds)},
    symbolic y coords={Pipeline},
    ytick=data,
    y tick label style={font=\small},
    xmin=0,
    legend style={at={(0.5,-0.6)}, anchor=north, legend columns=3, font=\small},
    nodes near coords,
    nodes near coords style={font=\tiny\bfseries, text=white},
    every axis plot/.append style={fill opacity=0.9},
]
\addplot[fill=blue!70, draw=blue!90] coordinates {(142,Pipeline)};
\addlegendentry{Research (142s)}
\addplot[fill=red!60, draw=red!80] coordinates {(14,Pipeline)};
\addlegendentry{Quality Eval (14s)}
\addplot[fill=purple!60, draw=purple!80] coordinates {(48,Pipeline)};
\addlegendentry{Methodology (48s)}
\addplot[fill=teal!60, draw=teal!80] coordinates {(95,Pipeline)};
\addlegendentry{Visualization (95s)}
\addplot[fill=orange!60, draw=orange!80] coordinates {(65,Pipeline)};
\addlegendentry{Synthesis (65s)}
\addplot[fill=green!50, draw=green!70] coordinates {(5,Pipeline)};
\addlegendentry{PDF Export (5s)}
\end{axis}
\end{tikzpicture}
\caption{Pipeline Phase Time Distribution (Mean Total: 369 seconds)}
\label{fig:time_dist}
\end{figure}
"""
# Insert after the phase duration figure
content = content.replace(
    "The mean total pipeline duration of 369 seconds",
    time_dist + "\r\nThe mean total pipeline duration of 369 seconds"
)

# ===== STEP 5: Write fixed file =====
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("SUCCESS: All tables fixed and diagrams added!")
print("Changes made:")
print("  - Removed duplicate third header rows from all tables")
print("  - Fixed 13 tables with p{14.5cm} columns to fit within page margins")
print("  - Added 6 new diagrams/charts:")
print("    1. JSON Repair Pipeline Flowchart (Chapter 5)")
print("    2. Tournament Selection Process (Chapter 4)")  
print("    3. Baseline Comparison Grouped Bar Chart (Chapter 6)")
print("    4. Research Quality Scores by Topic Chart (Chapter 6)")
print("    5. Feature Capability Comparison Chart (Chapter 2)")
print("    6. Pipeline Time Distribution Chart (Chapter 6)")
