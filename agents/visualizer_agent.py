"""
Visualizer Agent — PaperBanana (Gemini) primary, Pillow ByteByteGo fallback.
Generates: Architecture, Workflow, Methods diagrams + per-methodology flowcharts.
NO MERMAID. All output is PNG images.
Every generation uses a RANDOMIZED visual theme so outputs always look fresh.
"""
import os
import sys
import re
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

if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

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


ALLOWED_GROQ_MODELS = {
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "gemma2-9b-it",
}

DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"


def _resolve_groq_model(requested: str | None, default: str = DEFAULT_GROQ_MODEL) -> str:
    if requested and requested in ALLOWED_GROQ_MODELS:
        return requested
    if requested and requested not in ALLOWED_GROQ_MODELS:
        # If it's a known mapping, resolve it (e.g. from env vars that might be outdated)
        if "llama" in requested.lower() and "70b" in requested.lower(): return "llama-3.3-70b-versatile"
        if "mixtral" in requested.lower(): return "mixtral-8x7b-32768"
        if "deepseek" in requested.lower(): return "deepseek-r1-distill-llama-70b"
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
            "title": topic.title(), "subtitle": f"ML Pipeline Architecture | {domain.title()}",
            "layers": [
                {"name":"DATA INGESTION","type":"client","components":[
                    {"name":"API Connectors","sub":"REST / GraphQL","icon":"A"},
                    {"name":"Web Scrapers","sub":"Crawl4AI / Scrapy","icon":"S"},
                    {"name":"File Upload","sub":"CSV / PDF / JSON","icon":"F"},
                    {"name":"Stream Input","sub":"Kafka / Kinesis","icon":"K"}]},
                {"name":"FEATURE ENGINEERING","type":"gateway","components":[
                    {"name":"Preprocessing","sub":"Cleaning / Norm","icon":"P"},
                    {"name":"Feature Store","sub":"Feast / Tecton","icon":"F"},
                    {"name":"Embeddings","sub":m0,"icon":"E"}]},
                {"name":"TRAINING LAYER","type":"ai_ml","components":[
                    {"name":"GPU Cluster","sub":"A100 / H100","icon":"G"},
                    {"name":"Experiment Track","sub":"MLflow / W&B","icon":"X"},
                    {"name":"Model Registry","sub":"Version Control","icon":"R"},
                    {"name":"AutoML","sub":m1,"icon":"A"}]},
                {"name":"INFERENCE LAYER","type":"service","components":[
                    {"name":"Model Server","sub":"TorchServe / TFX","icon":"S"},
                    {"name":"A/B Testing","sub":"Traffic Split","icon":"T"},
                    {"name":"Auto-scaling","sub":"K8s HPA","icon":"H"}]},
                {"name":"MONITORING","type":"infra","components":[
                    {"name":"Model Drift","sub":"Evidently AI","icon":"D"},
                    {"name":"Performance","sub":"Prometheus","icon":"P"},
                    {"name":"Data Quality","sub":"Great Expectations","icon":"Q"}]},
            ],
            "connections":[{"from":0,"to":1,"label":"Raw Data"},{"from":1,"to":2,"label":"Features"},
                           {"from":2,"to":3,"label":"Model Artifact"},{"from":3,"to":4,"label":"Metrics"}],
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
#  GROQ LLM-DESIGNED ARCHITECTURE
# ═════════════════════════════════════════════════════════════════════

