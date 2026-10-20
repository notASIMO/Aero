import os
import sys
import json
from google import genai
from google.genai import types

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "company_memory.json")
WAKE_WORDS = ["aero", "arrow", "asimo", "hey aero", "ok aero", "jarvis"]
WAKE_HOTKEY = "shift+alt+space"
ACTIVE_WINDOW_SECONDS = 25
CREATE_NO_WINDOW = 0x08000000

def load_api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    env_file = os.path.join(BASE_DIR, ".env")
    if not key and os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f: key = f.read().strip()
    return key

GEMINI_API_KEY = load_api_key()
if not GEMINI_API_KEY: sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

def discover_models():
    available = []
    try:
        for m in client.models.list(): available.append(m.name.replace("models/", ""))
    except Exception: pass
    flash = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash", "gemini-1.5-flash-latest"]
    pro = ["gemini-2.5-pro", "gemini-pro-latest", "gemini-2.0-pro-exp"]
    return [m for m in flash if m in available] or flash, [m for m in pro if m in available] or pro

FLASH_MODELS, PRO_MODELS = discover_models()

def call_gemini(prompt: str, system_instruction: str = "", use_pro: bool = False, json_mode: bool = False, image_pil=None) -> str:
    pool = (PRO_MODELS + FLASH_MODELS) if use_pro else (FLASH_MODELS + PRO_MODELS)
    contents = [image_pil, prompt] if image_pil else prompt
    cfg = types.GenerateContentConfig()
    if system_instruction: cfg.system_instruction = system_instruction
    if json_mode: cfg.response_mime_type = "application/json"
    for m in pool:
        try:
            resp = client.models.generate_content(model=m, contents=contents, config=cfg)
            if resp and resp.text: return resp.text.strip()
        except Exception: continue
    return "{}" if json_mode else "Busy."
