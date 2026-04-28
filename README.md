# Multi-Agentic Framework for Research

A robust, multi-agent AI research assistant built with Streamlit and powered by Groq's Llama 3 / Mixtral models. This system simulates a team of specialized AI researchers to automatically generate PhD-caliber technical research reports, methodology blueprints, and architecture diagrams for a given topic.

## 🌟 Features

- **Multi-Agent Research Pipeline**: 
  - **Historical Agent**: Reviews foundational papers and early breakthroughs.
  - **State-of-the-Art (SOTA) Agent**: Analyzes current leading methods and cutting-edge papers.
  - **Ongoing/Emerging Agent**: Focuses on future trends, unreleased preprints, and active problems.
- **Methodology Synthesis**: An orchestrator agent that consolidates the findings into a single, cohesive research methodology.
- **Visualizer Agent**: Automatically generates system architecture and workflow diagrams for the proposed methodology.
- **Report Generation**: A compiler agent that packages everything into a formatted Markdown and PDF report, including full citations and literature review.
- **Streamlit UI**: A clean, interactive web interface to parameterize research, track progress, and download artifacts.

## 🛠 Prerequisites

- **Python 3.10+**
- A **Groq API Key** (for fast Llama 3 / Mixtral inference).

## 🚀 Installation & Setup

Follow these steps to run the application locally:

### 1. Clone the repository
```bash
git clone https://github.com/Jalpeshv/Multi-Agentic-Framework-for-research.git
cd Multi-Agentic-Framework-for-research
```

### 2. Set up the virtual environment
Create a Python virtual environment to keep dependencies isolated:
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
Install the required packages from `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
You need to set up your API keys. A template is provided in `.env.example`.

Copy `.env.example` to `.env`:
```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open the `.env` file and insert your API keys:

> **💡 Pro Tip for API Limits & Quality**: 
> - **Groq API**: Since Groq has strict rate limits on free tiers, we recommend generating multiple Groq API keys and rotating them, or keeping your queries small.
> - **OpenRouter API**: For the best output quality and to avoid rate limits entirely, we highly recommend using **OpenRouter** instead.

```env
GROQ_API_KEY=your_groq_api_key_here
# If using OpenRouter, you can add your OPENROUTER_API_KEY here instead/additionally
# OPENROUTER_API_KEY=your_openrouter_key
GROQ_MODEL=llama3-70b-8192

# Optional: If you use Ollama locally for certain agents
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=mistral
```
> **Note:** The `.env` file is excluded in `.gitignore` to prevent leaking your API keys to version control.

### 5. Run the Application
Start the Streamlit server:
```bash
streamlit run app/streamlit_app.py
```

This will automatically open the application in your default web browser (usually at `http://localhost:8501`).

## 🧠 How to Approach It

1. **Enter a Topic**: On the left sidebar, enter a specific technical or academic topic (e.g., "Quantum Error Correction" or "RAG systems optimization").
2. **Configure Parameters**: Select the domain, timeframe (years back), system design category, and maximum papers per agent.
3. **Start Research**: Click **Start Research Pipeline**. The system will kick off 3 concurrent agents. You can monitor their progress in the UI.
4. **Methodology & Architecture**: Once research is gathered, the agents synthesize a master methodology and an architecture diagram.
5. **Download Report**: Finally, the system generates a comprehensive report. You can review it on the page or download it as **Markdown** or **PDF**.

## 📁 Repository Structure

- `app/` - Contains the Streamlit frontend (`streamlit_app.py`).
- `agents/` - Individual agent definitions (`research_agent.py`, `invoice_agent.py`, `visualizer_agent.py`, etc.).
- `orchestrator/` - Pipeline validation and logic connecting agents.
- `output/` - Generated PDF and Markdown reports.
- `outputs/` - Generated visual artifacts and diagrams.
- `pdf/` - Utilities for converting markdown to PDF.

## 📄 License
This project is open-source. See the LICENSE file for more details.