def _groq_design_arch(topic, domain, research_outputs, out_dir, theme=None, system_category="General / Web App"):
    from groq import Groq
    key=os.getenv("GROQ_API_KEY")
    if not key: raise RuntimeError("GROQ_API_KEY not set")
    if theme is None: theme = _pick_theme()
    model = _resolve_groq_model(os.getenv("MODEL_VISUALIZER"), DEFAULT_GROQ_MODEL)
    client=Groq(api_key=key)
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
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
    ]
    # Deduplicate while preserving order
    seen=set(); models_dedup=[]
    for mm in all_models:
        if mm not in seen: seen.add(mm); models_dedup.append(mm)
    last_raw = None
    for m in models_dedup:
        for attempt in range(2):  # Retry each model once
            try:
                print(f"DEBUG: Groq arch design attempt {attempt+1} with {m}", file=sys.stderr)
                resp=client.chat.completions.create(model=m,messages=[{"role":"user","content":prompt}],max_tokens=4000,temperature=0.4+attempt*0.2)
                raw=resp.choices[0].message.content.strip()
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
                        print(f"DEBUG: Groq arch design successful with {m}: {len(spec['layers'])} layers", file=sys.stderr)
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
                        print(f"DEBUG: Groq {m} returned invalid JSON (no layers key). Raw[:200]: {raw[:200]}", file=sys.stderr)
            except Exception as e:
                err_str = str(e)
                print(f"DEBUG: Groq {m} attempt {attempt+1} failed: {err_str[:200]}",file=sys.stderr)
                if "429" in err_str or "rate_limit" in err_str.lower():
                    import time as _time; _time.sleep(5)
                    continue
                elif "decommissioned" in err_str or "not found" in err_str.lower():
                    break  # Skip this model entirely
                break
    # Final fallback: build spec from category defaults
    print(f"DEBUG: All Groq models failed for arch design, using category fallback", file=sys.stderr)
    raise RuntimeError("All Groq models failed for architecture design")

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

# ── Academic Figure Caption Templates (communicative_intent) ──
# PaperBanana uses this as the "caption" for the generated figure.
# Specific, descriptive captions guide the Retriever and Planner better.
CAPTION_TEMPLATES = {
    "architecture": [
        "Figure 1: End-to-end system architecture of the proposed {topic} framework showing data flow from input ingestion through processing layers to output generation.",
        "Figure 1: High-level overview of the {topic} pipeline illustrating the multi-component architecture with inter-module communication protocols and data transformation stages.",
        "Figure 1: Unified system design for {topic} depicting the hierarchical arrangement of processing modules, storage layers, and decision components with labeled data paths.",
        "Figure 1: Complete architectural blueprint of the {topic} system showing the relationship between {n_methods} core methods, {n_papers} referenced techniques, and {n_agents} processing stages.",
    ],
    "methodology": [
        "Figure {idx}: Detailed methodology pipeline for {title} showing the sequential processing stages from input preparation through model training to evaluation.",
        "Figure {idx}: Overview of the proposed {title} approach illustrating the {n_steps}-stage pipeline with data transformations, model components, and feedback mechanisms.",
        "Figure {idx}: Schematic representation of the {title} framework depicting component interactions, data flow pathways, and iterative refinement loops.",
    ],
    "workflow": [
        "Figure 2: Research workflow diagram showing the multi-agent orchestration pipeline for {topic} with parallel research streams, synthesis stages, and output generation.",
        "Figure 2: Process flow for the {topic} investigation depicting data collection, analysis, synthesis, and reporting stages with quality control checkpoints.",
    ],
}


