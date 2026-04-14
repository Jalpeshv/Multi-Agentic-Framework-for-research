#!/usr/bin/env bash
# run_local.sh - convenience: create venv, install, start streamlit
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "Make sure you edited .env and started Ollama."
streamlit run app/streamlit_app.py --server.port=8501
