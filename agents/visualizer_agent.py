"""
Visualizer Agent — PaperBanana (OpenRouter) primary, Pillow ByteByteGo fallback.
Generates: Architecture, Workflow, Methods diagrams + per-methodology flowcharts.
NO MERMAID. All output is PNG images.
Every generation uses a RANDOMIZED visual theme so outputs always look fresh.
"""
import os
import sys
import re
import time
import json as _json
import importlib.util
import base64
import asyncio
import shutil
import math
import random
import hashlib
import textwrap
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

# OpenRouter key setup for PaperBanana
if not os.getenv("OPENROUTER_API_KEY") and os.getenv("PAPERBANANA_OPENROUTER_API_KEY"):
    os.environ["OPENROUTER_API_KEY"] = os.getenv("PAPERBANANA_OPENROUTER_API_KEY")

# ═════════════════════════════════════════════════════════════════════
#  DRAWING PRIMITIVES
# ═════════════════════════════════════════════════════════════════════

def _get_font(size, bold=False):
    from PIL import ImageFont
    candidates = (
        ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
         "C:/Windows/Fonts/calibrib.ttf"] if bold else []
    ) + ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
         "C:/Windows/Fonts/calibri.ttf"]
    for fp in candidates:
        if os.path.exists(fp):
            try: return ImageFont.truetype(fp, size)
            except: pass
    return ImageFont.load_default()

def _hex(c): c=c.lstrip('#'); return tuple(int(c[i:i+2],16) for i in(0,2,4))

def _is_dark_bg(bg_color):
    """Check if background is dark using luminance. Returns True for dark backgrounds."""
    r,g,b = _hex(bg_color)
    lum = 0.299*r + 0.587*g + 0.114*b
    return lum < 128

def _gradient(draw, bbox, top, bot):
    x1,y1,x2,y2=bbox; t=_hex(top); b=_hex(bot); h=max(y2-y1,1)
    for y in range(int(y1),int(y2)):
        r=((y-y1)/h); draw.line([(x1,y),(x2,y)],fill=tuple(int(t[i]+(b[i]-t[i])*r) for i in range(3)))

def _arrow(draw, s, e, color="#58a6ff", w=4, hs=18):
    draw.line([s,e],fill=color,width=w)
    dx,dy=e[0]-s[0],e[1]-s[1]; L=max(math.sqrt(dx*dx+dy*dy),1)
    ux,uy=dx/L,dy/L; px,py=-uy,ux
    draw.polygon([e,(e[0]-hs*ux+hs*.4*px,e[1]-hs*uy+hs*.4*py),
                  (e[0]-hs*ux-hs*.4*px,e[1]-hs*uy-hs*.4*py)],fill=color)

def _dashed(draw, s, e, color="#8b949e", w=2, dl=12, gl=8):
    dx,dy=e[0]-s[0],e[1]-s[1]; L=math.sqrt(dx*dx+dy*dy)
    if L==0: return
    ux,uy=dx/L,dy/L; p=0
    while p<L:
        se=min(p+dl,L)
        draw.line([(s[0]+ux*p,s[1]+uy*p),(s[0]+ux*se,s[1]+uy*se)],fill=color,width=w)
        p+=dl+gl


ALLOWED_OPENROUTER_MODELS = {
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
    "meta-llama/llama-3.3-70b-instruct",
    # Legacy Groq names (mapped automatically)
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "gemma2-9b-it",
}

DEFAULT_OPENROUTER_MODEL = "google/gemini-2.5-flash"


def _resolve_openrouter_model(requested: str | None, default: str = DEFAULT_OPENROUTER_MODEL) -> str:
    MODEL_MAP = {
        "llama-3.3-70b-versatile": "google/gemini-2.5-flash",
        "llama-3.1-8b-instant": "google/gemini-2.5-flash",
        "gemma2-9b-it": "google/gemini-2.5-flash",
    }
    if not requested:
        return default
    if "/" in requested:  # Already an OpenRouter model ID
        return requested
    if requested in MODEL_MAP:
        return MODEL_MAP[requested]
    if "llama" in requested.lower() and "70b" in requested.lower():
        return "google/gemini-2.5-flash"
    if "8b" in requested.lower():
        return "google/gemini-2.5-flash"
    print(f"WARNING: [visualizer] Unsupported model '{requested}', using '{default}'", file=sys.stderr)
    return default


def _paperbanana_available() -> bool:
    return importlib.util.find_spec("paperbanana") is not None

# Color palettes — DYNAMIC THEME ENGINE
# ═══════════════════════════════════════════════════════════════
# Each run picks a random theme so outputs never look the same.
# ═══════════════════════════════════════════════════════════════

THEME_PALETTES = [
    # Theme 0: Dark Cyber (original)
    {
        "name": "Dark Cyber",
        "bg": "#0d1117", "bg2": "#161b22", "card": "#21262d", "border": "#30363d",
        "accent": "#58a6ff", "text": "#e6edf3", "muted": "#8b949e",
        "layer_colors": {
            "client":  {"fill":"#1a3a2a","bdr":"#3fb950","acc":"#3fb950","txt":"#7ee787","glow":"#238636"},
            "gateway": {"fill":"#3d2a1a","bdr":"#d29922","acc":"#d29922","txt":"#e3b341","glow":"#9e6a03"},
            "service": {"fill":"#1a2a3d","bdr":"#58a6ff","acc":"#58a6ff","txt":"#79c0ff","glow":"#1f6feb"},
            "ai_ml":   {"fill":"#2d1a3d","bdr":"#bc8cff","acc":"#bc8cff","txt":"#d2a8ff","glow":"#8957e5"},
            "data":    {"fill":"#3d1a1a","bdr":"#f85149","acc":"#f85149","txt":"#ff7b72","glow":"#da3633"},
            "infra":   {"fill":"#1a3d3d","bdr":"#3fb9b9","acc":"#3fb9b9","txt":"#7eeaea","glow":"#1b7b7b"},
        },
        "step_colors": [
            {"fill":"#1a3a2a","bdr":"#3fb950","acc":"#3fb950","txt":"#7ee787","glow":"#238636"},
            {"fill":"#3d2a1a","bdr":"#d29922","acc":"#d29922","txt":"#e3b341","glow":"#9e6a03"},
            {"fill":"#1a2a3d","bdr":"#58a6ff","acc":"#58a6ff","txt":"#79c0ff","glow":"#1f6feb"},
            {"fill":"#2d1a3d","bdr":"#bc8cff","acc":"#bc8cff","txt":"#d2a8ff","glow":"#8957e5"},
            {"fill":"#3d1a1a","bdr":"#f85149","acc":"#f85149","txt":"#ff7b72","glow":"#da3633"},
            {"fill":"#1a3d3d","bdr":"#3fb9b9","acc":"#3fb9b9","txt":"#7eeaea","glow":"#1b7b7b"},
        ],
        "grid_dot": "#181d27", "title_accent_bar": True,
        "card_radius": 18, "card_shadow": "#08090d",
        "bg_pattern": "dots",  # dots | grid | diagonal | hexagon | none
        "layout_style": "horizontal_layers",  # horizontal_layers | vertical_columns | radial | zigzag
    },
    # Theme 1: Clean White (ByteByteGo Classic)
    {
        "name": "Clean White",
        "bg": "#FFFFFF", "bg2": "#F8F9FA", "card": "#FFFFFF", "border": "#E0E0E0",
        "accent": "#4285F4", "text": "#202124", "muted": "#5F6368",
        "layer_colors": {
            "client":  {"fill":"#E8F5E9","bdr":"#34A853","acc":"#34A853","txt":"#1B5E20","glow":"#A5D6A7"},
            "gateway": {"fill":"#FFF3E0","bdr":"#FB8C00","acc":"#FB8C00","txt":"#E65100","glow":"#FFCC80"},
            "service": {"fill":"#E3F2FD","bdr":"#4285F4","acc":"#4285F4","txt":"#0D47A1","glow":"#90CAF9"},
            "ai_ml":   {"fill":"#F3E5F5","bdr":"#9C27B0","acc":"#9C27B0","txt":"#4A148C","glow":"#CE93D8"},
            "data":    {"fill":"#FFEBEE","bdr":"#E53935","acc":"#E53935","txt":"#B71C1C","glow":"#EF9A9A"},
            "infra":   {"fill":"#E0F7FA","bdr":"#00ACC1","acc":"#00ACC1","txt":"#006064","glow":"#80DEEA"},
        },
        "step_colors": [
            {"fill":"#E8F5E9","bdr":"#34A853","acc":"#34A853","txt":"#1B5E20","glow":"#A5D6A7"},
            {"fill":"#FFF3E0","bdr":"#FB8C00","acc":"#FB8C00","txt":"#E65100","glow":"#FFCC80"},
            {"fill":"#E3F2FD","bdr":"#4285F4","acc":"#4285F4","txt":"#0D47A1","glow":"#90CAF9"},
            {"fill":"#F3E5F5","bdr":"#9C27B0","acc":"#9C27B0","txt":"#4A148C","glow":"#CE93D8"},
            {"fill":"#FFEBEE","bdr":"#E53935","acc":"#E53935","txt":"#B71C1C","glow":"#EF9A9A"},
            {"fill":"#E0F7FA","bdr":"#00ACC1","acc":"#00ACC1","txt":"#006064","glow":"#80DEEA"},
        ],
        "grid_dot": "#F0F0F0", "title_accent_bar": False,
        "card_radius": 12, "card_shadow": "#E8E8E8",
        "bg_pattern": "grid",
        "layout_style": "horizontal_layers",
    },
    # Theme 2: Midnight Ocean
    {
        "name": "Midnight Ocean",
        "bg": "#0A192F", "bg2": "#112240", "card": "#1D3461", "border": "#2E4A7A",
        "accent": "#64FFDA", "text": "#CCD6F6", "muted": "#8892B0",
        "layer_colors": {
            "client":  {"fill":"#0A2E2E","bdr":"#64FFDA","acc":"#64FFDA","txt":"#A8FFF0","glow":"#1A6B5A"},
            "gateway": {"fill":"#2E1A0A","bdr":"#FFB347","acc":"#FFB347","txt":"#FFD699","glow":"#8B5E3C"},
            "service": {"fill":"#0A1A3D","bdr":"#57CBF5","acc":"#57CBF5","txt":"#A3E4FF","glow":"#1A5276"},
            "ai_ml":   {"fill":"#1A0A3D","bdr":"#BD93F9","acc":"#BD93F9","txt":"#D6B8FF","glow":"#6C3483"},
            "data":    {"fill":"#3D0A1A","bdr":"#FF6B6B","acc":"#FF6B6B","txt":"#FFB3B3","glow":"#8B2252"},
            "infra":   {"fill":"#0A2A2A","bdr":"#48D1CC","acc":"#48D1CC","txt":"#7FFFD4","glow":"#1A5B5B"},
        },
        "step_colors": [
            {"fill":"#0A2E2E","bdr":"#64FFDA","acc":"#64FFDA","txt":"#A8FFF0","glow":"#1A6B5A"},
            {"fill":"#2E1A0A","bdr":"#FFB347","acc":"#FFB347","txt":"#FFD699","glow":"#8B5E3C"},
            {"fill":"#0A1A3D","bdr":"#57CBF5","acc":"#57CBF5","txt":"#A3E4FF","glow":"#1A5276"},
            {"fill":"#1A0A3D","bdr":"#BD93F9","acc":"#BD93F9","txt":"#D6B8FF","glow":"#6C3483"},
            {"fill":"#3D0A1A","bdr":"#FF6B6B","acc":"#FF6B6B","txt":"#FFB3B3","glow":"#8B2252"},
            {"fill":"#0A2A2A","bdr":"#48D1CC","acc":"#48D1CC","txt":"#7FFFD4","glow":"#1A5B5B"},
        ],
        "grid_dot": "#0E2244", "title_accent_bar": True,
        "card_radius": 20, "card_shadow": "#050E1A",
        "bg_pattern": "diagonal",
        "layout_style": "vertical_columns",
    },
    # Theme 3: Warm Sunset
    {
        "name": "Warm Sunset",
        "bg": "#1A1423", "bg2": "#231C2E", "card": "#2D2438", "border": "#3E3350",
        "accent": "#FF6B9D", "text": "#F0E4F7", "muted": "#A89BBF",
        "layer_colors": {
            "client":  {"fill":"#2A1A22","bdr":"#FF6B9D","acc":"#FF6B9D","txt":"#FFB3CC","glow":"#8B3A5A"},
            "gateway": {"fill":"#2A2A1A","bdr":"#FFD93D","acc":"#FFD93D","txt":"#FFEB8A","glow":"#8B8B1A"},
            "service": {"fill":"#1A1A2A","bdr":"#6C5CE7","acc":"#6C5CE7","txt":"#A29BFE","glow":"#4834D4"},
            "ai_ml":   {"fill":"#2A1A2A","bdr":"#FD79A8","acc":"#FD79A8","txt":"#FFB8D0","glow":"#B33771"},
            "data":    {"fill":"#1A2A1A","bdr":"#00B894","acc":"#00B894","txt":"#55EFC4","glow":"#007A5E"},
            "infra":   {"fill":"#2A1F1A","bdr":"#E17055","acc":"#E17055","txt":"#FAB1A0","glow":"#8B4513"},
        },
        "step_colors": [
            {"fill":"#2A1A22","bdr":"#FF6B9D","acc":"#FF6B9D","txt":"#FFB3CC","glow":"#8B3A5A"},
            {"fill":"#2A2A1A","bdr":"#FFD93D","acc":"#FFD93D","txt":"#FFEB8A","glow":"#8B8B1A"},
            {"fill":"#1A1A2A","bdr":"#6C5CE7","acc":"#6C5CE7","txt":"#A29BFE","glow":"#4834D4"},
            {"fill":"#2A1A2A","bdr":"#FD79A8","acc":"#FD79A8","txt":"#FFB8D0","glow":"#B33771"},
            {"fill":"#1A2A1A","bdr":"#00B894","acc":"#00B894","txt":"#55EFC4","glow":"#007A5E"},
            {"fill":"#2A1F1A","bdr":"#E17055","acc":"#E17055","txt":"#FAB1A0","glow":"#8B4513"},
        ],
        "grid_dot": "#1E172A", "title_accent_bar": True,
        "card_radius": 22, "card_shadow": "#0D0A12",
        "bg_pattern": "hexagon",
        "layout_style": "zigzag",
    },
    # Theme 4: Arctic Frost
    {
        "name": "Arctic Frost",
        "bg": "#F0F4F8", "bg2": "#E2E8F0", "card": "#FFFFFF", "border": "#CBD5E0",
        "accent": "#2B6CB0", "text": "#2D3748", "muted": "#718096",
        "layer_colors": {
            "client":  {"fill":"#EBF8FF","bdr":"#3182CE","acc":"#3182CE","txt":"#2A4365","glow":"#BEE3F8"},
            "gateway": {"fill":"#FEFCBF","bdr":"#D69E2E","acc":"#D69E2E","txt":"#744210","glow":"#FAF089"},
            "service": {"fill":"#EBF4FF","bdr":"#4299E1","acc":"#4299E1","txt":"#2B6CB0","glow":"#90CDF4"},
            "ai_ml":   {"fill":"#FAF5FF","bdr":"#805AD5","acc":"#805AD5","txt":"#553C9A","glow":"#D6BCFA"},
            "data":    {"fill":"#FFF5F5","bdr":"#E53E3E","acc":"#E53E3E","txt":"#9B2C2C","glow":"#FEB2B2"},
            "infra":   {"fill":"#E6FFFA","bdr":"#38B2AC","acc":"#38B2AC","txt":"#234E52","glow":"#B2F5EA"},
        },
        "step_colors": [
            {"fill":"#EBF8FF","bdr":"#3182CE","acc":"#3182CE","txt":"#2A4365","glow":"#BEE3F8"},
            {"fill":"#FEFCBF","bdr":"#D69E2E","acc":"#D69E2E","txt":"#744210","glow":"#FAF089"},
            {"fill":"#EBF4FF","bdr":"#4299E1","acc":"#4299E1","txt":"#2B6CB0","glow":"#90CDF4"},
            {"fill":"#FAF5FF","bdr":"#805AD5","acc":"#805AD5","txt":"#553C9A","glow":"#D6BCFA"},
            {"fill":"#FFF5F5","bdr":"#E53E3E","acc":"#E53E3E","txt":"#9B2C2C","glow":"#FEB2B2"},
            {"fill":"#E6FFFA","bdr":"#38B2AC","acc":"#38B2AC","txt":"#234E52","glow":"#B2F5EA"},
        ],
        "grid_dot": "#E2E8F0", "title_accent_bar": False,
        "card_radius": 14, "card_shadow": "#CBD5E0",
        "bg_pattern": "none",
        "layout_style": "horizontal_layers",
    },
    # Theme 5: Neon Matrix
    {
        "name": "Neon Matrix",
        "bg": "#0B0B0F", "bg2": "#12121A", "card": "#1A1A2E", "border": "#2A2A44",
        "accent": "#00FF88", "text": "#E0FFE0", "muted": "#6B8F6B",
        "layer_colors": {
            "client":  {"fill":"#0A1F0A","bdr":"#00FF88","acc":"#00FF88","txt":"#88FFBB","glow":"#004422"},
            "gateway": {"fill":"#1F1A0A","bdr":"#FFD700","acc":"#FFD700","txt":"#FFEB99","glow":"#6B4E00"},
            "service": {"fill":"#0A0A1F","bdr":"#00BFFF","acc":"#00BFFF","txt":"#88DFFF","glow":"#004466"},
            "ai_ml":   {"fill":"#1F0A1F","bdr":"#FF00FF","acc":"#FF00FF","txt":"#FF88FF","glow":"#660066"},
            "data":    {"fill":"#1F0A0A","bdr":"#FF4444","acc":"#FF4444","txt":"#FF9999","glow":"#660000"},
            "infra":   {"fill":"#0A1F1F","bdr":"#00FFFF","acc":"#00FFFF","txt":"#88FFFF","glow":"#004444"},
        },
        "step_colors": [
            {"fill":"#0A1F0A","bdr":"#00FF88","acc":"#00FF88","txt":"#88FFBB","glow":"#004422"},
            {"fill":"#1F1A0A","bdr":"#FFD700","acc":"#FFD700","txt":"#FFEB99","glow":"#6B4E00"},
            {"fill":"#0A0A1F","bdr":"#00BFFF","acc":"#00BFFF","txt":"#88DFFF","glow":"#004466"},
            {"fill":"#1F0A1F","bdr":"#FF00FF","acc":"#FF00FF","txt":"#FF88FF","glow":"#660066"},
            {"fill":"#1F0A0A","bdr":"#FF4444","acc":"#FF4444","txt":"#FF9999","glow":"#660000"},
            {"fill":"#0A1F1F","bdr":"#00FFFF","acc":"#00FFFF","txt":"#88FFFF","glow":"#004444"},
        ],
        "grid_dot": "#0E0E16", "title_accent_bar": True,
        "card_radius": 8, "card_shadow": "#050508",
        "bg_pattern": "grid",
        "layout_style": "vertical_columns",
    },
    # Theme 6: Coral Reef
    {
        "name": "Coral Reef",
        "bg": "#FFFEF7", "bg2": "#FFF8E7", "card": "#FFFFFF", "border": "#E8DCC8",
        "accent": "#FF6F61", "text": "#3D3D3D", "muted": "#8B7D6B",
        "layer_colors": {
            "client":  {"fill":"#FFF0E5","bdr":"#FF8C69","acc":"#FF8C69","txt":"#CC4400","glow":"#FFD1B8"},
            "gateway": {"fill":"#FFF5CC","bdr":"#FFB800","acc":"#FFB800","txt":"#996E00","glow":"#FFE066"},
            "service": {"fill":"#E5F0FF","bdr":"#5B9BD5","acc":"#5B9BD5","txt":"#2C5F8A","glow":"#B8D6F0"},
            "ai_ml":   {"fill":"#F5E5FF","bdr":"#9B59B6","acc":"#9B59B6","txt":"#6C3483","glow":"#D7BDE2"},
            "data":    {"fill":"#FFE5E5","bdr":"#E74C3C","acc":"#E74C3C","txt":"#922B21","glow":"#F5B7B1"},
            "infra":   {"fill":"#E5FFF0","bdr":"#27AE60","acc":"#27AE60","txt":"#1E8449","glow":"#A9DFBF"},
        },
        "step_colors": [
            {"fill":"#FFF0E5","bdr":"#FF8C69","acc":"#FF8C69","txt":"#CC4400","glow":"#FFD1B8"},
            {"fill":"#FFF5CC","bdr":"#FFB800","acc":"#FFB800","txt":"#996E00","glow":"#FFE066"},
            {"fill":"#E5F0FF","bdr":"#5B9BD5","acc":"#5B9BD5","txt":"#2C5F8A","glow":"#B8D6F0"},
            {"fill":"#F5E5FF","bdr":"#9B59B6","acc":"#9B59B6","txt":"#6C3483","glow":"#D7BDE2"},
            {"fill":"#FFE5E5","bdr":"#E74C3C","acc":"#E74C3C","txt":"#922B21","glow":"#F5B7B1"},
            {"fill":"#E5FFF0","bdr":"#27AE60","acc":"#27AE60","txt":"#1E8449","glow":"#A9DFBF"},
        ],
        "grid_dot": "#F0EBE0", "title_accent_bar": False,
        "card_radius": 16, "card_shadow": "#DDD4C4",
        "bg_pattern": "dots",
        "layout_style": "zigzag",
    },
    # Theme 7: Deep Space
    {
        "name": "Deep Space",
        "bg": "#0F0C29", "bg2": "#1B1545", "card": "#252052", "border": "#3D3670",
        "accent": "#E040FB", "text": "#EDE7F6", "muted": "#9FA8DA",
        "layer_colors": {
            "client":  {"fill":"#1A0F33","bdr":"#E040FB","acc":"#E040FB","txt":"#F0A0FF","glow":"#6A1B9A"},
            "gateway": {"fill":"#33280F","bdr":"#FFB74D","acc":"#FFB74D","txt":"#FFE0B2","glow":"#8D6E63"},
            "service": {"fill":"#0F1A33","bdr":"#42A5F5","acc":"#42A5F5","txt":"#BBDEFB","glow":"#1565C0"},
            "ai_ml":   {"fill":"#1A0F2E","bdr":"#AB47BC","acc":"#AB47BC","txt":"#CE93D8","glow":"#7B1FA2"},
            "data":    {"fill":"#330F0F","bdr":"#EF5350","acc":"#EF5350","txt":"#EF9A9A","glow":"#C62828"},
            "infra":   {"fill":"#0F2E2E","bdr":"#26C6DA","acc":"#26C6DA","txt":"#80DEEA","glow":"#00838F"},
        },
        "step_colors": [
            {"fill":"#1A0F33","bdr":"#E040FB","acc":"#E040FB","txt":"#F0A0FF","glow":"#6A1B9A"},
            {"fill":"#33280F","bdr":"#FFB74D","acc":"#FFB74D","txt":"#FFE0B2","glow":"#8D6E63"},
            {"fill":"#0F1A33","bdr":"#42A5F5","acc":"#42A5F5","txt":"#BBDEFB","glow":"#1565C0"},
            {"fill":"#1A0F2E","bdr":"#AB47BC","acc":"#AB47BC","txt":"#CE93D8","glow":"#7B1FA2"},
            {"fill":"#330F0F","bdr":"#EF5350","acc":"#EF5350","txt":"#EF9A9A","glow":"#C62828"},
            {"fill":"#0F2E2E","bdr":"#26C6DA","acc":"#26C6DA","txt":"#80DEEA","glow":"#00838F"},
        ],
        "grid_dot": "#13103A", "title_accent_bar": True,
        "card_radius": 24, "card_shadow": "#08061A",
        "bg_pattern": "hexagon",
        "layout_style": "horizontal_layers",
    },
]