def _build_academic_source_context(topic, domain, research_outputs, system_category="General / Web App"):
    """Build source_context that reads like an ACTUAL academic methodology section.
    
    PaperBanana's Retriever was trained on academic papers — so the source_context
    should mimic the structure and language of a methodology section in a top venue paper.
    This ensures the Retriever selects the BEST matching references, which directly
    determines diagram quality (Planner can only be as good as its references).
    """
    # Extract rich research data
    methods = []
    components = []
    data_flows = []
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

    # Build component list from category + research
    style_rules = STYLE_CONFIGS.get(system_category, STYLE_CONFIGS["General / Web App"])
    
    # Karpathy style removed.
    
    category_components = style_rules["required_elements"]
    research_methods_str = ", ".join(methods[:12]) if methods else "standard processing pipeline"
    
    # Randomize architecture patterns for variety
    arch_patterns = [
        ("multi-layered pipeline", "sequential processing stages connected by data transformation interfaces"),
        ("hub-and-spoke", "central orchestration hub coordinating specialized processing modules"),  
        ("microservices mesh", "loosely coupled service modules communicating via message queues and API gateways"),
        ("hierarchical cascade", "top-down processing hierarchy with feedback loops at each level"),
        ("parallel-merge", "parallel processing branches that converge at synchronization points for aggregated output"),
        ("event-driven reactive", "event-triggered processing pipeline with pub/sub communication between components"),
    ]
    arch_name, arch_desc = random.choice(arch_patterns)
    
    # Randomize component arrangements
    component_arrangements = [
        "three-tier arrangement with separate data ingestion, processing, and output layers",
        "five-layer stack: input preprocessing, feature extraction, core computation, post-processing, and output formatting",
        "diamond topology with input fan-out to parallel processors and result fan-in to aggregator",
        "pipeline-with-bypass architecture where intermediate results can skip stages via shortcut connections",
    ]
    arrangement = random.choice(component_arrangements)
    
    # Build academic methodology text
    sections = []
    
    # Section 1: System Overview (mimics academic paper intro to methodology)
    sections.append(
        f"We present a comprehensive {arch_name} architecture for {topic} in the {domain} domain. "
        f"The proposed system employs {arch_desc}, specifically designed to handle the requirements "
        f"of {topic}. Our architecture follows a {arrangement}. "
        f"The system integrates {len(methods)} core methods including {research_methods_str}, "
        f"drawing upon insights from {len(key_papers)} recent publications in the field."
    )
    
    # Section 2: Component Description (detailed, academic style)
    sections.append(
        f"\nThe architecture comprises the following key components: {category_components}. "
        f"Each component is implemented as an independent processing module with well-defined "
        f"input/output interfaces. The system processes data through multiple transformation "
        f"stages, beginning with raw input acquisition and progressing through feature extraction, "
        f"core analysis using {methods[0] if methods else 'domain-specific algorithms'}, "
        f"and culminating in structured output generation."
    )
    
    # Section 3: Data Flow (critical for diagram quality)
    data_flow_patterns = [
        f"Data flows through the system in a directed acyclic graph (DAG) pattern. "
        f"Raw inputs enter through the ingestion layer, undergo validation and normalization, "
        f"then branch into parallel processing tracks for {methods[0] if methods else 'primary analysis'} "
        f"and {methods[1] if len(methods) > 1 else 'secondary processing'}. "
        f"Results merge at a synchronization barrier before final output assembly.",
        
        f"The processing pipeline implements a producer-consumer pattern with buffered queues "
        f"between stages. Input data is partitioned and distributed across processing nodes "
        f"implementing {methods[0] if methods else 'core algorithms'}. "
        f"Intermediate results are aggregated through a reduce phase, "
        f"with {methods[1] if len(methods) > 1 else 'post-processing'} applied to the merged output.",
        
        f"Data traverses the system through a multi-stage transformation pipeline. "
        f"The initial preprocessing stage normalizes inputs and extracts features using "
        f"{methods[0] if methods else 'feature extractors'}. "
        f"These features feed into a {methods[1] if len(methods) > 1 else 'core model'} component "
        f"that produces structured representations. A final synthesis stage combines outputs "
        f"from all processing branches into the deliverable artifacts.",
    ]
    sections.append("\n" + random.choice(data_flow_patterns))
    
    # Section 4: Method-Specific Components (from research data)
    if methods:
        method_desc_parts = []
        for i, m in enumerate(methods[:8]):
            positions = ["input preprocessing", "feature extraction", "core computation", 
                        "intermediate processing", "output generation", "quality validation",
                        "feedback control", "monitoring and logging"]
            pos = positions[i % len(positions)]
            method_desc_parts.append(f"{m} (deployed at the {pos} stage)")
        sections.append(
            f"\nThe technical stack incorporates: {'; '.join(method_desc_parts)}. "
            f"These methods are interconnected through typed data interfaces that ensure "
            f"compatibility across pipeline stages while maintaining processing isolation."
        )
    
    # Section 5: Methodology Pipelines (from research scopes)
    if methodologies:
        for midx, meth in enumerate(methodologies[:3]):
            steps_str = " → ".join(meth["steps"][:6]) if meth["steps"] else ""
            sections.append(
                f"\nMethodology {midx+1} — {meth['title']}: {meth['methodology'][:300]}"
                + (f"\nPipeline: {steps_str}" if steps_str else "")
            )
    
    # Section 6: Domain context
    if datasets:
        sections.append(
            f"\nThe system is evaluated on datasets including: {', '.join(datasets[:5])}. "
            f"Performance metrics are tracked across all pipeline stages with automated "
            f"quality gates at each processing boundary."
        )
    
    return "\n".join(sections)


