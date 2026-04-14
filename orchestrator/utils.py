# orchestrator/utils.py
import json
import uuid
from datetime import datetime, timezone

def now_iso_z():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def make_agent_id(prefix: str, role: str):
    return f"{prefix}_{role}_{uuid.uuid4().hex[:8]}"

def load_prompt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()