# ─── Track last used theme to avoid repeats ───
_LAST_THEME_FILE = PROJECT_ROOT / "outputs" / ".last_theme_idx"

def _pick_theme():
    """Pick a random theme that differs from the last used one."""
    last_idx = -1
    try:
        if _LAST_THEME_FILE.exists():
            last_idx = int(_LAST_THEME_FILE.read_text().strip())
    except: pass
    available = [i for i in range(len(THEME_PALETTES)) if i != last_idx]
    if not available:
        available = list(range(len(THEME_PALETTES)))
    chosen = random.choice(available)
    try:
        _LAST_THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LAST_THEME_FILE.write_text(str(chosen))
    except: pass
    return THEME_PALETTES[chosen]

def _draw_bg_pattern(draw, W, H, theme, title_h=0, footer_h=0):
    """Draw varied background patterns based on theme."""
    pattern = theme.get("bg_pattern", "none")
    dot_color = theme.get("grid_dot", "#181d27")
    y_start, y_end = title_h, H - footer_h
    
    if pattern == "dots":
        spacing = random.choice([40, 50, 60])
        for gx in range(0, W, spacing):
            for gy in range(y_start, y_end, spacing):
                r = random.choice([1, 2])
                draw.ellipse((gx, gy, gx+r*2, gy+r*2), fill=dot_color)
    elif pattern == "grid":
        spacing = random.choice([60, 80, 100])
        for gx in range(0, W, spacing):
            draw.line([(gx, y_start), (gx, y_end)], fill=dot_color, width=1)
        for gy in range(y_start, y_end, spacing):
            draw.line([(0, gy), (W, gy)], fill=dot_color, width=1)
    elif pattern == "diagonal":
        spacing = random.choice([50, 70, 90])
        for offset in range(-H, W + H, spacing):
            draw.line([(offset, y_start), (offset + H, y_end)], fill=dot_color, width=1)
    elif pattern == "hexagon":
        spacing = random.choice([60, 80])
        for row_i, gy in enumerate(range(y_start, y_end, spacing)):
            x_off = (spacing // 2) if row_i % 2 else 0
            for gx in range(x_off, W, spacing):
                r = 3
                for angle in range(6):
                    a1 = math.radians(60 * angle)
                    a2 = math.radians(60 * (angle + 1))
                    draw.line([(gx + r*math.cos(a1), gy + r*math.sin(a1)),
                               (gx + r*math.cos(a2), gy + r*math.sin(a2))], fill=dot_color, width=1)

# Legacy compatibility aliases — will be overridden per-render
BG="#0d1117"; BG2="#161b22"; CARD="#21262d"; BORDER="#30363d"; ACCENT="#58a6ff"
TEXT_C="#e6edf3"; MUTED="#8b949e"
LC = THEME_PALETTES[0]["layer_colors"]
STEP_COLORS = THEME_PALETTES[0]["step_colors"]

def _methods_from_research(research_outputs):
    m=set()
    for r in research_outputs:
        for x in r.get("key_methods",[]): m.add(x)
        for x in r.get("future_scope_methodologies",[]): m.add(x.get("scope_title",""))
    m.discard(""); return list(m)[:15]

def _text_w(draw, text, font):
    try: bb=draw.textbbox((0,0),text,font=font); return bb[2]-bb[0]
    except: return len(text)*10

def _text_h(draw, text, font):
    try: bb=draw.textbbox((0,0),text,font=font); return bb[3]-bb[1]
    except: return 20

def _center_text(draw, x, y, w, text, font, fill):
    tw=_text_w(draw,text,font); draw.text((x+w//2-tw//2, y), text, fill=fill, font=font)

# ═════════════════════════════════════════════════════════════════════
#  ARCHITECTURE DIAGRAM (ByteByteGo-style, LARGE fonts)
# ═════════════════════════════════════════════════════════════════════

def _build_arch_spec(topic, domain, research_outputs, system_category="General / Web App"):
    """Build architecture spec with DIFFERENT layouts per system category.
    Each category produces genuinely different layers, components, and connections."""
    methods = _methods_from_research(research_outputs)
    total_papers = sum(len(r.get("top_papers",[])) for r in research_outputs)
    base_stats = {"papers":total_papers,"methods":len(methods),"agents":3}

    # ─── Inject research-derived tech names into components ───
    m0 = methods[0][:18] if methods else "Multi-model"
    m1 = methods[1][:18] if len(methods)>1 else "Analysis"
    m2 = methods[2][:18] if len(methods)>2 else "Processing"

    # Remove Karpathy style override
    # if "karpathy" in topic.lower() or "karpathy" in domain.lower():
    #     system_category = "Deep Learning / Karpathy Style"
        
    CATEGORY_SPECS = {
        "General / Web App": {
            "title": topic.title(), "subtitle": f"Web Application Architecture | {domain.title()}",
            "layers": [
                {"name":"CLIENT LAYER","type":"client","components":[
                    {"name":"Web Dashboard","sub":"React / Streamlit","icon":"D"},
                    {"name":"REST API","sub":"FastAPI Endpoints","icon":"A"},
                    {"name":"Mobile Client","sub":"Cross-platform","icon":"M"}]},
                {"name":"API GATEWAY","type":"gateway","components":[

                    {"name":"Load Balancer","sub":"Round-robin","icon":"L"},
                    {"name":"Auth & Rate Limit","sub":"JWT + Throttle","icon":"S"},
                    {"name":"Request Router","sub":"Path-based","icon":"R"}]},
                {"name":"SERVICE LAYER","type":"service","components":[
                    {"name":"Core Service","sub":"Business Logic","icon":"C"},
                    {"name":"Search Engine","sub":"ElasticSearch","icon":"S"},
                    {"name":"Notification","sub":"Email / Push","icon":"N"},
                    {"name":"Task Queue","sub":"Celery / RQ","icon":"Q"}]},
                {"name":"DATA LAYER","type":"data","components":[
                    {"name":"Primary DB","sub":"PostgreSQL","icon":"D"},
                    {"name":"Cache","sub":"Redis","icon":"C"},
                    {"name":"Object Store","sub":"S3 / CDN","icon":"O"}]},
            ],
            "connections":[{"from":0,"to":1,"label":"HTTPS / WSS"},{"from":1,"to":2,"label":"REST / gRPC"},
                           {"from":2,"to":3,"label":"Read / Write"}],
            "cross_cuts":[{"name":"Monitoring","icon":"M"},{"name":"CI/CD","icon":"C"},{"name":"Logging","icon":"L"}],
        },
        "AI & Machine Learning": {
            "title": topic.title(), "subtitle": f"{topic.title()} — Comparative Architecture | {domain.title()}",
            "layers": [
                {"name":"INPUT & DATA","type":"client","components":[
                    {"name":"Text Corpus","sub":"Pretraining Data","icon":"T"},
                    {"name":"Image/Video","sub":"Visual Inputs","icon":"I"},
                    {"name":"Multimodal","sub":"Text + Vision","icon":"M"},
                    {"name":"Benchmarks","sub":"Eval Datasets","icon":"B"}]},
                {"name":m0.upper() if m0 != "Multi-model" else "MODEL VARIANT A","type":"gateway","components":[
                    {"name":"Tokenizer","sub":"BPE / SentencePiece","icon":"T"},
                    {"name":"Encoder","sub":m0,"icon":"E"},
                    {"name":"Attention","sub":"Multi-Head / Sparse","icon":"A"}]},
                {"name":m1.upper() if m1 != "Analysis" else "MODEL VARIANT B","type":"ai_ml","components":[
                    {"name":"Architecture","sub":m1,"icon":"A"},
                    {"name":"Adapter","sub":"LoRA / QLoRA","icon":"L"},
                    {"name":"Distillation","sub":"KD / Pruning","icon":"D"},
                    {"name":"Fine-tuning","sub":"PEFT / SFT","icon":"F"}]},
                {"name":"EVALUATION","type":"service","components":[
                    {"name":"Accuracy","sub":"BLEU / ROUGE","icon":"A"},
                    {"name":"Efficiency","sub":"FLOPs / Latency","icon":"E"},
                    {"name":"Memory","sub":"VRAM / Params","icon":"M"}]},
                {"name":"DEPLOYMENT","type":"infra","components":[
                    {"name":"Inference","sub":"vLLM / TGI","icon":"I"},
                    {"name":"Quantization","sub":"GPTQ / AWQ","icon":"Q"},
                    {"name":"Edge / Mobile","sub":"ONNX / TFLite","icon":"E"}]},
            ],
            "connections":[{"from":0,"to":1,"label":"Raw Data"},{"from":0,"to":2,"label":"Raw Data"},
                           {"from":1,"to":3,"label":"Predictions"},{"from":2,"to":3,"label":"Predictions"},
                           {"from":3,"to":4,"label":"Best Model"}],
            "cross_cuts":[{"name":"Orchestrator","icon":"O"},{"name":"Lineage","icon":"L"},{"name":"Alerts","icon":"A"}],
        },
        "Fintech & Payments": {
            "title": topic.title(), "subtitle": f"Fintech System Architecture | {domain.title()}",
            "layers": [
                {"name":"CLIENT CHANNELS","type":"client","components":[
                    {"name":"Mobile Banking","sub":"iOS / Android","icon":"M"},
                    {"name":"Web Portal","sub":"React SPA","icon":"W"},
                    {"name":"Partner API","sub":"B2B Integration","icon":"P"}]},
                {"name":"SECURITY GATEWAY","type":"gateway","components":[
                    {"name":"WAF","sub":"Web App Firewall","icon":"W"},
                    {"name":"Auth Server","sub":"OAuth2 / MFA","icon":"A"},
                    {"name":"Rate Limiter","sub":"Token Bucket","icon":"R"},
                    {"name":"Fraud Engine","sub":"ML Real-time","icon":"F"}]},
                {"name":"TRANSACTION ENGINE","type":"service","components":[
                    {"name":"Payment Router","sub":"Stripe / PayPal","icon":"P"},
                    {"name":"Ledger Service","sub":"Double-entry","icon":"L"},
                    {"name":"Settlement","sub":"T+1 Batch","icon":"S"},
                    {"name":"Notification","sub":"SMS / Email","icon":"N"}]},
                {"name":"COMPLIANCE","type":"ai_ml","components":[
                    {"name":"KYC / AML","sub":"Identity Verify","icon":"K"},
                    {"name":"PCI-DSS","sub":"Card Data Vault","icon":"C"},
                    {"name":"Audit Trail","sub":"Immutable Log","icon":"A"}]},
                {"name":"DATA VAULT","type":"data","components":[
                    {"name":"Transaction DB","sub":"PostgreSQL HA","icon":"T"},
                    {"name":"Secrets Vault","sub":"HashiCorp","icon":"V"},
                    {"name":"Analytics DW","sub":"Snowflake","icon":"D"},
                    {"name":"Event Store","sub":"Kafka + S3","icon":"E"}]},
            ],
            "connections":[{"from":0,"to":1,"label":"TLS 1.3"},{"from":1,"to":2,"label":"Encrypted"},
                           {"from":2,"to":3,"label":"Compliance Check"},{"from":2,"to":4,"label":"ACID Write"},
                           {"from":3,"to":4,"label":"Audit Log"}],
            "cross_cuts":[{"name":"Encryption","icon":"E"},{"name":"Compliance","icon":"C"},{"name":"DR/HA","icon":"H"}],
        },
        "DevOps & CI/CD Infrastructure": {
            "title": topic.title(), "subtitle": f"CI/CD Pipeline Architecture | {domain.title()}",
            "layers": [
                {"name":"SOURCE CONTROL","type":"client","components":[
                    {"name":"Git Repository","sub":"GitHub / GitLab","icon":"G"},
                    {"name":"Code Review","sub":"PR Automation","icon":"R"},
                    {"name":"Branch Policy","sub":"GitFlow","icon":"B"}]},
                {"name":"BUILD & TEST","type":"gateway","components":[
                    {"name":"CI Server","sub":"GitHub Actions","icon":"C"},
                    {"name":"Test Runner","sub":"Jest / PyTest","icon":"T"},
                    {"name":"Code Analysis","sub":"SonarQube","icon":"S"},
                    {"name":"Security Scan","sub":"Snyk / Trivy","icon":"X"}]},
                {"name":"ARTIFACT MGMT","type":"service","components":[
                    {"name":"Container Reg","sub":"Docker Hub","icon":"D"},
                    {"name":"Helm Charts","sub":"Chart Museum","icon":"H"},
                    {"name":"Version Tags","sub":"SemVer","icon":"V"}]},
                {"name":"DEPLOYMENT","type":"ai_ml","components":[
                    {"name":"K8s Cluster","sub":"EKS / GKE","icon":"K"},
                    {"name":"Canary Deploy","sub":"Argo Rollouts","icon":"C"},
                    {"name":"Rollback","sub":"Auto-revert","icon":"R"},
                    {"name":"Config Mgmt","sub":"Ansible / Terraform","icon":"T"}]},
                {"name":"OBSERVABILITY","type":"infra","components":[
                    {"name":"Prometheus","sub":"Metrics","icon":"P"},
                    {"name":"Grafana","sub":"Dashboards","icon":"G"},
                    {"name":"Alert Manager","sub":"PagerDuty","icon":"A"},
                    {"name":"Log Stack","sub":"ELK / Loki","icon":"L"}]},
            ],
            "connections":[{"from":0,"to":1,"label":"Webhook"},{"from":1,"to":2,"label":"Artifacts"},
                           {"from":2,"to":3,"label":"Helm Deploy"},{"from":3,"to":4,"label":"Telemetry"}],
            "cross_cuts":[{"name":"Secrets","icon":"S"},{"name":"IaC","icon":"I"},{"name":"SLOs","icon":"O"}],
        },
        "Real-World Case Study": {
            "title": topic.title(), "subtitle": f"Production System Architecture | {domain.title()}",
            "layers": [
                {"name":"USER INTERFACE","type":"client","components":[
                    {"name":"Web Browser","sub":"SPA / SSR","icon":"W"},
                    {"name":"Mobile App","sub":"React Native","icon":"M"},
                    {"name":"CLI Tool","sub":"Terminal","icon":"C"}]},
                {"name":"EDGE / CDN","type":"gateway","components":[
                    {"name":"CloudFront","sub":"Global CDN","icon":"C"},
                    {"name":"Edge Functions","sub":"Lambda@Edge","icon":"E"},
                    {"name":"DNS / WAF","sub":"Route53","icon":"D"}]},
                {"name":"APPLICATION","type":"service","components":[
                    {"name":"API Servers","sub":"Auto-scaled","icon":"A"},
                    {"name":"WebSocket Hub","sub":"Real-time","icon":"W"},
                    {"name":"Queue Workers","sub":"SQS / RabbitMQ","icon":"Q"},
                    {"name":"Scheduler","sub":"Cron Jobs","icon":"S"}]},
                {"name":"STORAGE","type":"data","components":[
                    {"name":"SQL Cluster","sub":"Aurora / RDS","icon":"S"},
                    {"name":"NoSQL Store","sub":"DynamoDB","icon":"N"},
                    {"name":"Object Store","sub":"S3","icon":"O"},
                    {"name":"Search Index","sub":"ElasticSearch","icon":"E"}]},
                {"name":"INFRASTRUCTURE","type":"infra","components":[
                    {"name":"Container Orch","sub":"ECS / K8s","icon":"K"},
                    {"name":"Service Mesh","sub":"Istio","icon":"M"},
                    {"name":"Load Balancer","sub":"ALB / NLB","icon":"L"}]},
            ],
            "connections":[{"from":0,"to":1,"label":"HTTPS"},{"from":1,"to":2,"label":"Origin Pull"},
                           {"from":2,"to":3,"label":"Queries / Events"},{"from":2,"to":4,"label":"Orchestration"}],
            "cross_cuts":[{"name":"Monitoring","icon":"M"},{"name":"Security","icon":"S"},{"name":"Backup","icon":"B"}],
        },
        "Data Engineering & Big Data": {
            "title": topic.title(), "subtitle": f"Data Platform Architecture | {domain.title()}",
            "layers": [
                {"name":"DATA SOURCES","type":"client","components":[
                    {"name":"APIs / SaaS","sub":"REST / Webhooks","icon":"A"},
                    {"name":"Databases","sub":"CDC Capture","icon":"D"},
                    {"name":"File Systems","sub":"SFTP / GCS","icon":"F"},
                    {"name":"IoT Streams","sub":"MQTT / HTTP","icon":"I"}]},
                {"name":"INGESTION","type":"gateway","components":[
                    {"name":"Kafka","sub":"Event Streaming","icon":"K"},
                    {"name":"Debezium","sub":"CDC Connector","icon":"D"},
                    {"name":"Batch Loader","sub":"Airbyte / Fivetran","icon":"B"}]},
                {"name":"PROCESSING","type":"service","components":[
                    {"name":"Spark","sub":"Batch / Micro-batch","icon":"S"},
                    {"name":"Flink","sub":"Real-time Stream","icon":"F"},
                    {"name":"dbt","sub":"Transform / Model","icon":"T"},
                    {"name":"Beam","sub":"Unified Pipeline","icon":"B"}]},
                {"name":"STORAGE","type":"data","components":[
                    {"name":"Data Lake","sub":"S3 / Delta Lake","icon":"L"},
                    {"name":"Data Warehouse","sub":"BigQuery / SF","icon":"W"},
                    {"name":"Feature Store","sub":"Feast / Tecton","icon":"F"}]},
                {"name":"SERVING","type":"infra","components":[
                    {"name":"BI Dashboard","sub":"Looker / Tableau","icon":"B"},
                    {"name":"ML API","sub":"Model Serving","icon":"M"},
                    {"name":"Data Catalog","sub":"DataHub","icon":"C"},
                    {"name":"Orchestrator","sub":"Airflow / Dagster","icon":"O"}]},
            ],
            "connections":[{"from":0,"to":1,"label":"Push / Pull"},{"from":1,"to":2,"label":"Events / Batch"},
                           {"from":2,"to":3,"label":"Write Optimized"},{"from":3,"to":4,"label":"Query / Serve"}],
            "cross_cuts":[{"name":"Governance","icon":"G"},{"name":"Quality","icon":"Q"},{"name":"Lineage","icon":"L"}],
        },
    }

    spec = CATEGORY_SPECS.get(system_category, CATEGORY_SPECS["General / Web App"])
    spec["stats"] = base_stats
    # Add some randomization: shuffle component order within layers
    for layer in spec.get("layers", []):
        comps = layer.get("components", [])
        if len(comps) > 2 and random.random() > 0.6:
            random.shuffle(comps)
    return spec

def _render_architecture(spec, topic, domain, out_dir, theme=None):
    from PIL import Image, ImageDraw
    if theme is None: theme = _pick_theme()
    T_BG=theme["bg"]; T_BG2=theme["bg2"]; T_CARD=theme["card"]; T_BORDER=theme["border"]
    T_ACCENT=theme["accent"]; T_TEXT=theme["text"]; T_MUTED=theme["muted"]
    T_LC=theme["layer_colors"]; T_SHADOW=theme.get("card_shadow","#08090d")
    T_RADIUS=theme.get("card_radius",18)

    # ── Deterministic Layout Calculation ──
    layers = spec.get("layers", [])
    nl = len(layers)
    max_components = max((len(l.get("components", [])) for l in layers), default=0)
    
    # Calculate required dimensions based on content
    header_h = 240
    footer_h = 100
    layer_h = 400
    layer_gap = 60
    
    # Dynamic Height
    H = header_h + (nl * layer_h) + ((nl - 1) * layer_gap) + footer_h
    H = max(H, 2000) # Minimum height
    
    # Dynamic Width
    comp_w = 400
    comp_gap = 40
    sidebar_w = 300 # layers badges
    needed_w = sidebar_w + 100 + (max_components * (comp_w + comp_gap)) + 100
    W = max(3200, needed_w)

    img=Image.new("RGB",(W,H),T_BG); draw=ImageDraw.Draw(img)
    _gradient(draw,(0,0,W,H),T_BG,T_BG2)
    _draw_bg_pattern(draw, W, H, theme, header_h, footer_h)

    # ── Fonts ──
    # Try to load better fonts, use larger sizes
    ft=_get_font(80,True); fst=_get_font(40); fly=_get_font(36,True)
    fc=_get_font(32,True); fc_sm=_get_font(28,True)
    fcs=_get_font(28); fcs_sm=_get_font(24)
    fa=_get_font(30,True)
    fsn=_get_font(60,True); fsl=_get_font(28); flg=_get_font(30,True)
    fbr=_get_font(40,True)

    # Title bar
    draw.rectangle([(0,0),(W,header_h)],fill=T_BG2)
    draw.rectangle([(0,header_h-6),(W,header_h)],fill=T_ACCENT)
    
    # Title text
    title_text = spec.get("title", topic.title())
    draw.text((80,40), title_text, fill="#FFFFFF" if _is_dark_bg(T_BG) else "#1A1A2E", font=ft)
    
    subtitle_text = spec.get("subtitle", f"{domain.title()} Architecture")
    draw.text((80,140), subtitle_text, fill=T_MUTED, font=fst)
    
    brand=f"PaperBanana Framework"; bw=_text_w(draw,brand,fbr)
    draw.rounded_rectangle((W-bw-80,60,W-40,140),radius=16,fill=T_ACCENT)
    draw.text((W-bw-60,75),brand,fill="#FFFFFF" if _is_dark_bg(T_BG) else "#000000",font=fbr)

    # Stats / Info Bar (moved to footer or integrated?)
    # Let's put stats in subtitles or skip to clean up.
    
    # Layers Rendering
    lx = 60
    ly_start = header_h + 80
    
    layer_rects = []
    comp_rects = []
    
    for li, layer in enumerate(layers):
        ly = ly_start + li * (layer_h + layer_gap)
        lt = layer.get("type", "service")
        sc = T_LC.get(lt, T_LC["service"])
        
        # Layer Background
        lw = W - 120
        draw.rounded_rectangle((lx, ly, lx+lw, ly+layer_h), radius=T_RADIUS, fill=sc["fill"], outline=sc["bdr"], width=3)
        
        # Layer Label (Left Sidebar style)
        label_w = 260
        draw.rounded_rectangle((lx+20, ly+20, lx+20+label_w, ly+layer_h-20), radius=16, fill=sc["acc"])
        
        lname = layer.get("name", "Layer")
        # Multiline label if needed
        words = lname.split()
        lines = []
        current_line = []
        for word in words:
            if _text_w(draw, " ".join(current_line + [word]), fly) < label_w - 30:
                current_line.append(word)
            else:
                lines.append(" ".join(current_line))
                current_line = [word]
        lines.append(" ".join(current_line))
        
        total_text_h = len(lines) * 40
        start_text_y = ly + (layer_h // 2) - (total_text_h // 2)
        
        for idx, line in enumerate(lines):
            tw = _text_w(draw, line, fly)
            draw.text((lx+20 + (label_w//2) - (tw//2), start_text_y + idx*40), line, fill="#FFFFFF", font=fly)
            
        # Components
        comps = layer.get("components", [])
        if not comps: continue
        
        # Center components in remaining space
        avail_w = lw - label_w - 60
        comp_area_x = lx + label_w + 40
        
        # Calculate optimal component width
        nc = len(comps)
        # We want to fill the width but not be too wide
        # max_comp_w = 500?
        
        # If components don't fit, we might need to shrink or wrap (wrapping not supported in this simple layout yet)
        # But we calculated W based on max_components, so they should fit.
        
        actual_comp_w = (avail_w - ((nc-1)*comp_gap)) // nc
        actual_comp_w = min(actual_comp_w, 600) # Cap max width
        
        # Re-center if we capped width
        total_used_w = (nc * actual_comp_w) + ((nc-1) * comp_gap)
        start_x = comp_area_x + (avail_w - total_used_w) // 2
        
        clayer_rects = []
        
        for ci, comp in enumerate(comps):
            cx = start_x + ci * (actual_comp_w + comp_gap)
            cy = ly + 40
            ch = layer_h - 80
            
            # Shadow
            draw.rounded_rectangle((cx+6, cy+6, cx+actual_comp_w+6, cy+ch+6), radius=T_RADIUS, fill=T_SHADOW)
            # Card
            draw.rounded_rectangle((cx, cy, cx+actual_comp_w, cy+ch), radius=T_RADIUS, fill=T_CARD, outline=sc["bdr"], width=2)
            
            # Top accent bar
            draw.rounded_rectangle((cx, cy, cx+actual_comp_w, cy+8), radius=min(4, T_RADIUS), fill=sc["acc"])
            
            # Icon
            icon = comp.get("icon", "?")
            # Draw icon circle
            ic_size = 80
            ic_x = cx + (actual_comp_w // 2) - (ic_size // 2)
            ic_y = cy + 40
            draw.ellipse((ic_x, ic_y, ic_x+ic_size, ic_y+ic_size), fill=sc["acc"])
            # Icon text
            iw = _text_w(draw, icon, fsn)
            ih = _text_h(draw, icon, fsn)
            draw.text((ic_x + ic_size//2 - iw//2, ic_y + ic_size//2 - ih//2 - 4), icon, fill="#FFFFFF", font=fsn)
            
            # Name
            cname = comp.get("name", "Component")
            # Formatting logic similar to label
            cwords = cname.split()
            clines = []
            cline = []
            for w in cwords:
                if _text_w(draw, " ".join(cline + [w]), fc) < actual_comp_w - 30:
                    cline.append(w)
                else:
                    clines.append(" ".join(cline))
                    cline = [w]
            clines.append(" ".join(cline))
            
            name_y = ic_y + ic_size + 30
            for l_idx, line in enumerate(clines):
                lw_val = _text_w(draw, line, fc)
                draw.text((cx + actual_comp_w//2 - lw_val//2, name_y + l_idx*36), line, fill=T_TEXT, font=fc)
            
            # Subtitle
            sub = comp.get("sub", "")
            if sub:
                 # Truncate if too long
                 sub = textwrap.shorten(sub, width=30, placeholder="...")
                 sw = _text_w(draw, sub, fcs)
                 draw.text((cx + actual_comp_w//2 - sw//2, cy + ch - 50), sub, fill=T_MUTED, font=fcs)
                 
            clayer_rects.append((cx, cy, actual_comp_w, ch))
            
        comp_rects.append(clayer_rects)
        layer_rects.append((lx, ly, lw, layer_h))

    # Connections
    for conn in spec.get("connections", []):
        f_idx = conn.get("from", 0)
        t_idx = conn.get("to", 1)
        label = conn.get("label", "")
        
        if f_idx < len(layer_rects) and t_idx < len(layer_rects):
            f_rect = layer_rects[f_idx]
            t_rect = layer_rects[t_idx]
            
            fx = f_rect[0] + f_rect[2] // 2
            fy = f_rect[1] + f_rect[3]
            tx = t_rect[0] + t_rect[2] // 2
            ty = t_rect[1]
            
            draw.line([(fx, fy), (tx, ty)], fill=T_ACCENT, width=8)
            hs = 30
            draw.polygon([(tx, ty), (tx-hs, ty-hs), (tx+hs, ty-hs)], fill=T_ACCENT)
            
            if label:
                lbl_w = _text_w(draw, label, fst)
                mid_x = (fx + tx) // 2
                mid_y = (fy + ty) // 2
                draw.rounded_rectangle((mid_x - lbl_w//2 - 10, mid_y - 20, mid_x + lbl_w//2 + 10, mid_y + 20), radius=8, fill=T_BG, outline=T_BORDER)
                draw.text((mid_x - lbl_w//2, mid_y - 15), label, fill=T_TEXT, font=fst)

            # Dashed component-to-component connectors
            if f_idx < len(comp_rects) and t_idx < len(comp_rects):
                if comp_rects[f_idx] and comp_rects[t_idx]:
                    _dashed(draw,
                            (comp_rects[f_idx][0][0]+comp_rects[f_idx][0][2]//2, comp_rects[f_idx][0][1]+comp_rects[f_idx][0][3]),
                            (comp_rects[t_idx][0][0]+comp_rects[t_idx][0][2]//2, comp_rects[t_idx][0][1]),
                            color=T_MUTED, w=1, dl=6, gl=4)

    # Cross-cuts sidebar
    fcc = _get_font(28, True)
    fff = _get_font(26)
    ccs = spec.get("cross_cuts", [])
    if ccs:
        ccw = 240
        cy_start = ly_start
        cy_end = ly_start + nl * (layer_h + layer_gap) - layer_gap
        ccx = W - ccw - 30
        ccy = cy_start
        cch = cy_end - cy_start
        for ss, se in [((ccx,ccy),(ccx+ccw,ccy)), ((ccx+ccw,ccy),(ccx+ccw,ccy+cch)),
                       ((ccx,ccy+cch),(ccx+ccw,ccy+cch)), ((ccx,ccy),(ccx,ccy+cch))]:
            _dashed(draw, ss, se, color=T_MUTED, w=1)
        _center_text(draw, ccx, ccy+12, ccw, "CROSS-CUT", fcc, T_MUTED)
        ith = min(100, (cch-60) // max(len(ccs), 1))
        for ci, cc in enumerate(ccs):
            iy = ccy + 50 + ci * (ith + 14)
            draw.rounded_rectangle((ccx+10, iy, ccx+ccw-10, iy+ith), radius=T_RADIUS-6, fill=T_CARD, outline=T_BORDER, width=1)
            _center_text(draw, ccx+10, iy+ith//2-14, ccw-20, cc.get("name",""), fcc, T_TEXT)

    # Footer/legend
    fy = H - 130
    draw.rectangle([(0, fy), (W, H)], fill=T_BG2)
    draw.rectangle([(0, fy), (W, fy + 4)], fill=T_ACCENT)
    for i, layer in enumerate(layers):
        sc = T_LC.get(layer.get("type", "service"), T_LC["service"])
        ix = 60 + i * ((W - 250) // max(nl, 1))
        draw.ellipse((ix, fy + 28, ix + 22, fy + 50), fill=sc["acc"])
        draw.text((ix + 30, fy + 26), textwrap.shorten(layer.get('name', ''), width=24, placeholder='...'), fill=T_MUTED, font=flg)
    draw.text((60, fy + 80), f"AI Research Assistant | {domain.title()} | {theme['name']} Theme", fill=T_MUTED, font=fff)
    draw.text((W - 440, fy + 80), "PaperBanana", fill=T_ACCENT, font=fff)

    out = out_dir / f"{topic.strip().replace(' ', '_').lower()}_architecture.png"
    img.save(out, "PNG", dpi=(200, 200))
    return out

# ═════════════════════════════════════════════════════════════════════
#  WORKFLOW DIAGRAM
# ═════════════════════════════════════════════════════════════════════

def _render_workflow(topic, domain, research_outputs, out_dir, theme=None):
    from PIL import Image, ImageDraw
    if theme is None: theme = _pick_theme()
    T_BG=theme["bg"]; T_BG2=theme["bg2"]; T_CARD=theme["card"]; T_BORDER=theme["border"]
    T_ACCENT=theme["accent"]; T_TEXT=theme["text"]; T_MUTED=theme["muted"]
    T_STEPS=theme["step_colors"]; T_SHADOW=theme.get("card_shadow","#08090d")
    T_RADIUS=theme.get("card_radius",18)

    W,H=3200,1800; img=Image.new("RGB",(W,H),T_BG); draw=ImageDraw.Draw(img)
    _gradient(draw,(0,0,W,H),T_BG,T_BG2)
    _draw_bg_pattern(draw, W, H, theme, 140, 70)
    ft=_get_font(72,True); fs=_get_font(36); fn=_get_font(66,True)
    fst=_get_font(40,True); fd=_get_font(32); ff=_get_font(26)

    draw.rectangle([(0,0),(W,140)],fill=T_BG2)
    if theme.get("title_accent_bar", True):
        draw.rectangle([(0,136),(W,140)],fill=T_ACCENT)
        draw.rectangle([(50,22),(62,110)],fill=T_ACCENT)
    else:
        draw.rectangle([(0,138),(W,140)],fill=T_BORDER)
    draw.text((80,16),f"How {topic.title()} Pipeline Works",fill="#FFFFFF" if _is_dark_bg(T_BG) else "#1A1A2E",font=ft)
    draw.text((80,96),"End-to-End Research Workflow",fill=T_MUTED,font=fs)

    methods=_methods_from_research(research_outputs)
    steps=[
        {"n":"01","t":"Input & Config","d":f"Topic: {topic[:24]}","dt":f"Domain: {domain}"},
        {"n":"02","t":"Research Agents","d":"3x parallel LLM agents","dt":"Historical · SOTA · Emerging"},
        {"n":"03","t":"Methodology","d":"Specialist analysis","dt":methods[0][:24] if methods else "Gap analysis"},
        {"n":"04","t":"Architecture Viz","d":"Diagram generation","dt":"PaperBanana + Pillow"},
        {"n":"05","t":"Report Synthesis","d":"PhD-grade whitepaper","dt":"4000+ words · 50+ cites"},
        {"n":"06","t":"Output & Export","d":"PDF + Markdown + PNG","dt":"Download-ready"},
    ]
    # Randomize layout between grid and flow styles
    layout = theme.get("layout_style", "horizontal_layers")
    cols,rows=3,2; mx,my=80,180; gx,gy=50,90
    if layout == "zigzag":
        cols,rows=2,3; gx,gy=60,70
    cw=(W-2*mx-(cols-1)*gx)//cols; ch=(H-my-160-(rows-1)*gy)//rows
    positions=[]
    for i,step in enumerate(steps):
        row,col=i//cols,i%cols
        if layout == "zigzag" and row%2==1: col=cols-1-col
        elif layout != "zigzag" and row==1: col=cols-1-col
        cx=mx+col*(cw+gx); cy=my+row*(ch+gy); sc=T_STEPS[i%len(T_STEPS)]
        draw.rounded_rectangle((cx+6,cy+6,cx+cw+6,cy+ch+6),radius=T_RADIUS,fill=T_SHADOW)
        draw.rounded_rectangle((cx,cy,cx+cw,cy+ch),radius=T_RADIUS,fill=sc["fill"],outline=sc["bdr"],width=3)
        draw.rounded_rectangle((cx+3,cy+3,cx+cw-3,cy+10),radius=4,fill=sc["acc"])
        bs=82; draw.rounded_rectangle((cx+22,cy+22,cx+22+bs,cy+22+bs),radius=T_RADIUS-2,fill=sc["acc"])
        nw=_text_w(draw,step["n"],fn); nh=_text_h(draw,step["n"],fn)
        draw.text((cx+22+bs//2-nw//2,cy+22+bs//2-nh//2-2),step["n"],fill="#FFFFFF" if _is_dark_bg(T_BG) else "#000000",font=fn)
        draw.text((cx+22+bs+22,cy+30),step["t"],fill=sc["txt"],font=fst)
        draw.text((cx+22+bs+22,cy+78),step["d"],fill=T_TEXT,font=fd)
        draw.text((cx+32,cy+ch-64),step["dt"],fill=T_MUTED,font=fd)
        bar_y=cy+ch-14; filled=(i+1)/len(steps)
        draw.rounded_rectangle((cx+8,bar_y,cx+cw-8,bar_y+8),radius=4,fill=T_BORDER)
        draw.rounded_rectangle((cx+8,bar_y,cx+8+int((cw-16)*filled),bar_y+8),radius=4,fill=sc["acc"])
        positions.append((cx,cy,cw,ch,col,row))
    for i in range(len(positions)-1):
        s,e=positions[i],positions[i+1]; sc=T_STEPS[i%len(T_STEPS)]
        if s[5]==e[5]:
            if s[4]<e[4]: _arrow(draw,(s[0]+s[2],s[1]+s[3]//2),(e[0],e[1]+e[3]//2),sc["acc"],5,20)
            else: _arrow(draw,(s[0],s[1]+s[3]//2),(e[0]+e[2],e[1]+e[3]//2),sc["acc"],5,20)
        else: _arrow(draw,(s[0]+s[2]//2,s[1]+s[3]),(e[0]+e[2]//2,e[1]),sc["acc"],5,20)
    draw.rectangle([(0,H-70),(W,H)],fill=T_BG2)
    draw.text((60,H-54),f"AI Research Pipeline | {domain.title()} | {theme['name']} Theme",fill=T_MUTED,font=ff)
    out=out_dir/f"{topic.strip().replace(' ','_').lower()}_workflow.png"
    img.save(out,"PNG",dpi=(200,200)); return out

# ═════════════════════════════════════════════════════════════════════
#  METHODS GRID DIAGRAM
# ═════════════════════════════════════════════════════════════════════

def _render_methods(topic, domain, research_outputs, out_dir, theme=None):
    from PIL import Image, ImageDraw
    if theme is None: theme = _pick_theme()
    T_BG=theme["bg"]; T_BG2=theme["bg2"]; T_CARD=theme["card"]; T_BORDER=theme["border"]
    T_ACCENT=theme["accent"]; T_TEXT=theme["text"]; T_MUTED=theme["muted"]
    T_SHADOW=theme.get("card_shadow","#08090d"); T_RADIUS=theme.get("card_radius",18)

    W,H=3200,2200; img=Image.new("RGB",(W,H),T_BG); draw=ImageDraw.Draw(img)
    _gradient(draw,(0,0,W,H),T_BG,T_BG2)
    _draw_bg_pattern(draw, W, H, theme, 140, 70)
    ft=_get_font(68,True); fs=_get_font(36); fn=_get_font(54,True)
    fm=_get_font(34,True); fd=_get_font(26); ff=_get_font(26)

    # Randomize accent for title bar
    title_accent = theme["step_colors"][random.randint(0, len(theme["step_colors"])-1)]["acc"]
    draw.rectangle([(0,0),(W,140)],fill=T_BG2)
    if theme.get("title_accent_bar", True):
        draw.rectangle([(0,136),(W,140)],fill=title_accent)
    else:
        draw.rectangle([(0,138),(W,140)],fill=T_BORDER)
    draw.text((60,16),"Key Methods & Techniques",fill="#FFFFFF" if _is_dark_bg(T_BG) else "#1A1A2E",font=ft)
    draw.text((60,88),f"{topic.title()} | {domain.title()}",fill=T_MUTED,font=fs)

    methods=[]; descs={}
    for r in research_outputs:
        for m in r.get("key_methods",[]):
            if m not in descs: methods.append(m); descs[m]=""
        s=r.get("summary","")
        for m in methods:
            if m.lower() in s.lower() and not descs.get(m):
                idx=s.lower().find(m.lower()); descs[m]=s[max(0,idx-20):idx+len(m)+80].strip()
    fillers=["Data Augmentation","Transfer Learning","Ensemble Methods","Cross-Validation",
             "Feature Engineering","Hyperparameter Tuning","Regularization","Batch Norm"]
    for f in fillers:
        if len(methods)>=12: break
        if f not in methods: methods.append(f); descs[f]=f"Standard technique for {topic}"
    methods=methods[:16]; cols=4; rows=math.ceil(len(methods)/cols)
    mx,my=60,165; gap=24; cw=(W-2*mx-(cols-1)*gap)//cols; ch=(H-my-100-(rows-1)*gap)//rows; ch=min(ch,450)
    # Use theme step_colors cycled for variety
    gc=[sc["acc"] for sc in theme["step_colors"]] * 3
    for i,method in enumerate(methods):
        r2,c2=i//cols,i%cols; cx=mx+c2*(cw+gap); cy=my+r2*(ch+gap); c=gc[i%len(gc)]
        draw.rounded_rectangle((cx+5,cy+5,cx+cw+5,cy+ch+5),radius=T_RADIUS,fill=T_SHADOW)
        draw.rounded_rectangle((cx,cy,cx+cw,cy+ch),radius=T_RADIUS,fill=T_CARD,outline=T_BORDER,width=2)
        bs=62; draw.rounded_rectangle((cx+18,cy+18,cx+18+bs,cy+18+bs),radius=T_RADIUS-4,fill=c)
        ns=str(i+1); nw=_text_w(draw,ns,fn); nh=_text_h(draw,ns,fn)
        draw.text((cx+18+bs//2-nw//2,cy+18+bs//2-nh//2-2),ns,fill="#FFFFFF" if _is_dark_bg(T_BG) else "#000000",font=fn)
        mc=max(6,(cw-bs-50)//14); dn=textwrap.shorten(method,width=mc,placeholder="...")
        draw.text((cx+18+bs+16,cy+28),dn,fill=c,font=fm)
        desc=descs.get(method,f"Technique for {topic}"); mdc=max(10,(cw-40)//12)
        for di,dl in enumerate(textwrap.wrap(desc,width=mdc)[:3]):
            draw.text((cx+24,cy+96+di*36),dl,fill=T_MUTED,font=fd)
        draw.rounded_rectangle((cx+12,cy+ch-8,cx+cw-12,cy+ch-3),radius=3,fill=c)
    draw.rectangle([(0,H-70),(W,H)],fill=T_BG2)
    draw.text((60,H-54),f"Methods Analysis | {len(methods)} Key Techniques | {theme['name']}",fill=T_MUTED,font=ff)
    out=out_dir/f"{topic.strip().replace(' ','_').lower()}_methods.png"
    img.save(out,"PNG",dpi=(200,200)); return out

# ═════════════════════════════════════════════════════════════════════
#  METHODOLOGY FLOWCHART RENDERER — 6 DIFFERENT LAYOUT TYPES
#  Each flowchart picks a RANDOM layout so they never look the same.
# ═════════════════════════════════════════════════════════════════════

def _extract_steps(pipeline_steps, methodology_text, title):
    """Extract meaningful steps from pipeline_steps or methodology_text."""
    steps = []
    if pipeline_steps and isinstance(pipeline_steps, list):
        steps = [s.strip() for s in pipeline_steps if isinstance(s, str) and len(s.strip()) > 10]
    if not steps:
        numbered = re.findall(r'(?:\d+[\.\)]\s*)(.*?)(?=\n\s*\d+[\.\)]|\Z)', methodology_text, re.DOTALL)
        if len(numbered) >= 3:
            steps = [s.strip().rstrip('.').strip() for s in numbered if len(s.strip()) > 15][:10]
    if not steps:
        sentences = re.split(r'(?<=[.!?])\s+', methodology_text)
        steps = [s.strip() for s in sentences if len(s.strip()) > 25][:8]
    if not steps:
        steps = [f"Phase {i+1}: Analysis and implementation for {title}" for i in range(4)]
    return steps[:10]


def _split_step_text(step_text):
    """Split a step into title + description. Never repeats same text.
    
    For steps with separators (colon, dash), splits at the separator.
    For long steps without separators, splits at a natural word boundary
    to produce a shorter title + remaining description.
    For short steps, returns just the title with no description.
    """
    step_text = step_text.strip()
    colon = step_text.find(":")
    dash = step_text.find(" \u2013 ")
    if dash < 0: dash = step_text.find(" - ")
    if 5 < colon < 60:
        t = step_text[:colon].strip()
        d = step_text[colon+1:].strip()
        return t, d if d.lower() != t.lower() else ""
    elif 5 < dash < 60:
        t = step_text[:dash].strip()
        d = step_text[dash+3:].strip()
        return t, d if d.lower() != t.lower() else ""
    else:
        # For long text without separator, try to split at a natural point
        # Use semicolon, comma after 30+ chars, or "including" / "using" / "with" / "for"
        if len(step_text) > 50:
            for sep in [";", " including ", " using ", " with ", " for ", " by "]:
                idx = step_text.find(sep)
                if 15 < idx < 70:
                    t = step_text[:idx].strip().rstrip(",;")
                    d = step_text[idx:].lstrip(";, ").strip()
                    if d and d.lower() != t.lower():
                        return t, d
            # Split at last comma before position 60
            last_comma = step_text.rfind(",", 15, 60)
            if last_comma > 15:
                t = step_text[:last_comma].strip()
                d = step_text[last_comma+1:].strip()
                if d and d.lower() != t.lower():
                    return t, d
        # Short text or no good break point — title only, no description
        return step_text, ""


def _meth_title_bar(draw, W, title_h, pad, title, n, theme, fc_accent, ft, fsub, fbadge):
    """Draw title bar for methodology flowcharts."""
    T_BG2=theme["bg2"]; T_TEXT=theme["text"]; T_MUTED=theme["muted"]; T_BORDER=theme["border"]
    draw.rectangle([(0,0),(W,title_h)], fill=T_BG2)
    if theme.get("title_accent_bar", True):
        draw.rectangle([(0,title_h-4),(W,title_h)], fill=fc_accent)
        draw.rectangle([(pad,20),(pad+10,title_h-26)], fill=fc_accent)
    else:
        draw.rectangle([(0,title_h-2),(W,title_h)], fill=T_BORDER)
    draw.text((pad+24,16), textwrap.shorten(title,width=55,placeholder="..."),
              fill="#FFFFFF" if _is_dark_bg(theme["bg"]) else "#1A1A2E", font=ft)
    draw.text((pad+24,78), "Proposed Methodology Pipeline", fill=T_MUTED, font=fsub)
    badge = f"{n} STEPS"
    bw_t = _text_w(draw,badge,fbadge)+36
    draw.rounded_rectangle((W-bw_t-pad,30,W-pad,72), radius=14, fill=fc_accent)
    draw.text((W-bw_t-pad+18,38), badge,
              fill="#FFFFFF" if _is_dark_bg(theme["bg"]) else "#000000", font=fbadge)


def _meth_footer(draw, W, H, footer_h, title, theme, fc_accent, fftr):
    """Draw footer for methodology flowcharts."""
    T_BG2=theme["bg2"]; T_MUTED=theme["muted"]; T_ACCENT=theme["accent"]
    draw.rectangle([(0,H-footer_h),(W,H)], fill=T_BG2)
    draw.rectangle([(0,H-footer_h),(W,H-footer_h+3)], fill=fc_accent)
    draw.text((60,H-footer_h+24),
              f"Methodology Pipeline | {textwrap.shorten(title,width=50,placeholder='...')}",
              fill=T_MUTED, font=fftr)
    draw.text((W-350,H-footer_h+24), f"PaperBanana | {theme['name']}", fill=T_ACCENT, font=fftr)


# ── LAYOUT 1: HORIZONTAL PIPELINE (steps flow left-to-right in rows) ──
def _meth_layout_horizontal(draw, img, steps, title, theme, fc_accent, W, H, title_h, footer_h):
    T_STEPS=theme["step_colors"]; T_CARD=theme["card"]; T_BORDER=theme["border"]
    T_TEXT=theme["text"]; T_MUTED=theme["muted"]; T_SHADOW=theme.get("card_shadow","#08090d")
    T_RADIUS=theme.get("card_radius",18)
    n=len(steps); fnum=_get_font(42,True); fstep=_get_font(34,True); fdesc=_get_font(28); fa=_get_font(26,True)
    cols=min(n,3); rows=math.ceil(n/cols); pad=60
    gap_x,gap_y=60,80
    card_w=(W-2*pad-(cols-1)*gap_x)//cols; card_h=280
    y_start=title_h+40
    positions=[]
    for i,step_text in enumerate(steps):
        r2=i//cols; c2=i%cols; sc=T_STEPS[i%len(T_STEPS)]
        if r2%2==1: c2=cols-1-c2
        cx=pad+c2*(card_w+gap_x); cy=y_start+r2*(card_h+gap_y)
        draw.rounded_rectangle((cx+6,cy+6,cx+card_w+6,cy+card_h+6),radius=T_RADIUS,fill=T_SHADOW)
        draw.rounded_rectangle((cx,cy,cx+card_w,cy+card_h),radius=T_RADIUS,fill=sc["fill"],outline=sc["bdr"],width=3)
        draw.rounded_rectangle((cx+4,cy+3,cx+card_w-4,cy+12),radius=4,fill=sc["acc"])
        nr=30; ncx=cx+48; ncy=cy+58
        draw.ellipse((ncx-nr,ncy-nr,ncx+nr,ncy+nr),fill=sc["acc"])
        ns=str(i+1); nw=_text_w(draw,ns,fnum); nh=_text_h(draw,ns,fnum)
        draw.text((ncx-nw//2,ncy-nh//2-2),ns,fill="#FFFFFF",font=fnum)
        s_title,s_desc=_split_step_text(step_text)
        tx=cx+94; avail=card_w-110
        cpl=max(25,avail//18)
        # Wrap title across multiple lines if needed
        title_lines=textwrap.wrap(s_title,width=cpl)[:2]
        for tli,tline in enumerate(title_lines):
            draw.text((tx,cy+24+tli*38),tline,fill=sc["txt"],font=fstep)
        desc_y=cy+24+len(title_lines)*38+8
        if s_desc:
            for li,line in enumerate(textwrap.wrap(s_desc,width=max(22,avail//16))[:4]):
                draw.text((tx,desc_y+li*32),line,fill=T_TEXT,font=fdesc)
        frac=f"STEP {i+1}/{n}"; fw=_text_w(draw,frac,fa)
        draw.text((cx+card_w-fw-16,cy+card_h-34),frac,fill=T_MUTED,font=fa)
        prog=(i+1)/n; bar_y=cy+card_h-10
        draw.rounded_rectangle((cx+14,bar_y,cx+card_w-14,bar_y+6),radius=3,fill=T_BORDER)
        draw.rounded_rectangle((cx+14,bar_y,cx+14+int((card_w-28)*prog),bar_y+6),radius=3,fill=sc["acc"])
        positions.append((cx,cy,card_w,card_h,c2,r2))
    for i in range(len(positions)-1):
        s,e=positions[i],positions[i+1]; sc=T_STEPS[i%len(T_STEPS)]
        if s[5]==e[5]:
            if s[4]<e[4]: _arrow(draw,(s[0]+s[2],s[1]+s[3]//2),(e[0],e[1]+e[3]//2),sc["acc"],5,18)
            else: _arrow(draw,(s[0],s[1]+s[3]//2),(e[0]+e[2],e[1]+e[3]//2),sc["acc"],5,18)
        else:
            _arrow(draw,(s[0]+s[2]//2,s[1]+s[3]),(e[0]+e[2]//2,e[1]),sc["acc"],5,18)


# ── LAYOUT 2: GRID MATRIX (steps in a structured grid) ──
def _meth_layout_grid(draw, img, steps, title, theme, fc_accent, W, H, title_h, footer_h):
    T_STEPS=theme["step_colors"]; T_CARD=theme["card"]; T_BORDER=theme["border"]
    T_TEXT=theme["text"]; T_MUTED=theme["muted"]; T_SHADOW=theme.get("card_shadow","#08090d")
    T_RADIUS=theme.get("card_radius",18); T_ACCENT=theme["accent"]
    n=len(steps); fnum=_get_font(48,True); fstep=_get_font(32,True); fdesc=_get_font(26); fa=_get_font(24)
    cols=3 if n>=6 else 2; rows=math.ceil(n/cols); pad=50; gap=40
    card_w=(W-2*pad-(cols-1)*gap)//cols; card_h=max(280,min(340,(H-title_h-footer_h-80-(rows-1)*gap)//rows))
    y_start=title_h+40
    for i,step_text in enumerate(steps):
        r2=i//cols; c2=i%cols; sc=T_STEPS[i%len(T_STEPS)]
        cx=pad+c2*(card_w+gap); cy=y_start+r2*(card_h+gap)
        draw.rounded_rectangle((cx+6,cy+6,cx+card_w+6,cy+card_h+6),radius=T_RADIUS,fill=T_SHADOW)
        draw.rounded_rectangle((cx,cy,cx+card_w,cy+card_h),radius=T_RADIUS,fill=T_CARD,outline=T_BORDER,width=2)
        draw.rounded_rectangle((cx+2,cy+6,cx+12,cy+card_h-6),radius=4,fill=sc["acc"])
        ns=str(i+1); nw=_text_w(draw,ns,fnum)
        draw.text((cx+card_w-nw-20,cy+12),ns,fill=sc["glow"],font=fnum)
        s_title,s_desc=_split_step_text(step_text)
        tx=cx+28; avail=card_w-80
        cpl=max(22,avail//17)
        title_lines=textwrap.wrap(s_title,width=cpl)[:2]
        for tli,tline in enumerate(title_lines):
            draw.text((tx,cy+22+tli*38),tline,fill=sc["txt"],font=fstep)
        desc_y=cy+22+len(title_lines)*38+10
        if s_desc:
            for li,line in enumerate(textwrap.wrap(s_desc,width=max(22,avail//15))[:4]):
                draw.text((tx,desc_y+li*30),line,fill=T_MUTED,font=fdesc)
        prog=(i+1)/n; bar_y=cy+card_h-12
        draw.rounded_rectangle((cx+14,bar_y,cx+card_w-14,bar_y+6),radius=3,fill=T_BORDER)
        draw.rounded_rectangle((cx+14,bar_y,cx+14+int((card_w-28)*prog),bar_y+6),radius=3,fill=sc["acc"])
    for i in range(n-1):
        r1,c1=i//cols,i%cols; r2,c2=(i+1)//cols,(i+1)%cols
        sc=T_STEPS[i%len(T_STEPS)]
        x1=pad+c1*(card_w+gap)+card_w//2; y1=y_start+r1*(card_h+gap)+card_h
        x2=pad+c2*(card_w+gap)+card_w//2; y2=y_start+r2*(card_h+gap)
        if r1==r2:
            x1s=pad+c1*(card_w+gap)+card_w; y1s=y_start+r1*(card_h+gap)+card_h//2
            x2s=pad+c2*(card_w+gap); y2s=y1s
            _arrow(draw,(x1s,y1s),(x2s,y2s),sc["acc"],4,16)
        else:
            _arrow(draw,(x1,y1+4),(x2,y2-4),sc["acc"],4,16)


# ── LAYOUT 3: CIRCULAR/RADIAL (steps around a center hub) ──
def _meth_layout_radial(draw, img, steps, title, theme, fc_accent, W, H, title_h, footer_h):
    T_STEPS=theme["step_colors"]; T_CARD=theme["card"]; T_BORDER=theme["border"]
    T_TEXT=theme["text"]; T_MUTED=theme["muted"]; T_SHADOW=theme.get("card_shadow","#08090d")
    T_RADIUS=theme.get("card_radius",18); T_ACCENT=theme["accent"]
    n=len(steps); fnum=_get_font(40,True); fstep=_get_font(32,True); fdesc=_get_font(26)
    ftitle_hub=_get_font(38,True); fsub_hub=_get_font(28)
    avail_h=H-title_h-footer_h; cx_hub=W//2; cy_hub=title_h+avail_h//2
    # Scale card size and radius based on step count
    card_w=560; card_h=220
    radius=min(avail_h//2 - card_h//2 - 40, W//2 - card_w//2 - 40)
    radius=max(radius, 400)  # minimum radius for readability
    hub_r=130
    # Hub
    draw.ellipse((cx_hub-hub_r-6,cy_hub-hub_r-6,cx_hub+hub_r+6,cy_hub+hub_r+6),fill=fc_accent)
    draw.ellipse((cx_hub-hub_r,cy_hub-hub_r,cx_hub+hub_r,cy_hub+hub_r),fill=theme["bg2"])
    # Hub title — wrap across multiple lines
    hub_lines=textwrap.wrap(title,width=16)[:3]
    hub_total_h=len(hub_lines)*36
    for hli,hline in enumerate(hub_lines):
        tw=_text_w(draw,hline,ftitle_hub)
        draw.text((cx_hub-tw//2,cy_hub-hub_total_h//2+hli*36),hline,fill=T_ACCENT,font=ftitle_hub)
    steps_label=f"{n} Steps"
    tw2=_text_w(draw,steps_label,fsub_hub)
    draw.text((cx_hub-tw2//2,cy_hub+hub_total_h//2+4),steps_label,fill=T_MUTED,font=fsub_hub)
    positions=[]
    for i,step_text in enumerate(steps):
        angle=2*math.pi*i/n - math.pi/2
        ccx=cx_hub+int(radius*math.cos(angle)); ccy=cy_hub+int(radius*math.sin(angle))
        ccx=max(card_w//2+20,min(W-card_w//2-20,ccx))
        ccy=max(title_h+card_h//2+10,min(H-footer_h-card_h//2-10,ccy))
        sc=T_STEPS[i%len(T_STEPS)]; lx=ccx-card_w//2; ly=ccy-card_h//2
        # Connector line from hub to card
        hub_edge_x=cx_hub+int(hub_r*math.cos(angle))
        hub_edge_y=cy_hub+int(hub_r*math.sin(angle))
        card_edge_x=ccx-int((card_w//2-10)*math.cos(angle)) if abs(math.cos(angle))>0.2 else ccx
        card_edge_y=ccy-int((card_h//2-10)*math.sin(angle)) if abs(math.sin(angle))>0.2 else ccy
        _arrow(draw,(hub_edge_x,hub_edge_y),(card_edge_x,card_edge_y),color=sc["acc"],w=3,hs=14)
        # Card shadow + body
        draw.rounded_rectangle((lx+5,ly+5,lx+card_w+5,ly+card_h+5),radius=T_RADIUS,fill=T_SHADOW)
        draw.rounded_rectangle((lx,ly,lx+card_w,ly+card_h),radius=T_RADIUS,fill=sc["fill"],outline=sc["bdr"],width=3)
        # Top accent bar
        draw.rounded_rectangle((lx+4,ly+3,lx+card_w-4,ly+10),radius=4,fill=sc["acc"])
        # Step number circle
        nr=28; draw.ellipse((lx+16,ly+22,lx+16+nr*2,ly+22+nr*2),fill=sc["acc"])
        ns=str(i+1); nw=_text_w(draw,ns,fnum); nh=_text_h(draw,ns,fnum)
        draw.text((lx+16+nr-nw//2,ly+22+nr-nh//2-2),ns,fill="#FFFFFF",font=fnum)
        s_title,s_desc=_split_step_text(step_text)
        tx=lx+80; avail=card_w-96
        cpl=max(22,avail//18)
        title_lines=textwrap.wrap(s_title,width=cpl)[:2]
        for tli,tline in enumerate(title_lines):
            draw.text((tx,ly+22+tli*36),tline,fill=sc["txt"],font=fstep)
        desc_y=ly+22+len(title_lines)*36+8
        if s_desc:
            for li,line in enumerate(textwrap.wrap(s_desc,width=max(22,avail//16))[:3]):
                draw.text((lx+20,desc_y+li*30),line,fill=T_MUTED,font=fdesc)
        # Progress bar at bottom
        prog=(i+1)/n; bar_y=ly+card_h-10
        draw.rounded_rectangle((lx+14,bar_y,lx+card_w-14,bar_y+6),radius=3,fill=T_BORDER)
        draw.rounded_rectangle((lx+14,bar_y,lx+14+int((card_w-28)*prog),bar_y+6),radius=3,fill=sc["acc"])
        positions.append((ccx,ccy))


# ── LAYOUT 4: STAIRCASE/ZIGZAG (cards alternate left-right descending) ──
def _meth_layout_staircase(draw, img, steps, title, theme, fc_accent, W, H, title_h, footer_h):
    T_STEPS=theme["step_colors"]; T_CARD=theme["card"]; T_BORDER=theme["border"]
    T_TEXT=theme["text"]; T_MUTED=theme["muted"]; T_SHADOW=theme.get("card_shadow","#08090d")
    T_RADIUS=theme.get("card_radius",18)
    n=len(steps); fnum=_get_font(44,True); fstep=_get_font(34,True); fdesc=_get_font(28); fa=_get_font(26)
    pad=60; card_w=(W-3*pad)//2; card_h=200; gap_y=40
    y_start=title_h+30; positions=[]
    for i,step_text in enumerate(steps):
        sc=T_STEPS[i%len(T_STEPS)]; cy=y_start+i*(card_h+gap_y)
        cx=pad if i%2==0 else W-pad-card_w
        draw.rounded_rectangle((cx+6,cy+6,cx+card_w+6,cy+card_h+6),radius=T_RADIUS,fill=T_SHADOW)
        draw.rounded_rectangle((cx,cy,cx+card_w,cy+card_h),radius=T_RADIUS,fill=sc["fill"],outline=sc["bdr"],width=3)
        draw.rounded_rectangle((cx+4,cy+3,cx+card_w//3,cy+12),radius=4,fill=sc["acc"])
        nr=32; ncx=cx+50; ncy=cy+card_h//2
        pts_hex=[]
        for a in range(6):
            ang=math.radians(60*a-30)
            pts_hex.append((ncx+nr*math.cos(ang),ncy+nr*math.sin(ang)))
        draw.polygon(pts_hex,fill=sc["acc"])
        ns=str(i+1); nw=_text_w(draw,ns,fnum); nh=_text_h(draw,ns,fnum)
        draw.text((ncx-nw//2,ncy-nh//2-2),ns,fill="#FFFFFF",font=fnum)
        s_title,s_desc=_split_step_text(step_text)
        tx=cx+100; avail=card_w-120
        cpl=max(22,avail//18)
        title_lines=textwrap.wrap(s_title,width=cpl)[:2]
        for tli,tline in enumerate(title_lines):
            draw.text((tx,cy+20+tli*38),tline,fill=sc["txt"],font=fstep)
        desc_y=cy+20+len(title_lines)*38+8
        if s_desc:
            for li,line in enumerate(textwrap.wrap(s_desc,width=max(22,avail//16))[:3]):
                draw.text((tx,desc_y+li*32),line,fill=T_TEXT,font=fdesc)
        frac=f"STEP {i+1}/{n}"; fw=_text_w(draw,frac,fa)
        draw.text((cx+card_w-fw-16,cy+card_h-34),frac,fill=T_MUTED,font=fa)
        positions.append((cx,cy,card_w,card_h))
    for i in range(len(positions)-1):
        sc=T_STEPS[i%len(T_STEPS)]; s=positions[i]; e=positions[i+1]
        sx=s[0]+s[2]//2; sy=s[1]+s[3]; ex=e[0]+e[2]//2; ey=e[1]
        _arrow(draw,(sx,sy+4),(ex,ey-4),sc["acc"],4,16)


# ── LAYOUT 5: VERTICAL TIMELINE (original, kept as one option) ──
def _meth_layout_timeline(draw, img, steps, title, theme, fc_accent, W, H, title_h, footer_h):
    T_STEPS=theme["step_colors"]; T_CARD=theme["card"]; T_BORDER=theme["border"]
    T_TEXT=theme["text"]; T_MUTED=theme["muted"]; T_SHADOW=theme.get("card_shadow","#08090d")
    T_RADIUS=theme.get("card_radius",18); T_ACCENT=theme["accent"]
    n=len(steps); fnum=_get_font(44,True); fstep=_get_font(34,True); fdesc=_get_font(28); fftr=_get_font(24)
    pad=70; tl_x=pad+45; card_x=tl_x+80; card_w=W-card_x-pad; card_h=220; card_gap=50
    tl_y0=title_h+30; tl_y1=H-footer_h-10
    sp_colors=[_hex(T_STEPS[i%len(T_STEPS)]["acc"]) for i in range(min(3,len(T_STEPS)))]
    if len(sp_colors)<2: sp_colors=[_hex(fc_accent),_hex(T_ACCENT)]
    for seg in range(int(tl_y0),int(tl_y1),2):
        ratio=(seg-tl_y0)/max(tl_y1-tl_y0,1)
        si=min(int(ratio*(len(sp_colors)-1)),len(sp_colors)-2)
        lr=ratio*(len(sp_colors)-1)-si
        c=tuple(int(sp_colors[si][j]+(sp_colors[si+1][j]-sp_colors[si][j])*lr) for j in range(3))
        draw.line([(tl_x,seg),(tl_x,seg+2)],fill=c,width=5)
    y=title_h+40
    for i,step_text in enumerate(steps):
        sc=T_STEPS[i%len(T_STEPS)]; cy=y; node_cy=cy+card_h//2; node_r=32
        glow_c=sc.get("glow",sc["fill"])
        draw.ellipse((tl_x-node_r-6,node_cy-node_r-6,tl_x+node_r+6,node_cy+node_r+6),fill=glow_c)
        draw.ellipse((tl_x-node_r,node_cy-node_r,tl_x+node_r,node_cy+node_r),fill=sc["acc"])
        ns=str(i+1); nw3=_text_w(draw,ns,fnum); nh3=_text_h(draw,ns,fnum)
        draw.text((tl_x-nw3//2,node_cy-nh3//2-2),ns,fill="#FFFFFF",font=fnum)
        draw.line([(tl_x+node_r+2,node_cy),(card_x-6,node_cy)],fill=sc["acc"],width=4)
        draw.polygon([(card_x-4,node_cy-10),(card_x+12,node_cy),(card_x-4,node_cy+10)],fill=sc["acc"])
        draw.rounded_rectangle((card_x+6,cy+6,card_x+card_w+6,cy+card_h+6),radius=T_RADIUS,fill=T_SHADOW)
        draw.rounded_rectangle((card_x,cy,card_x+card_w,cy+card_h),radius=T_RADIUS,fill=sc["fill"],outline=sc["bdr"],width=3)
        draw.rounded_rectangle((card_x+2,cy+8,card_x+10,cy+card_h-8),radius=4,fill=sc["acc"])
        draw.rounded_rectangle((card_x+4,cy+2,card_x+card_w-4,cy+8),radius=3,fill=sc["acc"])
        tx=card_x+28; text_w2=card_w-60; cpl=max(30,text_w2//18)
        s_title,s_desc=_split_step_text(step_text)
        title_lines=textwrap.wrap(s_title,width=cpl)[:2]
        for tli,tline in enumerate(title_lines):
            draw.text((tx,cy+18+tli*38),tline,fill=sc["txt"],font=fstep)
        desc_y=cy+18+len(title_lines)*38+10
        if s_desc:
            for li,line in enumerate(textwrap.wrap(s_desc,width=cpl)[:3]):
                draw.text((tx,desc_y+li*32),line,fill=T_TEXT,font=fdesc)
        frac=f"STEP {i+1}/{n}"; fw2=_text_w(draw,frac,fftr)
        draw.text((card_x+card_w-fw2-18,cy+18),frac,fill=T_MUTED,font=fftr)
        prog=(i+1)/n; bar_y=cy+card_h-12
        draw.rounded_rectangle((card_x+14,bar_y,card_x+card_w-14,bar_y+6),radius=3,fill=T_BORDER)
        draw.rounded_rectangle((card_x+14,bar_y,card_x+14+int((card_w-28)*prog),bar_y+6),radius=3,fill=sc["acc"])
        y+=card_h+card_gap


# ── LAYOUT 6: WATERFALL CASCADE (diagonal descending blocks) ──
def _meth_layout_waterfall(draw, img, steps, title, theme, fc_accent, W, H, title_h, footer_h):
    T_STEPS=theme["step_colors"]; T_CARD=theme["card"]; T_BORDER=theme["border"]
    T_TEXT=theme["text"]; T_MUTED=theme["muted"]; T_SHADOW=theme.get("card_shadow","#08090d")
    T_RADIUS=theme.get("card_radius",18); T_ACCENT=theme["accent"]
    n=len(steps); fnum=_get_font(42,True); fstep=_get_font(32,True); fdesc=_get_font(26); fa=_get_font(24)
    pad=50; card_w=max(520,(W-2*pad)//2); card_h=190
    avail_h=H-title_h-footer_h-40; gap_y=max(24,(avail_h-n*card_h)//(n+1))
    x_step=(W-2*pad-card_w)/max(n-1,1)
    positions=[]
    for i,step_text in enumerate(steps):
        sc=T_STEPS[i%len(T_STEPS)]
        cx=pad+int(i*x_step); cy=title_h+20+i*(card_h+gap_y)
        cx=max(pad,min(W-card_w-pad,cx)); cy=min(cy,H-footer_h-card_h-10)
        draw.rounded_rectangle((cx+6,cy+6,cx+card_w+6,cy+card_h+6),radius=T_RADIUS,fill=T_SHADOW)
        draw.rounded_rectangle((cx,cy,cx+card_w,cy+card_h),radius=T_RADIUS,fill=sc["fill"],outline=sc["bdr"],width=3)
        draw.rounded_rectangle((cx+4,cy+3,cx+card_w-4,cy+10),radius=4,fill=sc["acc"])
        nr=28; ncx=cx+46; ncy=cy+card_h//2
        pts=[(ncx,ncy-nr),(ncx+nr,ncy),(ncx,ncy+nr),(ncx-nr,ncy)]
        draw.polygon(pts,fill=sc["acc"])
        ns=str(i+1); nw=_text_w(draw,ns,fnum); nh=_text_h(draw,ns,fnum)
        draw.text((ncx-nw//2,ncy-nh//2-2),ns,fill="#FFFFFF",font=fnum)
        s_title,s_desc=_split_step_text(step_text)
        tx=cx+88; avail=card_w-104
        cpl=max(22,avail//18)
        title_lines=textwrap.wrap(s_title,width=cpl)[:2]
        for tli,tline in enumerate(title_lines):
            draw.text((tx,cy+18+tli*36),tline,fill=sc["txt"],font=fstep)
        desc_y=cy+18+len(title_lines)*36+8
        if s_desc:
            for li,line in enumerate(textwrap.wrap(s_desc,width=max(22,avail//16))[:3]):
                draw.text((tx,desc_y+li*30),line,fill=T_MUTED,font=fdesc)
        draw.rounded_rectangle((cx+14,cy+card_h-10,cx+card_w-14,cy+card_h-4),radius=3,fill=sc["acc"])
        positions.append((cx,cy,card_w,card_h))
    for i in range(len(positions)-1):
        sc=T_STEPS[i%len(T_STEPS)]; s=positions[i]; e=positions[i+1]
        _arrow(draw,(s[0]+s[2]//2,s[1]+s[3]+4),(e[0]+e[2]//2,e[1]-4),sc["acc"],4,16)


# ── LAYOUT REGISTRY (each methodology flowchart picks a different one) ──
METHODOLOGY_LAYOUTS = [
    ("horizontal", _meth_layout_horizontal),
    ("grid", _meth_layout_grid),
    ("radial", _meth_layout_radial),
    ("staircase", _meth_layout_staircase),
    ("timeline", _meth_layout_timeline),
    ("waterfall", _meth_layout_waterfall),
]


def render_methodology_flowchart(title: str, methodology_text: str, output_dir: Path,
                                  index: int = 0, pipeline_steps: list = None,
                                  theme: dict = None) -> str:
    """Render a methodology as a professional flowchart with RANDOMIZED layout.
    Each call picks a DIFFERENT layout type (horizontal, grid, radial, staircase, timeline, waterfall).
    Returns path to generated PNG."""
    from PIL import Image, ImageDraw
    if theme is None: theme = _pick_theme()
    steps = _extract_steps(pipeline_steps, methodology_text, title)
    # Guard against empty steps causing negative heights (Pillow y1 < y0 error)
    if not steps:
        steps = ["Start → Process → Output"]
    n = len(steps)

    # Pick layout — use index to cycle through layouts so each methodology in a run looks different
    layout_name, layout_fn = METHODOLOGY_LAYOUTS[(index + random.randint(0, 2)) % len(METHODOLOGY_LAYOUTS)]
    print(f"DEBUG: Methodology flowchart '{title[:30]}' using layout: {layout_name}", file=sys.stderr)

    T_BG=theme["bg"]; T_BG2=theme["bg2"]; T_STEPS=theme["step_colors"]; T_ACCENT=theme["accent"]
    fc_accent = T_STEPS[random.randint(0, len(T_STEPS)-1)]["acc"]

    pad=70; title_h=150; footer_h=70
    if layout_name == "horizontal":
        cols=min(n,3); rows=math.ceil(n/cols)
        W=3200; H=title_h+rows*(280+80)+footer_h+80
    elif layout_name == "grid":
        cols=3 if n>=6 else 2; rows=math.ceil(n/cols)
        W=3200; H=title_h+rows*(340+40)+footer_h+80
    elif layout_name == "radial":
        W=3800; H=3400
    elif layout_name == "staircase":
        W=3200; H=title_h+n*(200+40)+footer_h+80
    elif layout_name == "timeline":
        W=3200; H=title_h+n*220+(n-1)*50+footer_h+80
    elif layout_name == "waterfall":
        W=3400; H=title_h+n*(190+30)+footer_h+80
    else:
        W=3200; H=2400
    H=max(H,1400)

    img = Image.new("RGB", (W, H), T_BG)
    draw = ImageDraw.Draw(img)
    _gradient(draw, (0,0,W,H), T_BG, T_BG2)
    _draw_bg_pattern(draw, W, H, theme, title_h, footer_h)

    ft=_get_font(52,True); fsub=_get_font(28); fbadge=_get_font(30,True); fftr=_get_font(22)
    _meth_title_bar(draw, W, title_h, pad, title, n, theme, fc_accent, ft, fsub, fbadge)
    _meth_footer(draw, W, H, footer_h, title, theme, fc_accent, fftr)
    try:
        layout_fn(draw, img, steps, title, theme, fc_accent, W, H, title_h, footer_h)
    except Exception as e:
        # Guard against any geometry errors (e.g., y1 < y0) and return a simple placeholder image.
        print(f"DEBUG: Layout '{layout_name}' failed with {e}; creating placeholder.", file=sys.stderr)
        draw.rectangle((50, 50, W-50, H-50), outline="#FF5555", width=6)
        draw.text((80, 80), f"Methodology: {title}\n(Layout error; placeholder)", fill="#FF5555")

    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', title.lower())[:40]
    out = output_dir / f"methodology_{index}_{safe_name}.png"
    img.save(out, "PNG", dpi=(200, 200))
    return str(out)


# ═════════════════════════════════════════════════════════════════════
#  OPENROUTER LLM-DESIGNED ARCHITECTURE
# ═════════════════════════════════════════════════════════════════════

def _groq_design_arch(topic, domain, research_outputs, out_dir, theme=None, system_category="General / Web App"):
    from agents.llm_client import _call_openrouter_api, _openrouter_pool
    api_key, key_label = _openrouter_pool.get_next()
    if not api_key: raise RuntimeError("OPENROUTER_API_KEY not set")
    if theme is None: theme = _pick_theme()
    model = _resolve_openrouter_model(os.getenv("MODEL_VISUALIZER"), DEFAULT_OPENROUTER_MODEL)
    methods=[]; summaries=[]
    for r in research_outputs:
        if "summary" in r: summaries.append(r["summary"][:150])
        for m in r.get("key_methods",[]):
            # Handle dicts: {"name": "GAT", ...} or plain strings
            if isinstance(m, dict):
                methods.append(m.get("name", m.get("method", str(m))))
            else:
                methods.append(str(m))
    methods = list(set(methods))[:6]
    style_rules = STYLE_CONFIGS.get(system_category, STYLE_CONFIGS["General / Web App"])
    prompt=f"""Design a MULTI-LAYER SYSTEM ARCHITECTURE for "{topic}" ({domain}).
System Category: {system_category}
Layout Pattern: {style_rules['layout_emphasis']}
Required Elements: {style_rules['required_elements']}
Context: {chr(10).join(summaries[:3])}
Methods: {', '.join(methods)}
Return JSON ONLY:
{{"title":"{topic.title()}","subtitle":"{system_category} Architecture | {domain.title()}",
"layers":[{{"name":"LAYER","type":"client|gateway|service|ai_ml|data|infra","components":[{{"name":"N","sub":"S","icon":"X"}}]}}],
"connections":[{{"from":0,"to":1,"label":"Protocol"}}],
"cross_cuts":[{{"name":"Concern","icon":"C"}}],
"stats":{{"papers":{sum(len(r.get("top_papers",[]))for r in research_outputs)},"methods":{len(set(methods))},"agents":3}}}}
RULES: 4-6 layers, 3-4 components each (MINIMUM 3 per layer). Real tech names relevant to {system_category}. /no_think"""
    all_models = [
        model,
        "google/gemini-2.5-flash",
        "google/gemini-2.5-pro",
    ]
    # Deduplicate while preserving order
    seen=set(); models_dedup=[]
    for mm in all_models:
        if mm not in seen: seen.add(mm); models_dedup.append(mm)
    last_raw = None
    for m in models_dedup:
        for attempt in range(2):  # Retry each model once
            try:
                print(f"DEBUG: OpenRouter arch design attempt {attempt+1} with {m}", file=sys.stderr)
                raw = _call_openrouter_api(
                    api_key=api_key,
                    model=m,
                    messages=[{"role":"user","content":prompt}],
                    max_tokens=4000,
                    temperature=0.4+attempt*0.2,
                )
                raw = raw.strip() if raw else ""
                if raw:
                    last_raw = raw
                    spec=_parse_json(raw)
                    if spec and "layers" in spec:
                        # Validate spec has actual content
                        if len(spec["layers"]) < 2:
                            print(f"DEBUG: Spec has only {len(spec['layers'])} layers, retrying", file=sys.stderr)
                            continue
                        spec.setdefault("stats",{"papers":0,"methods":0,"agents":3})
                        spec.setdefault("connections",[])
                        spec.setdefault("cross_cuts",[])
                        # Ensure connections exist between layers
                        if not spec["connections"]:
                            for ci in range(len(spec["layers"])-1):
                                spec["connections"].append({"from":ci,"to":ci+1,"label":""})
                        print(f"DEBUG: OpenRouter arch design successful with {m}: {len(spec['layers'])} layers", file=sys.stderr)
                        try:
                            return _render_architecture(spec,topic,domain,out_dir,theme=theme)
                        except Exception as e:
                            # Prevent downstream crashes; emit placeholder architecture image
                            print(f"DEBUG: _render_architecture failed: {e}", file=sys.stderr)
                            try:
                                from PIL import Image, ImageDraw
                                ph = Image.new("RGB", (1600, 900), "white")
                                d = ImageDraw.Draw(ph)
                                d.text((60,60), f"Architecture Placeholder\n{topic}", fill="black")
                                ph_path = out_dir / f"architecture_placeholder.png"
                                ph.save(ph_path, "PNG")
                                return str(ph_path)
                            except Exception as e2:
                                print(f"DEBUG: Architecture placeholder failed: {e2}", file=sys.stderr)
                                raise e
                    else:
                        print(f"DEBUG: OpenRouter {m} returned invalid JSON (no layers key). Raw[:200]: {raw[:200]}", file=sys.stderr)
            except Exception as e:
                err_str = str(e)
                print(f"DEBUG: OpenRouter {m} attempt {attempt+1} failed: {err_str[:200]}",file=sys.stderr)
                if "429" in err_str or "rate_limit" in err_str.lower():
                    import time as _time; _time.sleep(5)
                    continue
                elif "decommissioned" in err_str or "not found" in err_str.lower():
                    break  # Skip this model entirely
                break
    # Final fallback: build spec from category defaults
    print(f"DEBUG: All OpenRouter models failed for arch design, using category fallback", file=sys.stderr)
    raise RuntimeError("All OpenRouter models failed for architecture design")

def _parse_json(raw):
    text=re.sub(r"<think>.*?</think>","",raw,flags=re.DOTALL).strip()
    text=re.sub(r"```(?:json)?\s*","",text); text=re.sub(r"```\s*$","",text).strip()
    try: return _json.loads(text)
    except: pass
    s=text.find("{")
    if s==-1: return None
    d=0
    for i in range(s,len(text)):
        if text[i]=="{":d+=1
        elif text[i]=="}":
            d-=1
            if d==0:
                try: return _json.loads(text[s:i+1])
                except: return None
    return None

# ═════════════════════════════════════════════════════════════════════
#  DOMAIN-SPECIFIC STYLE CONFIGS  (Step 3.1)
#  Maps user-selected system category → visual rules for prompt injection
# ═════════════════════════════════════════════════════════════════════

STYLE_CONFIGS = {
    "General / Web App": {
        "icon_rules": "Database -> Cylinder; Service -> Rectangle; User -> Stick Figure; Cache -> Rounded Rectangle with Lightning.",
        "color_palette": "ByteByteGo Standard: Light Blue (#4285F4), White (#FFFFFF), Grey (#E0E0E0), Green accent (#34A853).",
        "layout_emphasis": "3-Tier Architecture (Client -> Server -> DB). Clear request/response flow.",
        "required_elements": "CDN, Load Balancer, API Gateway, Web Server, Database, Cache Layer.",
    },
    "AI & Machine Learning": {
        "icon_rules": "Model -> Neural Network Node; Data -> Cylinder Cluster (Data Lake); Training -> GPU Icon; Pipeline -> Conveyor; Vector Store -> Hexagonal DB.",
        "color_palette": "Futuristic: Purple (#660099), Neon Blue (#00CCFF), Dark Grey (#333333), Violet accent (#BC8CFF).",
        "layout_emphasis": "Data Pipeline: Ingestion -> Preprocessing -> Feature Engineering -> Training -> Evaluation -> Inference -> Monitoring.",
        "required_elements": "Data Lake, Feature Store, Model Registry, Training Cluster (GPU), Inference API, Vector DB, Experiment Tracker, Orchestrator (Airflow/Kubeflow).",
    },
    "Fintech & Payments": {
        "icon_rules": "Database -> Ledger/Vault Icon; API -> Shield Icon; Service -> Bank Building; Queue -> Parallelogram; Gateway -> Diamond with Lock.",
        "color_palette": "Trustworthy: Navy Blue (#003366), Emerald Green (#009933), Gold (#FFD700), Dark Grey (#2C2C2C).",
        "layout_emphasis": "Security-first layout. Transaction Flow with ACID guarantees. Show encryption boundaries.",
        "required_elements": "Payment Gateway (Stripe/PayPal), Firewalls, Load Balancers, Fraud Detection Engine, Ledger DB, PCI-DSS Compliance Boundary, Notification Service.",
    },
    "DevOps & CI/CD Infrastructure": {
        "icon_rules": "Pipeline -> Conveyor Belt/Infinity Loop; Container -> Shipping Cube (Docker); Server -> Rack; Registry -> Package Icon; Monitoring -> Dashboard.",
        "color_palette": "Operational: Orange (#FF6600), Slate Grey (#708090), White (#FFFFFF), Blue accent (#1E90FF).",
        "layout_emphasis": "Linear Pipeline Flow (Left to Right): Code -> Build -> Test -> Deploy -> Monitor.",
        "required_elements": "Git Repo, Build Server (Jenkins/GH Actions), Container Registry, K8s Cluster, Helm Charts, Monitoring Stack (Prometheus/Grafana), Secrets Manager.",
    },
    "Real-World Case Study": {
        "icon_rules": "User -> Person Icon; Service -> Rounded Rectangle; Database -> Cylinder; External API -> Cloud Shape; Queue -> Parallelogram.",
        "color_palette": "Professional: Teal (#008080), Coral (#FF6F61), Navy (#003366), Light Grey (#F5F5F5).",
        "layout_emphasis": "End-to-end user journey. Show real traffic flow, failure points, and scaling layers.",
        "required_elements": "User Client, API Gateway, Microservices, Message Queue, Database Cluster, CDN, Monitoring & Alerting.",
    },
    "Data Engineering & Big Data": {
        "icon_rules": "Data Source -> Cylinder with Arrow; Pipeline -> Conveyor; Warehouse -> Large Cylinder Stack; Dashboard -> Screen Icon; Stream -> Wave Line.",
        "color_palette": "Data: Ocean Blue (#0077B6), Teal (#00B4D8), Sandy (#F4A261), Dark Slate (#264653).",
        "layout_emphasis": "Data Flow: Sources -> Ingestion (Batch/Stream) -> Storage (Lake/Warehouse) -> Transform (ETL/ELT) -> Serve (BI/API).",
        "required_elements": "Data Sources (APIs/DBs/Files), Kafka/Kinesis, Spark/Flink, Data Lake (S3/GCS), Data Warehouse (BigQuery/Snowflake), dbt, Orchestrator (Airflow), BI Dashboard.",
    },
}

# ═════════════════════════════════════════════════════════════════════
#  PAPERBANANA DEEP INTEGRATION — 5-Agent Pipeline Optimization
#  Phase 1: Retriever → Planner → Stylist  (linear planning)
#  Phase 2: Visualizer ↔ Critic  (3 iterative refinement rounds)
#
#  KEY INSIGHT: "The Planner can only produce diagrams as good as
#  the references it learns from." — Therefore, source_context must
#  read like a REAL academic methodology section (not an image prompt).
#  PaperBanana's Stylist handles visual aesthetics internally.
#
#  VARIETY: Each generation builds a unique academic-style methodology
#  description with domain-specific components, data flow, and pipeline
#  architecture so PaperBanana's Retriever matches the best references.
# ═════════════════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════════════════
#  ELITE BLUEPRINT FRAMEWORK — PaperBanana Prompt Engineering
#  Generates spatially-aware, structurally rigorous diagram blueprints
#  that push PaperBanana's 5-agent pipeline to elite-level output.
#
#  Structure per blueprint:
#    1. CANVAS & THEME SPECIFICATION
#    2. HIERARCHICAL LAYOUT DEFINITION (zones/swimlanes/tiers)
#    3. NODE DEFINITIONS (shape, color, border, label, icon)
#    4. EDGE ROUTING & CONNECTIONS (arrow types, labels, routing)
#    5. LEGEND & ANNOTATIONS
# ═════════════════════════════════════════════════════════════════════

# ── Academic Figure Caption Templates (communicative_intent) ──
# PaperBanana uses this as the "caption" for the generated figure.
# Specific, descriptive captions guide the Retriever and Planner better.
CAPTION_TEMPLATES = {
    "architecture": [
        "Figure 1: End-to-end system architecture of the proposed {topic} framework showing data flow from input ingestion through processing layers to output generation. All modules are depicted as labeled nodes with directed edges showing data and control flow between layers.",
        "Figure 1: High-level layered architecture for {topic} with {n_methods} core methods arranged in a strict top-down hierarchy. Each tier contains typed processing nodes connected by labeled directed edges indicating data transformation, API calls, and feedback loops.",
        "Figure 1: Complete architectural blueprint of the {topic} system. The diagram uses a clean left-to-right layout with {n_agents} processing stages, color-coded swimlanes per functional layer, and annotated connections showing protocol types and data formats.",
    ],
    "methodology": [
        "Figure {idx}: Detailed methodology pipeline for {title} showing {n_steps} sequential stages. Each stage is a labeled rounded rectangle node with directed arrows indicating data flow. Includes feedback loops and quality checkpoints between processing phases.",
        "Figure {idx}: Schematic of the {title} approach as a multi-phase pipeline. Phase boundaries are marked with dashed separators. Nodes use consistent color coding: blue for data operations, green for model components, orange for evaluation stages.",
        "Figure {idx}: Architecture of the {title} framework with explicit node shapes (rectangles for processes, cylinders for storage, diamonds for decisions) connected by solid directed arrows with edge labels describing data transformations.",
    ],
    "workflow": [
        "Figure 2: Multi-agent research workflow for {topic} showing three parallel research streams converging at a synthesis node. Uses swimlane layout with labeled directed edges for data handoff between agents.",
        "Figure 2: End-to-end process flow for {topic} from data collection through analysis to report generation. Nodes are color-coded by phase with annotated edges showing intermediate outputs at each transition.",
    ],
}

# ── Elite Blueprint Theme Presets (injected into source_context) ──
BLUEPRINT_THEMES = [
    {
        "name": "Academic Standard",
        "spec": "Clean white background (#FFFFFF) with light gray grid lines. "
                "Node fills use soft pastels: blue (#E3F2FD) for data operations, "
                "green (#E8F5E9) for model/compute, orange (#FFF3E0) for evaluation, "
                "purple (#F3E5F5) for orchestration. All borders are 2px solid in the darker "
                "shade of each fill color. Text is black (#202124), 14pt sans-serif, "
                "bold for node titles, regular for subtitles. High contrast throughout.",
    },
    {
        "name": "Dark Cybernetic",
        "spec": "Deep navy background (#0d1117) with subtle dot-grid pattern. "
                "Node fills use rich dark tones: teal (#0A2E2E) for input, "
                "indigo (#1A2A3D) for processing, purple (#2D1A3D) for AI/ML, "
                "dark red (#3D1A1A) for storage. Borders are 2px glowing neon: "
                "cyan (#64FFDA), blue (#58A6FF), purple (#BC8CFF), red (#F85149). "
                "Text is light (#E6EDF3), bold titles with glow effect. "
                "Arrows use glowing accent colors with 3px width.",
    },
    {
        "name": "Warm Research",
        "spec": "Warm cream background (#FFFEF7) with faint diagonal line pattern. "
                "Node fills: coral (#FFF0E5) for inputs, gold (#FFF5CC) for processing, "
                "sky blue (#E5F0FF) for compute, lavender (#F5E5FF) for evaluation. "
                "Borders are 2px solid in saturated versions of fills. "
                "Text is dark charcoal (#3D3D3D), titles 16pt bold, subtitles 12pt regular. "
                "Directed arrows are 2px dark gray with clean mid-edge labels.",
    },
]

# ── Node Shape Vocabulary (category-specific) ──
CATEGORY_NODE_SHAPES = {
    "General / Web App": {
        "data_store": ("Cylinder", "#E3F2FD", "#4285F4"),
        "service": ("Rounded Rectangle", "#E8F5E9", "#34A853"),
        "gateway": ("Hexagon", "#FFF3E0", "#FB8C00"),
        "user": ("Rounded Rectangle with Person Icon", "#F3E5F5", "#9C27B0"),
        "cache": ("Rounded Rectangle with Lightning", "#FFEBEE", "#E53935"),
        "queue": ("Parallelogram", "#E0F7FA", "#00ACC1"),
    },
    "AI & Machine Learning": {
        "data_source": ("Cylinder Cluster", "#E3F2FD", "#4285F4"),
        "model": ("Rounded Rectangle with Brain Icon", "#F3E5F5", "#9C27B0"),
        "training": ("Rectangle with GPU Icon", "#FFF3E0", "#FB8C00"),
        "pipeline": ("Rounded Rectangle", "#E8F5E9", "#34A853"),
        "store": ("Hexagonal DB", "#FFEBEE", "#E53935"),
        "monitor": ("Dashboard Rectangle", "#E0F7FA", "#00ACC1"),
    },
    "Fintech & Payments": {
        "client": ("Rounded Rectangle with Person", "#E3F2FD", "#4285F4"),
        "security": ("Diamond with Lock", "#FFEBEE", "#E53935"),
        "transaction": ("Rectangle", "#E8F5E9", "#34A853"),
        "compliance": ("Rounded Rectangle with Shield", "#FFF3E0", "#FB8C00"),
        "vault": ("Cylinder with Lock", "#F3E5F5", "#9C27B0"),
        "queue": ("Parallelogram", "#E0F7FA", "#00ACC1"),
    },
    "DevOps & CI/CD Infrastructure": {
        "repo": ("Rectangle with Branch Icon", "#E3F2FD", "#4285F4"),
        "build": ("Rounded Rectangle", "#FFF3E0", "#FB8C00"),
        "container": ("Cube (Docker)", "#E8F5E9", "#34A853"),
        "deploy": ("Rounded Rectangle", "#F3E5F5", "#9C27B0"),
        "monitor": ("Dashboard Rectangle", "#E0F7FA", "#00ACC1"),
        "registry": ("Cylinder", "#FFEBEE", "#E53935"),
    },
    "Real-World Case Study": {
        "user": ("Rounded Rectangle with Person", "#E3F2FD", "#4285F4"),
        "service": ("Rounded Rectangle", "#E8F5E9", "#34A853"),
        "database": ("Cylinder", "#FFEBEE", "#E53935"),
        "external": ("Cloud Shape", "#FFF3E0", "#FB8C00"),
        "queue": ("Parallelogram", "#E0F7FA", "#00ACC1"),
        "cdn": ("Hexagon", "#F3E5F5", "#9C27B0"),
    },
    "Data Engineering & Big Data": {
        "source": ("Cylinder with Arrow", "#E3F2FD", "#4285F4"),
        "ingestion": ("Rounded Rectangle", "#FFF3E0", "#FB8C00"),
        "processing": ("Rectangle", "#E8F5E9", "#34A853"),
        "warehouse": ("Large Cylinder Stack", "#FFEBEE", "#E53935"),
        "dashboard": ("Screen Rectangle", "#E0F7FA", "#00ACC1"),
        "orchestrator": ("Rounded Rectangle with Gear", "#F3E5F5", "#9C27B0"),
    },
}


def _build_elite_blueprint(topic, domain, research_outputs, system_category="General / Web App"):
    """Build an Elite Blueprint for PaperBanana with Anti-Spaghetti Protocol.
    
    Generates a structured, layout-explicit prompt that PaperBanana's 5-agent pipeline
    (Retriever → Planner → Stylist → Visualizer ↔ Critic) can translate into
    elite-quality methodology and architecture diagrams.
    
    The blueprint includes:
      0. MASTER AESTHETIC CONSTRAINTS (Anti-Spaghetti Protocol)
      1. Canvas & Theme Specification
      2. Hierarchical Layout Definition (grid-snapped swimlanes)
      3. Typed Node Definitions (shape, color, label, uniform sizing)
      4. Edge Routing & Connections (orthogonal only, no diagonals)
      5. Legend & Annotations
    """
    # ─── Extract research data ───
    methods = []
    key_papers = []
    methodologies = []
    datasets = []
    
    for r in research_outputs:
        for m in r.get("key_methods", []):
            s = m.get("name", m.get("method", str(m))) if isinstance(m, dict) else str(m)
            if s and s not in methods:
                methods.append(s)
        for p in r.get("top_papers", [])[:4]:
            key_papers.append(p.get("title", ""))
        for d in r.get("datasets_used", []):
            if d not in datasets:
                datasets.append(d)
        for scope in r.get("future_scope_methodologies", []):
            title = scope.get("scope_title", "")
            meth = scope.get("proposed_methodology", "")[:500]
            steps = scope.get("pipeline_steps", [])
            if title:
                methodologies.append({
                    "title": title,
                    "methodology": meth,
                    "steps": steps[:8],
                })

    style_rules = STYLE_CONFIGS.get(system_category, STYLE_CONFIGS["General / Web App"])
    node_shapes = CATEGORY_NODE_SHAPES.get(system_category, CATEGORY_NODE_SHAPES["General / Web App"])
    bp_theme = random.choice(BLUEPRINT_THEMES)
    
    research_methods_str = ", ".join(methods[:10]) if methods else "standard processing pipeline"
    
    # ─── Get category-specific layers ───
    spec = _build_arch_spec(topic, domain, research_outputs, system_category)
    layers = spec.get("layers", [])
    connections = spec.get("connections", [])
    cross_cuts = spec.get("cross_cuts", [])
    
    # ═══ BUILD THE ELITE BLUEPRINT ═══
    blueprint = []
    
    # ─── 0. MASTER AESTHETIC CONSTRAINTS (Anti-Spaghetti Protocol) ───
    blueprint.append(
        "=== MASTER AESTHETIC CONSTRAINTS ===\n"
        "CRITICAL RULES — VIOLATING ANY OF THESE INVALIDATES THE ENTIRE DIAGRAM:\n"
        "  1. GRID LAYOUT: All nodes MUST snap to an invisible grid. No free-floating nodes.\n"
        "  2. ZERO OVERLAP: Absolute zero-tolerance for overlapping nodes, text, or edges.\n"
        "  3. ORTHOGONAL EDGES ONLY: All connection lines use sharp 90-degree turns.\n"
        "     NEVER use diagonal lines. NEVER use curved spaghetti lines.\n"
        "  4. NO RADIAL/SPOKE LAYOUTS: NEVER arrange nodes in a circle or radial pattern.\n"
        "     NEVER place a central hub with nodes radiating outward. This is FORBIDDEN.\n"
        "  5. WHITE-SPACE: Maintain minimum 20% empty white-space across the canvas.\n"
        "  6. TEXT INTEGRITY: All text fully visible, centered, with 16px minimum padding.\n"
        "     No text edge-clipping. No text truncation.\n"
        "  7. EDGE LABELS: Must have a solid white background box. Must not intersect nodes.\n"
        "  8. UNIFORM NODE SIZE: Nodes within the same tier must have identical dimensions.\n"
        "  9. ONE FLOW DIRECTION: Top-Down is the dominant flow. No backwards arrows."
    )
    
    # ─── 1. CANVAS & THEME SPECIFICATION ───
    blueprint.append(
        f"\n=== CANVAS & THEME ===\n"
        f"Aspect Ratio: Landscape, 16:9 (1920x1080).\n"
        f"Visual Theme: {bp_theme['spec']}\n"
        f"Typography: Bold 14pt sans-serif for node titles, regular 11pt for subtitles, "
        f"10pt for edge labels. All text high-contrast and perfectly legible."
    )
    
    # ─── 2. HIERARCHICAL LAYOUT DEFINITION (Grid-Snapped Swimlanes) ───
    tier_descs = []
    for i, layer in enumerate(layers):
        comps = [c.get("name", "") for c in layer.get("components", [])]
        tier_descs.append(f"  Tier {i+1} (Row {i+1}): {layer['name']} — [{', '.join(comps)}]")
    
    blueprint.append(
        f"\n=== HIERARCHICAL LAYOUT ===\n"
        f"Spatial Flow: Strict Top-Down layered architecture.\n"
        f"Grid Structure: {len(layers)} horizontal swimlanes stacked vertically.\n"
        f"Each swimlane is a full-width rectangular band with a faint background tint.\n"
        f"Swimlanes (top to bottom):\n" + "\n".join(tier_descs) + "\n\n"
        f"LAYOUT RULES:\n"
        f"  - Components within each swimlane: single horizontal row, evenly spaced.\n"
        f"  - Swimlanes separated by thin dashed horizontal lines, 40px vertical gap.\n"
        f"  - Connected nodes across tiers must be vertically aligned.\n"
        f"  - Swimlane label: bold vertical text on the LEFT side of each band."
    )
    
    # ─── 3. NODE DEFINITIONS ───
    blueprint.append(f"\n=== NODE DEFINITIONS ===")
    node_idx = 0
    for li, layer in enumerate(layers):
        layer_type = layer.get("type", "service")
        blueprint.append(f"\n--- Tier {li+1}: {layer['name']} ---")
        
        for ci, comp in enumerate(layer.get("components", [])):
            node_idx += 1
            name = comp.get("name", f"Component {ci+1}")
            sub = comp.get("sub", "")
            icon = comp.get("icon", "")
            
            # Determine shape from category vocabulary
            shape_keys = list(node_shapes.keys())
            shape_key = shape_keys[li % len(shape_keys)]
            shape_name, fill_color, border_color = node_shapes[shape_key]
            
            blueprint.append(
                f"  [Node {node_idx}: \"{name}\"] "
                f"(Shape: {shape_name}, Fill: {fill_color}, Border: 2px solid {border_color}, "
                f"Icon: \"{icon}\", Subtitle: \"{sub}\", Text: Bold centered title, regular subtitle below)"
            )
    
    # ─── 4. EDGE ROUTING & CONNECTIONS (Orthogonal Anti-Spaghetti Protocol) ───
    blueprint.append(
        f"\n=== EDGE ROUTING & CONNECTIONS ===\n"
        f"ROUTING PROTOCOL (MANDATORY):\n"
        f"  - ALL edges use ORTHOGONAL routing: horizontal and vertical segments ONLY.\n"
        f"  - Sharp 90-degree turns. NO diagonal lines. NO curved lines. NO spaghetti.\n"
        f"  - Edges route AROUND nodes, never through them.\n"
        f"  - Edge labels: midpoint placement, solid white background box, no intersections.\n"
        f"  - Minimize edge crossings by vertically aligning connected nodes."
    )
    
    for conn in connections:
        f_idx = conn.get("from", 0)
        t_idx = conn.get("to", 1)
        label = conn.get("label", "Data")
        
        f_name = layers[f_idx]["name"] if f_idx < len(layers) else "Source"
        t_name = layers[t_idx]["name"] if t_idx < len(layers) else "Target"
        
        blueprint.append(
            f"  Connect [{f_name}] → [{t_name}]: solid orthogonal arrow (2px), "
            f"label \"{label}\" (white background box). "
            f"Route: vertical drop from source bottom to target top."
        )
    
    # Cross-cutting connections (dashed)
    if cross_cuts:
        cc_names = [c.get("name", "Service") for c in cross_cuts]
        blueprint.append(
            f"\n  Cross-cutting concerns spanning all tiers (shown as a vertical dashed sidebar):\n"
            f"  [{', '.join(cc_names)}] — rendered as a thin vertical panel on the right side "
            f"with dashed border, connected to every tier via light dashed arrows."
        )
    
    # ─── 5. LEGEND & ANNOTATIONS ───
    shape_legend_items = []
    for key, (shape, fill, border) in list(node_shapes.items())[:6]:
        shape_legend_items.append(f"{shape} ({fill}) = {key.replace('_', ' ').title()}")
    
    blueprint.append(
        f"\n=== LEGEND & ANNOTATIONS ===\n"
        f"Place a clean boxed legend in the bottom-right corner containing:\n"
        f"  Shape/Color Legend:\n"
        + "\n".join(f"    • {item}" for item in shape_legend_items) + "\n"
        f"  Arrow Legend:\n"
        f"    • Solid arrow = Primary data flow\n"
        f"    • Dashed arrow = Cross-cutting / monitoring\n"
        f"    • Bidirectional arrow = Feedback loop\n"
        f"\n  Title: \"{topic.title()}\" (top-center, 24pt bold)\n"
        f"  Subtitle: \"{system_category} | {domain.title()}\" (below title, 14pt regular)\n"
        f"  Footer: \"Key Methods: {', '.join(methods[:5]) if methods else 'N/A'}\" (bottom-left, 10pt muted)"
    )
    
    # ─── 6. ACADEMIC CONTEXT (for Retriever matching) ───
    # PaperBanana's Retriever still benefits from academic prose alongside the blueprint
    blueprint.append(
        f"\n=== ACADEMIC CONTEXT ===\n"
        f"This diagram illustrates the proposed {system_category.lower()} architecture for research on "
        f"\"{topic}\" in the {domain} domain. The system comprises {len(layers)} functional tiers "
        f"with {sum(len(l.get('components',[])) for l in layers)} processing modules. "
        f"Core technical methods include {research_methods_str}. "
        f"{'The architecture draws from ' + str(len(key_papers)) + ' recent publications.' if key_papers else ''}"
    )
    
    if methodologies:
        meth_titles = [m["title"] for m in methodologies[:3]]
        blueprint.append(
            f"Research methodologies depicted: {'; '.join(meth_titles)}."
        )
    
    if datasets:
        blueprint.append(
            f"Evaluated on: {', '.join(datasets[:5])}."
        )
    
    return "\n".join(blueprint)


# ── Legacy alias for backward compatibility ──
def _build_academic_source_context(topic, domain, research_outputs, system_category="General / Web App"):
    """Delegates to the Elite Blueprint builder."""
    return _build_elite_blueprint(topic, domain, research_outputs, system_category)


def _build_methodology_source_context(scope_item, topic, domain, all_methods):
    """Build an Elite Blueprint for a SPECIFIC methodology / future scope.
    
    Uses the same spatially-aware framework as architecture blueprints,
    tailored for methodology pipeline diagrams. Each methodology gets
    explicit node definitions, edge routing, and canvas specs.
    """
    title = scope_item.get("scope_title", "Proposed Methodology")
    methodology = scope_item.get("proposed_methodology", "")
    steps = scope_item.get("pipeline_steps", [])
    problem = scope_item.get("problem_statement", "")
    
    bp_theme = random.choice(BLUEPRINT_THEMES)
    
    blueprint = []
    
    # ─── 0. MASTER AESTHETIC CONSTRAINTS (Anti-Spaghetti Protocol) ───
    blueprint.append(
        "=== MASTER AESTHETIC CONSTRAINTS ===\n"
        "CRITICAL RULES — VIOLATING ANY OF THESE INVALIDATES THE ENTIRE DIAGRAM:\n"
        "  1. GRID LAYOUT: All nodes MUST snap to an invisible grid. No free-floating nodes.\n"
        "  2. ZERO OVERLAP: Absolute zero-tolerance for overlapping nodes, text, or edges.\n"
        "  3. ORTHOGONAL EDGES ONLY: All connection lines use sharp 90-degree turns.\n"
        "     NEVER use diagonal lines. NEVER use curved spaghetti lines.\n"
        "  4. NO RADIAL/SPOKE/CIRCULAR LAYOUTS: NEVER arrange nodes in a circle.\n"
        "     NEVER place a central hub with nodes radiating outward. This is FORBIDDEN.\n"
        "     This is a SEQUENTIAL PIPELINE — nodes go in a LINE, not a CIRCLE.\n"
        "  5. WHITE-SPACE: Maintain minimum 20% empty white-space across the canvas.\n"
        "  6. TEXT INTEGRITY: All text fully visible, centered, with 16px minimum padding.\n"
        "  7. UNIFORM NODE SIZE: All pipeline step nodes must have identical dimensions.\n"
        "  8. SEQUENTIAL FLOW: Nodes are arranged in a straight line (left-to-right or top-down)."
    )
    
    # ─── 1. CANVAS & THEME ───
    blueprint.append(
        f"\n=== CANVAS & THEME ===\n"
        f"Aspect Ratio: Landscape, 16:9 (1920x1080).\n"
        f"Visual Theme: {bp_theme['spec']}\n"
        f"Typography: Bold 14pt for step titles, regular 11pt for descriptions."
    )
    
    # ─── 2. LAYOUT (Strict Linear — NO Radial) ───
    n_steps_actual = len(steps) if steps else 5
    stage_names = ["Input Processing", "Feature Engineering", "Core Computation",
                   "Model Training", "Optimization", "Evaluation", "Deployment", "Monitoring"]
    
    # Use 2-row grid for 5+ steps, single row for fewer
    if n_steps_actual <= 4:
        layout_desc = (
            f"Spatial Flow: Strict Left-to-Right linear pipeline.\n"
            f"All {n_steps_actual} nodes in a single horizontal row, evenly spaced.\n"
            f"Nodes connected by horizontal orthogonal arrows pointing right."
        )
    else:
        row1_count = (n_steps_actual + 1) // 2
        row2_count = n_steps_actual - row1_count
        layout_desc = (
            f"Spatial Flow: Left-to-Right, wrapping to a second row.\n"
            f"Row 1: Steps 1-{row1_count} in a horizontal line (left to right).\n"
            f"Row 2: Steps {row1_count+1}-{n_steps_actual} in a horizontal line (left to right).\n"
            f"Rows are stacked vertically with a 60px gap.\n"
            f"The last node on Row 1 connects down to the first node on Row 2 via an orthogonal elbow arrow."
        )
    
    blueprint.append(
        f"\n=== HIERARCHICAL LAYOUT ===\n"
        f"{layout_desc}\n\n"
        f"LAYOUT RULES:\n"
        f"  - This is a SEQUENTIAL PIPELINE. Each step follows the previous one.\n"
        f"  - Nodes are arranged in a STRAIGHT LINE, NOT a circle or radial pattern.\n"
        f"  - All nodes are the same size (uniform width and height).\n"
        f"  - Evenly spaced with large gaps between nodes."
    )
    
    # ─── 3. NODE DEFINITIONS ───
    blueprint.append(f"\n=== NODE DEFINITIONS ===")
    
    node_colors = [
        ("#E3F2FD", "#4285F4"), ("#E8F5E9", "#34A853"),
        ("#FFF3E0", "#FB8C00"), ("#F3E5F5", "#9C27B0"),
        ("#FFEBEE", "#E53935"), ("#E0F7FA", "#00ACC1"),
        ("#FFF9C4", "#F9A825"), ("#F1F8E9", "#558B2F"),
    ]
    
    if steps:
        for i, step in enumerate(steps[:8]):
            stage = stage_names[i % len(stage_names)]
            fill, border = node_colors[i % len(node_colors)]
            blueprint.append(
                f"  [Node {i+1}: \"{step[:50]}\"] "
                f"(Shape: Rounded Rectangle, Fill: {fill}, Border: 2px solid {border}, "
                f"Label: \"{stage}\", Size: uniform, Padding: 16px, Text: Bold centered.)"
            )
    else:
        generic_steps = ["Data Input", "Preprocessing", "Core Processing", "Analysis", "Output"]
        for i, step in enumerate(generic_steps):
            fill, border = node_colors[i % len(node_colors)]
            blueprint.append(
                f"  [Node {i+1}: \"{step}\"] "
                f"(Shape: Rounded Rectangle, Fill: {fill}, Border: 2px solid {border}, "
                f"Size: uniform, Padding: 16px, Text: Bold centered.)"
            )
    
    # ─── 4. EDGE ROUTING (Orthogonal Only — Anti-Spaghetti) ───
    blueprint.append(
        f"\n=== EDGE ROUTING & CONNECTIONS ===\n"
        f"ROUTING PROTOCOL (MANDATORY):\n"
        f"  - ALL edges use ORTHOGONAL routing: horizontal and vertical segments ONLY.\n"
        f"  - Sharp 90-degree turns. NO diagonal lines. NO curved lines. NO spaghetti.\n"
        f"  - Arrows point in the flow direction (left-to-right or top-to-bottom)."
    )
    
    actual_steps = steps if steps else ["Data Input", "Preprocessing", "Core Processing", "Analysis", "Output"]
    for i in range(len(actual_steps[:8]) - 1):
        blueprint.append(
            f"  Connect [Node {i+1}] -> [Node {i+2}]: solid orthogonal arrow (2px). "
            f"Route: straight horizontal segment, no diagonal."
        )
    
    # Feedback loop if applicable
    if len(actual_steps) > 3:
        blueprint.append(
            f"  Connect [Node {len(actual_steps[:8])}] -> [Node 2]: dashed orthogonal arrow "
            f"labeled \"Feedback / Iteration\". Route: orthogonal elbow BELOW the pipeline row."
        )
    
    # ─── 5. LEGEND ───
    blueprint.append(
        f"\n=== LEGEND & ANNOTATIONS ===\n"
        f"Title: \"{title}\" (top-center, 20pt bold)\n"
        f"Subtitle: \"Methodology Pipeline | {domain.title()}\" (below title, 12pt)\n"
        f"Legend (bottom-right box):\n"
        f"  • Solid arrow = Sequential data flow\n"
        f"  • Dashed arrow = Feedback / iteration loop"
    )
    
    # ─── 6. ACADEMIC CONTEXT ───
    blueprint.append(
        f"\n=== ACADEMIC CONTEXT ===\n"
        f"This diagram depicts the proposed methodology: {title}. "
        f"{'Problem addressed: ' + problem[:200] + '. ' if problem else ''}"
        f"The approach implements a {n_steps_actual}-stage pipeline "
        f"{'with stages: ' + ' → '.join(steps[:6]) + '.' if steps else '.'}"
    )
    
    if methodology:
        blueprint.append(f"Detailed approach: {methodology[:600]}")
    
    if all_methods:
        relevant = random.sample(all_methods, min(4, len(all_methods)))
        blueprint.append(
            f"Builds upon: {', '.join(relevant)}."
        )
    
    return "\n".join(blueprint)


def _build_communicative_intent(topic, diagram_type="architecture", 
                                  index=0, title="", n_methods=0, n_papers=0, 
                                  n_agents=3, n_steps=0):
    """Build a specific, descriptive academic figure caption.
    
    PaperBanana uses communicative_intent as the figure caption. Specific captions
    guide the Retriever to select better reference examples and help the Planner
    generate more accurate diagram descriptions.
    """
    templates = CAPTION_TEMPLATES.get(diagram_type, CAPTION_TEMPLATES["architecture"])
    template = random.choice(templates)
    
    return template.format(
        topic=topic[:80],
        title=title[:60] if title else topic[:60],
        idx=index + 1,
        n_methods=n_methods or 6,
        n_papers=n_papers or 10,
        n_agents=n_agents,
        n_steps=n_steps or 5,
    )


# ── PaperBanana Async Pipeline with Quality Settings ──

async def _paperbanana_generate(source_context, communicative_intent, out_dir,
                                 iterations=1, diagram_type="METHODOLOGY"):
    """Run PaperBanana's full 5-agent pipeline with optimal settings.
    
    Phase 1 (Linear): Retriever → Planner → Stylist
    Phase 2 (Iterative, {iterations} rounds): Visualizer ↔ Critic
    
    Key: source_context should read like academic methodology text.
    Key: communicative_intent should be a descriptive figure caption.
    Key: 3 refinement iterations is optimal (paper default).
    Key: 10 retrieval examples gives best reference coverage.
    
    OpenRouter Key Rotation: If primary key is quota-exhausted, tries backup keys.
    """
    from paperbanana import PaperBananaPipeline
    from paperbanana.core.config import Settings
    from paperbanana.core.types import GenerationInput, DiagramType
    
    # Build list of available OpenRouter keys for PaperBanana
    openrouter_keys = []
    pb_key = os.getenv("PAPERBANANA_OPENROUTER_API_KEY", "")
    if pb_key:
        openrouter_keys.append(pb_key)
    primary = os.getenv("OPENROUTER_API_KEY", "")
    if primary and primary not in openrouter_keys:
        openrouter_keys.append(primary)
    for i in range(1, 10):
        backup = os.getenv(f"OPENROUTER_API_KEY_{i}", "")
        if backup and backup not in openrouter_keys:
            openrouter_keys.append(backup)
    
    if not openrouter_keys:
        raise RuntimeError("OPENROUTER_API_KEY not set for PaperBanana")
    
    dt = DiagramType.METHODOLOGY  # PaperBanana specializes in methodology diagrams
    gen_input = GenerationInput(
        source_context=source_context[:12000],
        communicative_intent=communicative_intent,
        diagram_type=dt,
    )
    
    timeout = int(os.getenv("PAPERBANANA_TIMEOUT_SECONDS", "240"))
    last_error = None
    
    # Try each key — rotate on quota exhaustion
    for ki, api_key in enumerate(openrouter_keys):
        try:
            key_label = f"key_{ki+1}" if ki > 0 else "primary"
            print(f"DEBUG: PaperBanana pipeline starting ({key_label}): {iterations} iterations, "
                  f"10 retrieval examples, 2k resolution", file=sys.stderr)
            print(f"DEBUG: Caption: {communicative_intent[:100]}...", file=sys.stderr)
            print(f"DEBUG: Source context: {len(source_context)} chars", file=sys.stderr)
            
            settings = Settings(
                vlm_provider="openrouter",
                vlm_model="google/gemma-4-31b-it:free",      # SOTA free VLM!
                image_provider="openrouter_imagen",
                image_model="google/gemini-2.5-flash-image", # Keep as best image gen
                num_retrieval_examples=10,
                refinement_iterations=iterations,
                output_resolution="2k",
                output_dir=str(out_dir),
                save_iterations=True,
                openrouter_api_key=api_key,
            )
            
            pipeline = PaperBananaPipeline(settings=settings)
            result = await asyncio.wait_for(pipeline.generate(gen_input), timeout=timeout)
            return result
            
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            is_quota = any(q in err_str for q in ["quota", "429", "resource_exhausted", "rate_limit"])
            
            if is_quota and ki < len(openrouter_keys) - 1:
                print(f"DEBUG: PaperBanana {key_label} quota exhausted, trying next key...", file=sys.stderr)
                time.sleep(3)  # Brief cooldown before trying next key
                continue
            else:
                raise  # Non-quota error or last key — propagate
    
    raise last_error  # Should not reach here


def _run_paperbanana_sync(source_context, communicative_intent, out_dir,
                           iterations=1, diagram_type="METHODOLOGY"):
    """Synchronous wrapper for PaperBanana async pipeline."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        from concurrent.futures import ThreadPoolExecutor
        def _sync():
            tl = asyncio.new_event_loop()
            asyncio.set_event_loop(tl)
            return tl.run_until_complete(
                _paperbanana_generate(source_context, communicative_intent, 
                                       out_dir, iterations, diagram_type)
            )
        with ThreadPoolExecutor() as ex:
            return ex.submit(_sync).result()
    return loop.run_until_complete(
        _paperbanana_generate(source_context, communicative_intent,
                               out_dir, iterations, diagram_type)
    )


def _extract_pb_image_path(result, out_dir):
    """Extract the generated image path from PaperBanana result."""
    if result and hasattr(result, "image_path") and result.image_path:
        p = Path(str(result.image_path))
        if p.exists():
            return p
    # Fallback: find newest PNG in output dir (PaperBanana saves there)
    pngs = sorted(Path(out_dir).rglob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True)
    if pngs:
        import time as _time
        newest = pngs[0]
        if _time.time() - newest.stat().st_mtime < 300:  # Created in last 5 min
            return newest
    return None


# ── Fast Elite Blueprint Generator via OpenRouter LLM ──
# Uses OpenRouter (cloud, ~3s) to generate a structured Elite Blueprint that
# PaperBanana's Retriever + Planner can translate into elite-quality diagrams.
# The LLM produces spatially-aware blueprints with node defs and edge routing.

from agents.llm_client import call_groq, strip_think_tags


def _llm_generate_academic_context(topic, domain, research_outputs,
                                     system_category="General / Web App",
                                     context_type="architecture"):
    """
    Generate an Elite Blueprint via Groq LLM for PaperBanana's pipeline.

    Instead of generic academic prose, this instructs Groq to produce a
    structured blueprint with:
      1. Hierarchical layout with named tiers/zones
      2. Explicit node definitions (name, role, connections)
      3. Edge routing descriptions (arrow types, labels)
      4. Academic context paragraph for Retriever matching

    Groq (~3s) vs template builder. The LLM adds domain-specific intelligence
    that templates cannot: it knows what components actually belong in a
    '{system_category}' architecture for the specific topic.
    """
    # Gather research content
    methods = []
    datasets = []
    pipeline_steps = []
    summaries = []
    for r in research_outputs:
        if "summary" in r:
            summaries.append(r["summary"][:300])
        for m in r.get("key_methods", []):
            if m not in methods:
                methods.append(m)
        for d in r.get("datasets_used", []):
            if d not in datasets:
                datasets.append(d)
        for scope in r.get("future_scope_methodologies", [])[:1]:
            pipeline_steps.extend(scope.get("pipeline_steps", [])[:5])

    total_papers = sum(len(r.get("top_papers", [])) for r in research_outputs)
    style_rules = STYLE_CONFIGS.get(system_category, STYLE_CONFIGS["General / Web App"])

    prompt = f"""Generate a BRIEF structured diagram blueprint for "{topic}" in {domain}.

System Category: {system_category}
Key methods: {', '.join(methods[:5]) if methods else 'standard methods'}

CRITICAL CONSTRAINTS:
- MAXIMUM 8 components total. No more.
- Keep ALL descriptions to ONE short sentence each.  
- Do NOT exceed 400 words total.
- You MUST complete ALL sections below. Do NOT cut off mid-sentence.
- If you are running out of space, use fewer components (minimum 5).

=== LAYOUT ===
Top-Down layered architecture. 3-4 tiers maximum. Orthogonal edges only.

Tiers:
  Tier 1: [Name] — [2 components with real tech names, brief]
  Tier 2: [Name] — [2-3 components, brief]
  Tier 3: [Name] — [2-3 components, brief]

=== NODES (max 8) ===
1. [Name] (Role: one sentence. Connects to: [target])
2. [Name] (Role: one sentence. Connects to: [target])
... (up to 8 max)

=== EDGES (max 6) ===
[Source] -> [Target] labeled "[data type]"
All edges orthogonal (90-degree turns only).

=== ACADEMIC CONTEXT ===
[One 80-word paragraph naming specific technologies used. NO visual instructions.]

REMEMBER: Complete output is mandatory. Stop at 400 words. 8 components max."""

    try:
        print(f"DEBUG: [visualizer] Generating Elite Blueprint via Groq...", file=sys.stderr)
        raw = call_groq(
            prompt=prompt,
            system_msg=(
                "You are a systems architect. Generate BRIEF diagram blueprints. "
                "Maximum 8 components. Maximum 400 words total. "
                "Use real technology names. Plain text only. No markdown."
            ),
            temperature=0.6,
            max_tokens=6000,  # Maximum runway to prevent truncation
            timeout=30,
            max_retries=2,
        )

        if not raw or len(raw) < 150:
            print(f"DEBUG: [visualizer] Groq blueprint too short ({len(raw) if raw else 0} chars), using template", file=sys.stderr)
            return None, -1

        score = min(90, 50 + len(raw) // 8)
        print(f"DEBUG: [visualizer] Elite Blueprint generated via Groq: {len(raw)} chars", file=sys.stderr)
        return raw, score

    except Exception as e:
        print(f"DEBUG: [visualizer] Groq blueprint generation failed: {e}", file=sys.stderr)
        return None, -1


def run_visualizer_agent(topic: str, domain: str, research_outputs: list,
                         system_category: str = "General / Web App") -> dict:
    """Generate all diagrams using deep PaperBanana integration.
    
    Pipeline per diagram:
      LLM Academic Context → PaperBanana 5-Agent Pipeline → Groq AI → Pillow fallback
    
    PaperBanana's 5 agents:
      Phase 1: Retriever (matches academic text to 13 curated references)
             → Planner (designs diagram from references + text)
             → Stylist (applies NeurIPS formatting)
      Phase 2: Visualizer ↔ Critic × 3 rounds (iterative refinement)
    
    Each run produces unique diagrams because:
      - LLM generates academic context with randomized writing angles
      - Communicative intents use varied caption templates
      - High temperature (0.85) ensures diverse LLM output
      - PaperBanana Retriever matches against different references per run
    """
    print(f"DEBUG: Visualizer Agent started for '{topic}' [{system_category}]...", file=sys.stderr)
    out_dir = PROJECT_ROOT / "outputs" / "visuals"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pick a UNIQUE theme for this entire run (used by Pillow fallback layers)
    theme = _pick_theme()
    print(f"DEBUG: Selected visual theme: {theme['name']}", file=sys.stderr)

    # Gather aggregate stats for communicative intents
    total_papers = sum(len(r.get("top_papers", [])) for r in research_outputs)
    all_methods = []
    for r in research_outputs:
        for m in r.get("key_methods", []):
            if m not in all_methods:
                all_methods.append(m)
    n_agents = len(research_outputs)
    all_methodologies = []
    for r in research_outputs:
        all_methodologies.extend(r.get("future_scope_methodologies", []))

    # ─── STEP 1: Academic Context Generation via Ollama (local, NO limits) ───
    llm_context = None
    autoresearch_score = -1
    try:
        llm_context, autoresearch_score = _llm_generate_academic_context(
            topic, domain, research_outputs, system_category
        )
        if llm_context:
            print(f"DEBUG: LLM context generated via Ollama: {len(llm_context)} chars, score: {autoresearch_score}", file=sys.stderr)
        else:
            print(f"DEBUG: LLM context generation returned None, using template builder", file=sys.stderr)
    except Exception as e:
        print(f"DEBUG: LLM context generation failed: {e}, using template builder", file=sys.stderr)

    # Build PaperBanana source_context: prefer LLM academic text, fall back to template
    # CRITICAL: source_context must be academic methodology text, NOT an image prompt.
    # PaperBanana has its OWN Stylist agent — do NOT inject style instructions here.
    if llm_context:
        arch_source_context = llm_context
    else:
        arch_source_context = _build_academic_source_context(
            topic.strip(), domain.strip(), research_outputs, system_category
        )

    # Build communicative intent (academic figure caption for PaperBanana Planner)
    arch_caption = _build_communicative_intent(
        topic=topic.strip(),
        diagram_type="architecture",
        index=0,
        title=f"System Architecture for {topic.strip()}",
        n_methods=len(all_methods),
        n_papers=total_papers,
        n_agents=n_agents,
        n_steps=0
    )
    print(f"DEBUG: Architecture caption: {arch_caption[:100]}...", file=sys.stderr)

    final_path = None; warning = ""; pb_ok = False; groq_ok = False; all_diagrams = {}
    pb_available = _paperbanana_available()
    if not pb_available:
        warning = "PaperBanana not installed. Falling back to Groq/Pillow."
        print("DEBUG: PaperBanana not installed, skipping PB pipeline", file=sys.stderr)

    # ─── TIER 1: PaperBanana 5-Agent Pipeline with OPENROUTER KEY ROTATION ───
    # Cycles through all available OPENROUTER_API_KEY variants before falling to Pillow.
    if pb_available:
        or_keys = []
        pb_key = os.getenv("PAPERBANANA_OPENROUTER_API_KEY")
        if pb_key and pb_key.strip():
            or_keys.append(("PAPERBANANA_OPENROUTER_API_KEY", pb_key.strip()))
        for key_name in ["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_1", "OPENROUTER_API_KEY_2", "OPENROUTER_API_KEY_3"]:
            val = os.getenv(key_name)
            if val and val.strip() and val.strip() not in [k[1] for k in or_keys]:
                or_keys.append((key_name, val.strip()))

        for key_idx, (key_name, key_val) in enumerate(or_keys):
            if pb_ok:
                break  # Already succeeded with a previous key
            try:
                # Inject the current key into the environment for PaperBanana
                os.environ["OPENROUTER_API_KEY"] = key_val
                time.sleep(3 if key_idx == 0 else 1)
                print(f"DEBUG: PaperBanana TIER 1 — trying {key_name} (key {key_idx+1}/{len(or_keys)}), "
                      f"sending {len(arch_source_context)} chars", file=sys.stderr)
                result = _run_paperbanana_sync(
                    source_context=arch_source_context,
                    communicative_intent=arch_caption,
                    out_dir=out_dir,
                    iterations=3,
                    diagram_type="METHODOLOGY"
                )
                img_path = _extract_pb_image_path(result, out_dir)
                if img_path:
                    final_path = img_path
                    pb_ok = True
                    print(f"DEBUG: PaperBanana succeeded with {key_name}: {final_path}", file=sys.stderr)
            except Exception as e:
                err = str(e)
                print(f"DEBUG: PaperBanana failed with {key_name}: {err[:150]}", file=sys.stderr)
                is_quota = any(q in err.lower() for q in ["quota", "429", "resource_exhausted", "clienterror", "retryerror", "rate_limit"])
                if is_quota:
                    print(f"DEBUG: {key_name} quota exhausted, rotating to next key...", file=sys.stderr)
                    continue  # Try next key
                else:
                    # Non-quota error — try simpler context with same key before rotating
                    try:
                        print(f"DEBUG: PaperBanana retry with template context on {key_name}...", file=sys.stderr)
                        fallback_ctx = _build_academic_source_context(
                            topic.strip(), domain.strip(), research_outputs, system_category
                        )
                        result = _run_paperbanana_sync(
                            source_context=fallback_ctx,
                            communicative_intent=arch_caption,
                            out_dir=out_dir,
                            iterations=2,
                            diagram_type="METHODOLOGY"
                        )
                        img_path = _extract_pb_image_path(result, out_dir)
                        if img_path:
                            final_path = img_path
                            pb_ok = True
                    except Exception as retry_e:
                        print(f"DEBUG: PaperBanana retry also failed on {key_name}: {retry_e}", file=sys.stderr)

        if not pb_ok:
            warning = f"All {len(or_keys)} OpenRouter key(s) exhausted." if or_keys else "No OpenRouter keys configured."

    # ─── TIER 2: Category-specific Pillow fallback (with theme) ───
    if not final_path:
        print(f"DEBUG: PaperBanana unavailable/failed, using Pillow fallback", file=sys.stderr)
        spec = _build_arch_spec(topic, domain, research_outputs, system_category=system_category)
        final_path = _render_architecture(spec, topic, domain, out_dir, theme=theme)
        warning += " Used Pillow static fallback."

    # Canonical copy
    canonical = out_dir / f"{topic.strip().replace(' ','_').lower()}_architecture.png"
    if final_path != canonical:
        shutil.copy2(final_path, canonical)
        final_path = canonical
    all_diagrams["architecture"] = str(final_path)

    # ─── Workflow diagram (second and final diagram) ───
    try:
        wf = _render_workflow(topic, domain, research_outputs, out_dir, theme=theme)
        all_diagrams["workflow"] = str(wf)
    except Exception as e:
        print(f"DEBUG: Workflow failed: {e}", file=sys.stderr)

    # ─── Summary ───
    source = ("PaperBanana AI (5-Agent Pipeline)" if pb_ok
              else "Groq AI-Designed (Peak Detailed Mode)" if groq_ok
              else f"Peak-Detailed Output ({system_category})")
    prompt_source = "LLM Academic Context" if llm_context else "Template Builder"
    print(f"DEBUG: Visualizer done! Theme: {theme['name']} | Category: {system_category} | "
          f"Source: {prompt_source} | Diagrams: {list(all_diagrams.keys())}", file=sys.stderr)

    return {
        "status": "ok",
        "image_path": str(final_path),
        "image_paths": {"png": str(final_path)},
        "all_diagrams": all_diagrams,
        "methodology_images": [],  # No per-methodology diagrams
        "warning": warning.strip(),
        "paperbanana_used": pb_ok,
        "groq_designed": groq_ok,
        "source_label": f"{source} | Theme: {theme['name']} | {prompt_source}",
        "theme_name": theme["name"],
        "description": f"{system_category} architecture for {topic}. Theme: {theme['name']}. {prompt_source}.",
        "_autoresearch_score": autoresearch_score,
        "llm_generated_prompt": arch_source_context,
    }


