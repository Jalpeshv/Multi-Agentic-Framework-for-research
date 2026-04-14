# tests/validate_agent_outputs.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "example_output_sample.json"

def test_sample_exists():
    assert SAMPLE.exists()

def test_research_json_schema():
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert "research_outputs" in data
    res = data["research_outputs"]
    assert isinstance(res, list) and len(res) == 3
    for r in res:
        for field in ["agent_id", "role", "topic", "domain", "summary", "word_count",
                      "top_papers", "citations", "key_methods", "datasets_used", "open_problems",
                      "search_terms", "retrieved_on", "confidence"]:
            assert field in r
        assert 200 <= r["word_count"] <= 250

def test_invoice_json_schema():
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    invoice = data.get("invoice_output")
    assert invoice is not None
    for field in ["invoice_id", "topic", "domain", "cover_page_markdown", "table_of_contents_markdown", "sections_markdown", "references_markdown", "pdf_metadata"]:
        assert field in invoice
