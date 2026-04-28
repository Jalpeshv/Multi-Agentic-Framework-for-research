# agents/llm_client.py
"""
Unified LLM Client — Multi-Key OpenRouter Pool + Ollama Fallback.

DESIGN:
  • OpenRouter (cloud) → Primary for ALL tasks (OpenAI-compatible API)
  • Ollama (local) → Fallback when OpenRouter hits rate limits

Multi-key pool: Add OPENROUTER_API_KEY_1, _2, _3 to .env for 3x throughput.
Falls back to single OPENROUTER_API_KEY if numbered keys aren't set.
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

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Model mapping: old Groq model names → OpenRouter equivalents
MODEL_MAP = {
    "llama-3.3-70b-versatile": "google/gemini-2.5-flash",
    "llama-3.1-8b-instant": "google/gemini-2.5-flash",
    "gemma2-9b-it": "google/gemini-2.5-flash",
    # Direct OpenRouter model IDs pass through unchanged
}

# ═══════════════════════════════════════════════════
#  ROLE-BASED MODEL SPECIALIZATION (ALL FREE TIER)
#  Each agent type gets the optimal FREE model for its task.
#  Total cost: $0.00 — all models are free on OpenRouter.
# ═══════════════════════════════════════════════════
MODEL_ROLES = {
    # Research agents: Use different free models per role to SPREAD rate limits
    # Each agent hits a DIFFERENT model = parallel without rate conflicts
    "research":         "openai/gpt-oss-120b:free",                  # 120B, 131K ctx, 131K out
    "historical":       "openai/gpt-oss-120b:free",                  # Best for historical analysis
    "state_of_the_art": "nvidia/nemotron-3-super-120b-a12b:free",    # 120B, 262K ctx, 262K out
    "ongoing_emerging": "google/gemma-4-31b-it:free",                # 31B, 262K ctx, 32K out
    # Methodology: Deep reasoning with large output
    "methodology":      "nvidia/nemotron-3-super-120b-a12b:free",    # 120B, 262K max output
    "worker":           "google/gemma-4-31b-it:free",                # 31B, fast + capable
    # Report/Invoice: MAXIMUM output length for detailed PhD-grade reports
    "invoice":          "nvidia/nemotron-3-super-120b-a12b:free",    # 120B, 262K max output!
    "report":           "nvidia/nemotron-3-super-120b-a12b:free",    # Same — huge output capacity
    "orchestrator":     "openai/gpt-oss-120b:free",                  # 120B, great synthesis
    # Evaluator: fast + free
    "evaluator":        "google/gemma-4-31b-it:free",                # 31B, fast scoring
    # Architecture design: good quality
    "visualizer":       "google/gemma-4-31b-it:free",                # 31B, fast design
    # Search query generation: fast + cheap
    "search":           "google/gemma-4-31b-it:free",                # Fast query gen
}

# Fallback chain: if primary model fails, try these in order
FREE_FALLBACK_CHAIN = [
    "nvidia/nemotron-3-super-120b-a12b:free",    # 120B, 262K output
    "openai/gpt-oss-120b:free",                  # 120B, 131K output
    "google/gemma-4-31b-it:free",                # 31B, 32K output
    "z-ai/glm-4.5-air:free",                     # 96K max output
    "qwen/qwen3-coder:free",                     # 262K context
    "nousresearch/hermes-3-llama-3.1-405b:free", # 405B params!
    "meta-llama/llama-3.3-70b-instruct:free",    # 70B fallback
    "google/gemma-3-27b-it:free",                # 27B fallback
]

ALLOWED_MODELS = set(MODEL_MAP.keys()) | set(MODEL_MAP.values()) | set(MODEL_ROLES.values()) | set(FREE_FALLBACK_CHAIN)

# ═══════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════

def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from DeepSeek-R1 output."""
    if not text:
        return ""
    return re.sub(r'<think>[\s\S]*?</think>', '', text).strip()


def _resolve_model(requested: str | None, role: str | None = None) -> str:
    """Map a requested model name to an OpenRouter model ID.
    Priority: explicit request > role-based specialization > default.
    """
    # If explicitly requesting a model with '/' (OpenRouter ID), use it
    if requested and "/" in requested:
        return requested
    
    # If explicitly requesting a legacy Groq model name, map it
    if requested and requested in MODEL_MAP:
        return MODEL_MAP[requested]
    
    # Role-based specialization: pick the best model for this agent's job
    if role:
        role_lower = role.lower()
        for role_key, model_id in MODEL_ROLES.items():
            if role_key in role_lower:
                return model_id
    
    # Fuzzy matching for legacy model names
    if requested:
        low = requested.lower()
        if "qwen" in low:
            return "google/gemini-2.5-flash"
        if "mixtral" in low:
            return "google/gemini-2.5-flash"
        if "70b" in low:
            return "google/gemini-2.5-flash"
        if "8b" in low:
            return "google/gemini-2.5-flash"
        print(f"WARNING: [llm_client] Unknown model '{requested}', using default", file=sys.stderr)
    
    return OPENROUTER_DEFAULT_MODEL


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
    Call Ollama's local API. Fallback for when OpenRouter is rate-limited.
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
#  OPENROUTER KEY POOL — Round-Robin Multi-Key System
# ═══════════════════════════════════════════════════