def _build_methodology_source_context(scope_item, topic, domain, all_methods):
    """Build source_context for a SPECIFIC methodology / future scope.
    
    This generates academic-style text describing one research methodology,
    optimized for PaperBanana's Retriever to find the best matching reference
    diagrams for this specific type of pipeline.
    """
    title = scope_item.get("scope_title", "Proposed Methodology")
    methodology = scope_item.get("proposed_methodology", "")
    steps = scope_item.get("pipeline_steps", [])
    problem = scope_item.get("problem_statement", "")
    
    # Randomize pipeline descriptions for variety
    pipeline_styles = [
        "sequential multi-stage pipeline with checkpoint validation at each transition",
        "iterative refinement loop with early stopping based on convergence criteria",
        "branch-and-merge topology with parallel experimental tracks",
        "cascade architecture with progressive refinement at each level",
        "feedback-driven pipeline with a critic loop evaluating each stage's output",
    ]
    pipe_style = random.choice(pipeline_styles)
    
    sections = []
    
    # Academic methodology section
    sections.append(
        f"We propose {title} — a novel approach to address challenges in {topic} ({domain}). "
        f"{'The core problem: ' + problem[:200] + '. ' if problem else ''}"
        f"Our methodology implements a {pipe_style}."
    )
    
    # Pipeline description
    if steps:
        sections.append(f"\nThe proposed pipeline consists of {len(steps)} stages:")
        for i, step in enumerate(steps[:8]):
            stage_names = ["Input Processing", "Feature Engineering", "Core Computation",
                          "Model Training", "Optimization", "Evaluation", "Deployment", "Monitoring"]
            stage = stage_names[i % len(stage_names)]
            sections.append(f"  Stage {i+1} ({stage}): {step}")
        sections.append(
            f"\nData flows sequentially through these stages: "
            f"{' → '.join(steps[:8])}. "
            f"Each stage produces typed intermediate outputs consumed by the next stage."
        )
    
    # Methodology detail
    if methodology:
        sections.append(f"\nDetailed approach: {methodology[:800]}")
    
    # Connect to broader research
    if all_methods:
        relevant = random.sample(all_methods, min(5, len(all_methods)))
        sections.append(
            f"\nThis methodology builds upon established techniques including: "
            f"{', '.join(relevant)}. "
            f"The integration of these methods creates a unified framework that "
            f"addresses limitations identified in prior work."
        )
    
    return "\n".join(sections)


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
    """
    from paperbanana import PaperBananaPipeline
    from paperbanana.core.config import Settings
    from paperbanana.core.types import GenerationInput, DiagramType
    
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY not set")
    
    # Optimal settings for maximum quality
    settings = Settings(
        vlm_provider="gemini",
        vlm_model="gemini-2.0-flash",
        image_provider="google_imagen",
        image_model="gemini-3-pro-image-preview",
        num_retrieval_examples=10,          # Max reference coverage for Retriever
        refinement_iterations=iterations,    # 3 Visualizer-Critic rounds (paper default)
        output_resolution="2k",             # High-resolution output
        output_dir=str(out_dir),
        save_iterations=True,               # Keep intermediate outputs for debugging
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )
    
    dt = DiagramType.METHODOLOGY  # PaperBanana specializes in methodology diagrams
    
    gen_input = GenerationInput(
        source_context=source_context[:12000],   # PaperBanana handles long contexts well
        communicative_intent=communicative_intent,
        diagram_type=dt,
    )
    
    pipeline = PaperBananaPipeline(settings=settings)
    timeout = int(os.getenv("PAPERBANANA_TIMEOUT_SECONDS", "240"))  # 4 min for 3 iterations
    
    print(f"DEBUG: PaperBanana pipeline starting: {iterations} iterations, "
          f"10 retrieval examples, 2k resolution", file=sys.stderr)
    print(f"DEBUG: Caption: {communicative_intent[:100]}...", file=sys.stderr)
    print(f"DEBUG: Source context: {len(source_context)} chars", file=sys.stderr)
    
    result = await asyncio.wait_for(pipeline.generate(gen_input), timeout=timeout)
    return result


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


# ── Fast Academic Context Generator for PaperBanana Source Context ──
# Uses Groq (cloud) for speed — a 250-word context takes ~2 seconds vs ~90s on Ollama.
# PaperBanana's Retriever does NOT need an essay; it needs dense technical keywords.

from agents.llm_client import call_groq, strip_think_tags


def _llm_generate_academic_context(topic, domain, research_outputs,
                                     system_category="General / Web App",
                                     context_type="architecture"):
    """
    Generate rich academic methodology text for PaperBanana's Retriever.

    Fast Groq-powered academic methodology text for PaperBanana's Retriever.

    Groq (~2s) vs Ollama 8B (~90s). PaperBanana doesn't need 900 words —
    it needs dense technical keywords and component names so the Retriever
    can match the right reference diagrams. 250 focused words beat 900 generic ones.
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

    prompt = f"""Write a 200-300 word academic methodology paragraph describing the system architecture for a research paper on "{topic}" in {domain}.

Key components to include: {style_rules['required_elements']}
Key methods from research: {', '.join(methods[:10])}
Datasets: {', '.join(datasets[:4]) if datasets else 'standard benchmarks'}
Pipeline stages: {' → '.join(pipeline_steps[:5]) if pipeline_steps else 'Input → Processing → Output'}
Research context: {summaries[0][:200] if summaries else ''}

Rules: Name SPECIFIC components (e.g. "8-head Cross-Attention", "Redis Cache"). Describe data flow between modules. NO visual instructions. Academic prose only. 200-300 words maximum."""

    try:
        print(f"DEBUG: [visualizer] Generating PaperBanana context via Groq (fast)...", file=sys.stderr)
        raw = call_groq(
            prompt=prompt,
            system_msg="You are a senior AI researcher. Write dense, technical academic prose. 200-300 words only. No markdown.",
            temperature=0.5,
            max_tokens=512,
            timeout=30,
            max_retries=2,
        )

        if not raw or len(raw) < 100:
            print(f"DEBUG: [visualizer] Groq context too short, using template", file=sys.stderr)
            return None, -1

        score = min(85, 40 + len(raw) // 10)
        print(f"DEBUG: [visualizer] Context generated via Groq: {len(raw)} chars in ~2s", file=sys.stderr)
        return raw, score

    except Exception as e:
        print(f"DEBUG: [visualizer] Groq context generation failed: {e}", file=sys.stderr)
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

    # ─── TIER 1: PaperBanana 5-Agent Pipeline ───
    # Feeds academic methodology text to Retriever → Planner → Stylist → Visualizer ↔ Critic
    if pb_available:
        try:
            print(f"DEBUG: PaperBanana TIER 1: Sending {len(arch_source_context)} chars academic text + caption", file=sys.stderr)
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
                print(f"DEBUG: PaperBanana succeeded: {final_path}", file=sys.stderr)
        except Exception as e:
            err = str(e)
            print(f"DEBUG: PaperBanana failed: {err}", file=sys.stderr)
            is_quota = any(q in err.lower() for q in ["quota", "429", "resource_exhausted", "clienterror", "retryerror", "rate_limit"])
            
            if not is_quota:
                # Retry with simplified academic context (template-generated)
                try:
                    print(f"DEBUG: PaperBanana retry with template context...", file=sys.stderr)
                    fallback_ctx = _build_academic_source_context(
                        topic.strip(), domain.strip(), research_outputs, system_category
                    )
                    result = _run_paperbanana_sync(
                        source_context=fallback_ctx,
                        communicative_intent=arch_caption,
                        out_dir=out_dir,
                        iterations=2,  # Fewer iterations for retry
                        diagram_type="METHODOLOGY"
                    )
                    img_path = _extract_pb_image_path(result, out_dir)
                    if img_path:
                        final_path = img_path
                        pb_ok = True
                except Exception as retry_e:
                    print(f"DEBUG: PaperBanana retry also failed: {retry_e}", file=sys.stderr)
            
            if not pb_ok:
                warning = "Gemini quota exhausted." if is_quota else f"PaperBanana failed: {err[:80]}"

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

    # ─── Additional diagrams (using same theme for visual consistency) ───
    try:
        wf = _render_workflow(topic, domain, research_outputs, out_dir, theme=theme)
        all_diagrams["workflow"] = str(wf)
    except Exception as e:
        print(f"DEBUG: Workflow failed: {e}", file=sys.stderr)
    try:
        md = _render_methods(topic, domain, research_outputs, out_dir, theme=theme)
        all_diagrams["methods"] = str(md)
    except Exception as e:
        print(f"DEBUG: Methods failed: {e}", file=sys.stderr)

    # ─── Methodology flowcharts with PaperBanana integration ───
    # For each proposed methodology, try PaperBanana first (unique academic diagrams),
    # then fall back to the 6 Pillow layout types.
    methodology_images = []
    for r in research_outputs:
        for idx, m in enumerate(r.get("future_scope_methodologies", [])):
            title = m.get("scope_title", f"Methodology {idx+1}")
            text = m.get("proposed_methodology", "")
            if not text or len(text) < 30:
                continue
            
            p_steps = m.get("pipeline_steps", [])
            meth_path = None
            
            # Try PaperBanana for this methodology (only if PB available and quota isn't exhausted)
            if pb_available and (pb_ok or "quota" not in warning.lower()):
                try:
                    meth_context = _build_methodology_source_context(
                        scope_item=m,
                        topic=topic.strip(),
                        domain=domain.strip(),
                        all_methods=all_methods
                    )
                    meth_caption = _build_communicative_intent(
                        topic=topic.strip(),
                        diagram_type="methodology",
                        index=idx,
                        title=title,
                        n_methods=len(all_methods),
                        n_papers=total_papers,
                        n_agents=n_agents,
                        n_steps=len(p_steps)
                    )
                    meth_result = _run_paperbanana_sync(
                        source_context=meth_context,
                        communicative_intent=meth_caption,
                        out_dir=out_dir,
                        iterations=2,  # 2 iterations per methodology (faster)
                        diagram_type="METHODOLOGY"
                    )
                    meth_path_pb = _extract_pb_image_path(meth_result, out_dir)
                    if meth_path_pb:
                        # Copy to canonical name
                        safe_title = re.sub(r'[^a-zA-Z0-9]', '_', title.lower())[:50]
                        canon_meth = out_dir / f"methodology_{idx}_{safe_title}.png"
                        shutil.copy2(meth_path_pb, canon_meth)
                        meth_path = str(canon_meth)
                        print(f"DEBUG: PaperBanana methodology '{title}' succeeded", file=sys.stderr)
                except Exception as me:
                    print(f"DEBUG: PaperBanana methodology '{title}' failed: {me}", file=sys.stderr)

            # Fall back to Pillow methodology layouts (6 types)
            if not meth_path:
                try:
                    img_path = render_methodology_flowchart(title, text, out_dir, idx,
                                                           pipeline_steps=p_steps, theme=theme)
                    meth_path = img_path
                except Exception as e:
                    # Guard against geometry errors (y1<y0) by producing a minimal placeholder
                    print(f"DEBUG: Methodology flowchart '{title}' failed: {e}", file=sys.stderr)
                    try:
                        from PIL import Image, ImageDraw
                        ph = Image.new("RGB", (1200, 800), "white")
                        d = ImageDraw.Draw(ph)
                        d.text((40, 40), f"Methodology: {title}\n(Fallback placeholder)", fill="black")
                        ph_path = out_dir / f"methodology_placeholder_{idx}.png"
                        ph.save(ph_path, "PNG")
                        meth_path = str(ph_path)
                    except Exception as e2:
                        print(f"DEBUG: Placeholder generation failed: {e2}", file=sys.stderr)
            
            if meth_path:
                methodology_images.append({"title": title, "path": meth_path})
                all_diagrams[f"methodology_{idx}"] = meth_path

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
        "methodology_images": methodology_images,
        "warning": warning.strip(),
        "paperbanana_used": pb_ok,
        "groq_designed": groq_ok,
        "source_label": f"{source} | Theme: {theme['name']} | {prompt_source}",
        "theme_name": theme["name"],
        "description": f"{system_category} architecture for {topic}. Theme: {theme['name']}. {prompt_source}.",
        "_autoresearch_score": autoresearch_score,
        "llm_generated_prompt": arch_source_context,
    }


