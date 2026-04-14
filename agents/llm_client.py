# agents/llm_client.py
"""
Unified LLM Client — Multi-Key Groq Pool + Ollama Fallback.

DESIGN:
  • Groq (cloud) → Primary for ALL tasks (fast, ~2s per call)
  • Ollama (local) → Fallback when Groq hits rate limits

Multi-key pool: Add GROQ_API_KEY_1, _2, _3 to .env for 3x throughput.
Falls back to single GROQ_API_KEY if numbered keys aren't set.
"""

import os
import re
import sys
import json
import time
import threading
import requests
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)

# ═══════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

ALLOWED_GROQ_MODELS = {
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
}

# ═══════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════

def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from DeepSeek-R1 output."""
    if not text:
        return ""
    return re.sub(r'<think>[\s\S]*?</think>', '', text).strip()


def _resolve_groq_model(requested: str | None) -> str:
    """Validate a Groq model name. Returns safe default if invalid."""
    if requested and requested in ALLOWED_GROQ_MODELS:
        return requested
    if requested:
        low = requested.lower()
        if "qwen" in low:
            return "llama-3.1-8b-instant"
        if "mixtral" in low:
            return "gemma2-9b-it"
        if "70b" in low:
            return "llama-3.3-70b-versatile"
        print(f"WARNING: [llm_client] Unknown Groq model '{requested}', using default", file=sys.stderr)
    return GROQ_DEFAULT_MODEL


# ═══════════════════════════════════════════════════
#  OLLAMA CLIENT (Local — Fallback Only)
# ═══════════════════════════════════════════════════

def ollama_available() -> bool:
    """Check if Ollama server is reachable."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def call_ollama(
    prompt: str,
    system_msg: str = "You are a helpful AI research assistant. Output strict JSON only.",
    model: str | None = None,
    temperature: float = 0.3,
    max_retries: int = 2,
    timeout: int = 300,
    include_think: bool = False,
) -> str:
    """
    Call Ollama's local API. Fallback for when Groq is rate-limited.
    """
    model = model or OLLAMA_MODEL
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": include_think,   # False = skip reasoning (fast), True = show full chain
        "options": {
            "temperature": temperature,
            "num_predict": 4096,
        },
    }
    
    last_error = None
    for attempt in range(max_retries):
        try:
            print(f"DEBUG: [ollama] Calling {model} (attempt {attempt+1}/{max_retries})", file=sys.stderr)
            
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                timeout=timeout,
            )
            
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                print(f"WARNING: [ollama] {last_error}", file=sys.stderr)
                time.sleep(2)
                continue
            
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            
            if not content or not content.strip():
                last_error = "Empty response from Ollama"
                print(f"WARNING: [ollama] Empty response", file=sys.stderr)
                time.sleep(1)
                continue
            
            # Strip DeepSeek-R1 think tags unless explicitly requested
            if include_think:
                return content
            
            cleaned = strip_think_tags(content)
            if not cleaned.strip():
                last_error = "Response was only <think> tags, no actual output"
                print(f"WARNING: [ollama] {last_error}", file=sys.stderr)
                time.sleep(1)
                continue
            
            return cleaned
            
        except requests.exceptions.Timeout:
            last_error = f"Timeout after {timeout}s"
            print(f"WARNING: [ollama] {last_error}", file=sys.stderr)
        except requests.exceptions.ConnectionError:
            last_error = "Cannot connect to Ollama. Is 'ollama serve' running?"
            print(f"WARNING: [ollama] {last_error}", file=sys.stderr)
            time.sleep(3)
        except Exception as e:
            last_error = str(e)
            print(f"WARNING: [ollama] Unexpected error: {last_error}", file=sys.stderr)
            time.sleep(2)
    
    raise RuntimeError(f"Ollama call failed after {max_retries} attempts. Last error: {last_error}")


# ═══════════════════════════════════════════════════
#  GROQ KEY POOL — Round-Robin Multi-Key System
#  3 keys × 6,000 TPM = 18,000 TPM total
#  3 keys × 30 RPM  = 90 RPM total
# ═══════════════════════════════════════════════════