class OpenRouterKeyPool:
    """Thread-safe round-robin OpenRouter API key pool.
    
    Reads OPENROUTER_API_KEY_1, _2, _3 from .env.
    Falls back to single OPENROUTER_API_KEY if numbered keys aren't found.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._keys = []
        self._index = 0
        self._rate_limited = {}
        
        # Load numbered keys: OPENROUTER_API_KEY_1, _2, _3, ...
        for i in range(1, 10):
            key = os.getenv(f"OPENROUTER_API_KEY_{i}", "").strip()
            if key:
                self._keys.append(key)
        
        # Fallback: single OPENROUTER_API_KEY
        if not self._keys:
            single = os.getenv("OPENROUTER_API_KEY", "").strip()
            if single:
                self._keys.append(single)
        
        print(f"DEBUG: [openrouter-pool] Loaded {len(self._keys)} API key(s)", file=sys.stderr)
    
    def get_specific_key(self, index: int):
        """Force use of a specific key index (0-based) for rate limit isolation."""
        with self._lock:
            if not self._keys:
                return None, "no_keys"
                
            if 0 <= index < len(self._keys):
                raw_key = self._keys[index]
                label = f"key_{index + 1}"
                
                now = time.time()
                if raw_key in self._rate_limited and now < self._rate_limited[raw_key]:
                    wait = max(1, int(self._rate_limited[raw_key] - now))
                    print(f"DEBUG: [openrouter-pool] {label} is on cooldown. Waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    self._rate_limited.pop(raw_key, None)
                    
                return raw_key, label
            
            # If the index is out of bounds, fallback
            return None, "fallback"
    
    def get_next(self):
        """Get next (key, key_label) via round-robin, skipping rate-limited keys."""
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
                return key, label
            
            # All keys rate-limited — wait for earliest to expire
            if self._rate_limited:
                earliest = min(self._rate_limited, key=self._rate_limited.get)
                wait = max(1, int(self._rate_limited[earliest] - now))
                print(f"DEBUG: [openrouter-pool] ALL keys rate-limited. Waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                self._rate_limited.pop(earliest, None)
                return earliest, f"key_{self._keys.index(earliest) + 1}"
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
                print(f"DEBUG: [openrouter-pool] {key_label} rate-limited for {cooldown}s", file=sys.stderr)
    
    @property
    def available(self):
        return len(self._keys) > 0
    
    @property
    def key_count(self):
        return len(self._keys)


# Global pool instance
_openrouter_pool = OpenRouterKeyPool()


def _get_openrouter_client():
    """Legacy compatibility — returns next available API key from pool."""
    key, _ = _openrouter_pool.get_next()
    return key


# Legacy aliases for backward compatibility
_get_groq_client = _get_openrouter_client


def _call_openrouter_api(
    api_key: str,
    model: str,
    messages: list,
    temperature: float = 0.3,
    max_tokens: int = 4000,
    timeout: int = 90,
    frequency_penalty: float = 0.0,
) -> str:
    """Make a raw OpenRouter API call (OpenAI-compatible endpoint)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://ai-research-assistant.local",
        "X-Title": "AI Research Assistant",
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "frequency_penalty": frequency_penalty,
    }
    
    resp = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    
    if resp.status_code == 429:
        raise RuntimeError(f"429 Rate limit exceeded")
    
    if resp.status_code == 413:
        raise RuntimeError(f"413 Request too large: {resp.text[:200]}")
    
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    
    data = resp.json()
    
    # Check for OpenRouter error responses
    if "error" in data:
        error_msg = data["error"].get("message", str(data["error"]))
        if "rate" in error_msg.lower() or "429" in error_msg:
            raise RuntimeError(f"429 Rate limit: {error_msg}")
        raise RuntimeError(f"OpenRouter error: {error_msg}")
    
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("No choices in response")
    
    content = choices[0].get("message", {}).get("content", "")
    return content


