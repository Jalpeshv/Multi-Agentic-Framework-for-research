# AI Research Assistant — Groq Edition

This repository implements a production-style, deterministic, stateless Research Assistant consisting of:
- 3 Research Agents (Groq Llama 3 / Mixtral), roles: historical, state_of_the_art, ongoing_emerging.
- 1 Report Synthesis Agent (Groq).
- Gradio frontend for inputs, preview, and PDF download.

## Quick start

1. Open VS Code and open this folder.
2. Create venv and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app/gradio_app.py
```