class GroqKeyPool:
    """Thread-safe round-robin Groq API key pool.
    
    Reads GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3 from .env.
    Falls back to single GROQ_API_KEY if numbered keys aren't found.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._keys = []
        self._clients = {}
        self._index = 0
        self._rate_limited = {}
        
        # Load numbered keys: GROQ_API_KEY_1, _2, _3, ...
        for i in range(1, 10):
            key = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
            if key:
                self._keys.append(key)
        
        # Fallback: single GROQ_API_KEY
        if not self._keys:
            single = os.getenv("GROQ_API_KEY", "").strip()
            if single:
                self._keys.append(single)
        
        print(f"DEBUG: [groq-pool] Loaded {len(self._keys)} API key(s)", file=sys.stderr)
    
    def _get_client(self, key):
        if key not in self._clients:
            try:
                from groq import Groq
                self._clients[key] = Groq(api_key=key)
            except Exception as e:
                print(f"WARNING: [groq-pool] Client init failed: {e}", file=sys.stderr)
                return None
        return self._clients[key]
    
    def get_next(self):
        """Get next (client, key_label) via round-robin, skipping rate-limited keys."""
        with self._lock:
            if not self._keys:
                return None, "no_keys"
            now = time.time()
            for _ in range(len(self._keys)):
                idx = self._index % len(self._keys)
                key = self._keys[idx]
                label = f"key_{idx + 1}"
                self._index += 1
                if key in self._rate_limited and now < self._rate_limited[key]:
                    continue
                self._rate_limited.pop(key, None)
                client = self._get_client(key)
                if client:
                    return client, label
            
            # All keys rate-limited — wait for earliest to expire
            if self._rate_limited:
                earliest = min(self._rate_limited, key=self._rate_limited.get)
                wait = max(1, int(self._rate_limited[earliest] - now))
                print(f"DEBUG: [groq-pool] ALL keys rate-limited. Waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                self._rate_limited.pop(earliest, None)
                client = self._get_client(earliest)
                if client:
                    return client, f"key_{self._keys.index(earliest) + 1}"
            return None, "all_failed"
    
    def mark_rate_limited(self, key_label, cooldown=20):
        """Mark a key as rate-limited for cooldown seconds."""
        with self._lock:
            try:
                idx = int(key_label.split("_")[1]) - 1
            except (IndexError, ValueError):
                idx = 0
            if 0 <= idx < len(self._keys):
                self._rate_limited[self._keys[idx]] = time.time() + cooldown
                print(f"DEBUG: [groq-pool] {key_label} rate-limited for {cooldown}s", file=sys.stderr)
    
    @property
    def available(self):
        return len(self._keys) > 0
    
    @property
    def key_count(self):
        return len(self._keys)


# Global pool instance
_groq_pool = GroqKeyPool()


def _get_groq_client():
    """Legacy compatibility — returns next available client from pool."""
    client, _ = _groq_pool.get_next()
    return client


def call_groq(
    prompt: str,
    system_msg: str = "You are a helpful AI research assistant.",
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4000,
    timeout: int = 90,
    max_retries: int = 3,
) -> str:
    """Call Groq cloud API using multi-key pool. Auto-rotates on rate limits."""
    if not _groq_pool.available:
        raise RuntimeError("No Groq API keys found. Add GROQ_API_KEY_1, _2, _3 to .env")
    
    safe_model = _resolve_groq_model(model or GROQ_DEFAULT_MODEL)
    last_error = None
    
    for attempt in range(max_retries):
        client, key_label = _groq_pool.get_next()
        if not client:
            raise RuntimeError("No Groq clients available. Check API keys in .env")
        
        try:
            print(f"DEBUG: [groq] {key_label} -> {safe_model} (attempt {attempt+1}/{max_retries})", file=sys.stderr)
            
            completion = client.chat.completions.create(
                model=safe_model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            
            content = completion.choices[0].message.content
            if content and content.strip():
                return strip_think_tags(content)
            
            last_error = "Empty response"
            print(f"WARNING: [groq] Empty from {safe_model} via {key_label}", file=sys.stderr)
            
        except Exception as e:
            last_error = str(e)
            err_str = str(e)
            print(f"WARNING: [groq] {key_label} error: {err_str[:200]}", file=sys.stderr)
            
            # Rate limit — mark this key, rotate to next
            if "429" in err_str or "rate limit" in err_str.lower():
                _groq_pool.mark_rate_limited(key_label, cooldown=20)
                continue
            
            # Request too large — can't fix by rotating
            if "413" in err_str or "Request too large" in err_str:
                raise RuntimeError(f"Prompt too large for Groq: {err_str[:200]}")
            
            time.sleep(2)
    
    raise RuntimeError(f"Groq failed after {max_retries} attempts. Last error: {last_error}")


# ═══════════════════════════════════════════════════
#  SMART ROUTER — Groq-first, Ollama fallback
# ═══════════════════════════════════════════════════

OLLAMA_FALLBACK_ROLES = {
    "worker", "research", "methodology", "visualizer",
}

def call_llm(
    prompt: str,
    role: str = "worker",
    system_msg: str = "You are a helpful AI research assistant. Output strict JSON only.",
    temperature: float = 0.3,
    max_tokens: int = 4000,
    groq_model: str | None = None,
    ollama_model: str | None = None,
    timeout: int = 300,
    include_think: bool = False,
) -> str:
    """
    Smart router: Groq-first for ALL roles (fast ~2s).
    On rate limit: waits 15s and retries Groq (faster than Ollama fallback).
    Ollama is absolute last resort only.
    """
    max_router_retries = 3
    
    for router_attempt in range(max_router_retries):
        try:
            return call_groq(
                prompt=prompt,
                system_msg=system_msg,
                model=groq_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=min(timeout, 90),
            )
        except RuntimeError as e:
            err_str = str(e)
            
            if "429" in err_str or "rate limit" in err_str.lower():
                # Wait and retry Groq (15s is much faster than Ollama's 60-300s)
                if router_attempt < max_router_retries - 1:
                    wait = 15
                    print(f"DEBUG: [router] All Groq keys rate-limited, waiting {wait}s (attempt {router_attempt+1}/{max_router_retries})", file=sys.stderr)
                    time.sleep(wait)
                    continue
                
                # Final attempt failed — try Ollama as absolute last resort
                if role.lower() in OLLAMA_FALLBACK_ROLES and ollama_available():
                    print(f"DEBUG: [router] Groq exhausted, last resort: Ollama for {role}", file=sys.stderr)
                    return call_ollama(
                        prompt=prompt,
                        system_msg=system_msg,
                        model=ollama_model,
                        temperature=temperature,
                        timeout=min(timeout, 120),  # Cap Ollama at 2 min
                        include_think=include_think,
                    )
            raise