def call_groq(
    prompt: str,
    system_msg: str = "You are a helpful AI research assistant.",
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4000,
    timeout: int = 90,
    max_retries: int = 3,
    frequency_penalty: float = 0.0,
    agent_role: str | None = None,
) -> str:
    """Call OpenRouter API using multi-key pool. Auto-rotates on rate limits.
    
    NOTE: Function name kept as 'call_groq' for backward compatibility with
    all existing agent code. Internally routes to OpenRouter.
    """
    if not _openrouter_pool.available:
        raise RuntimeError("No OpenRouter API keys found. Add OPENROUTER_API_KEY_1, _2, _3 to .env")
    
    safe_model = _resolve_model(model, role=agent_role)  # model=None lets role take priority
    last_error = None
    
    # Dedicated Key Routing Logic
    specific_key_idx = -1
    if agent_role:
        role_lower = agent_role.lower()
        if "historical" in role_lower:
            specific_key_idx = 0
        elif "state_of_the_art" in role_lower:
            specific_key_idx = 1
        elif "ongoing_emerging" in role_lower:
            specific_key_idx = 2
            
    models_to_try = [safe_model]
    for fm in FREE_FALLBACK_CHAIN:
        if fm not in models_to_try:
            models_to_try.append(fm)
            
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ]
    
    last_error = "Unknown error"
    
    for current_model in models_to_try:
        # Try each model up to max_retries times (rotating keys)
        for attempt in range(max_retries):
            if specific_key_idx >= 0:
                api_key, key_label = _openrouter_pool.get_specific_key(specific_key_idx)
            else:
                api_key, key_label = _openrouter_pool.get_next()
                
            if not api_key:
                raise RuntimeError("No OpenRouter clients available. Check API keys in .env")
            
            try:
                print(f"DEBUG: [openrouter] {key_label} -> {current_model} (attempt {attempt+1}/{max_retries})", file=sys.stderr)
                
                content = _call_openrouter_api(
                    api_key=api_key,
                    model=current_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    frequency_penalty=frequency_penalty,
                )
                
                if content and content.strip():
                    return strip_think_tags(content)
                
                last_error = "Empty response"
                print(f"WARNING: [openrouter] Empty from {current_model} via {key_label}", file=sys.stderr)
                
            except Exception as e:
                last_error = str(e)
                err_str = str(e)
                print(f"WARNING: [openrouter] {key_label} error: {err_str[:200]}", file=sys.stderr)
                
                # Rate limit — mark this key, rotate to next
                if "429" in err_str or "rate limit" in err_str.lower() or "502" in err_str or "overloaded" in err_str.lower():
                    _openrouter_pool.mark_rate_limited(key_label, cooldown=20)
                    continue
                
                # Request too large — can't fix by rotating or falling back
                if "413" in err_str or "Request too large" in err_str:
                    raise RuntimeError(f"Prompt too large for OpenRouter: {err_str[:200]}")
                
                time.sleep(2)
                
        # If we exhausted retries for this model, we loop to the next model in the fallback chain!
        print(f"DEBUG: [openrouter] Model {current_model} exhausted, trying fallback...", file=sys.stderr)
    
    raise RuntimeError(f"OpenRouter failed absolutely all fallback models. Last error: {last_error}")


# ═══════════════════════════════════════════════════
#  SMART ROUTER — OpenRouter-first, Ollama fallback
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
    frequency_penalty: float = 0.0,
    agent_role: str | None = None,
) -> str:
    """
    Smart router: OpenRouter-first for ALL roles (fast ~2s).
    On rate limit: waits 15s and retries OpenRouter (faster than Ollama fallback).
    Ollama is absolute last resort only.
    """
    max_router_retries = 3
    
    # Map role to agent_role if missing (for legacy compatibility)
    if not agent_role and role not in ["worker", "evaluator", "orchestrator", "visualizer", "invoice", "methodology"]:
        agent_role = role
        
    for router_attempt in range(max_router_retries):
        try:
            return call_groq(
                prompt=prompt,
                system_msg=system_msg,
                model=groq_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=min(timeout, 150),
                frequency_penalty=frequency_penalty,
                agent_role=agent_role,
            )
        except RuntimeError as e:
            err_str = str(e)
            
            if "429" in err_str or "rate limit" in err_str.lower():
                # Wait and retry OpenRouter (15s is much faster than Ollama's 60-300s)
                if router_attempt < max_router_retries - 1:
                    wait = 15
                    print(f"DEBUG: [router] All OpenRouter keys rate-limited, waiting {wait}s (attempt {router_attempt+1}/{max_router_retries})", file=sys.stderr)
                    time.sleep(wait)
                    continue
                
            # If it's the final attempt OR a non-retriable error (413, 503, timeout), try Ollama as absolute last resort
            if role.lower() in OLLAMA_FALLBACK_ROLES and ollama_available():
                print(f"DEBUG: [router] OpenRouter failed, last resort: Ollama for {role}. Error: {err_str[:150]}", file=sys.stderr)
                return call_ollama(
                    prompt=prompt,
                    system_msg=system_msg,
                    model=ollama_model,
                    temperature=temperature,
                    timeout=min(timeout, 200),  # Cap Ollama at >3 min
                    include_think=include_think,
                )
            raise
