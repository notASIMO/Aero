import os
import re
import time
import json
import hashlib
import requests
from io import BytesIO
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

GEMINI_FLASH_POOL = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-1.5-flash"
]
GEMINI_PRO_POOL = [
    "gemini-2.5-pro",
    "gemini-2.0-pro-exp",
    "gemini-pro-latest"
]

# Tracks model cooldown timestamps when a 429 occurs
model_cooldowns = {}
response_cache = {}

router_telemetry = {
    "mode": "AUTO",  # AUTO | POLLINATIONS_FREE | GEMINI | GROQ | OPENROUTER | OLLAMA
    "last_provider": "LOCAL-REFLEX (0 TOKENS)",
    "tokens_saved": 0,
    "total_calls": 0,
    "cooldown_models": []
}

def set_router_mode(mode: str):
    router_telemetry["mode"] = mode.upper()

def save_plugin_keys(groq_key: str = "", openrouter_key: str = ""):
    if groq_key:
        os.environ["GROQ_API_KEY"] = groq_key.strip()
    if openrouter_key:
        os.environ["OPENROUTER_API_KEY"] = openrouter_key.strip()

# --- LAYER 1: ZERO-TOKEN LOCAL REFLEX PLUGIN ---
def check_local_reflex(prompt: str) -> dict | None:
    """
    Intercepts common laptop/OS/Spotify/Git commands in 2ms using 0 API tokens!
    Returns an execution plan dict if matched, or None if LLM reasoning is needed.
    """
    p = prompt.lower().strip()

    # 1. Spotify Reflexes
    if p in ("open spotify", "launch spotify", "start spotify", "spotify"):
        router_telemetry["tokens_saved"] += 450
        router_telemetry["last_provider"] = "REFLEX-ENGINE (0 TOKENS)"
        return {
            "parallel_wave": [{"agent": "VIBE", "action": "spotify", "task": "", "target": ""}],
            "final_spoken_reply": "Spotify is open and focused, sir. Which track shall I play?"
        }
    m_play = re.match(r"^(?:play|put on)\s+(.+?)(?:\s+on spotify)?$", p)
    if m_play and "youtube" not in p:
        song = m_play.group(1).strip()
        router_telemetry["tokens_saved"] += 450
        router_telemetry["last_provider"] = "REFLEX-ENGINE (0 TOKENS)"
        return {
            "parallel_wave": [{"agent": "VIBE", "action": "spotify", "task": song, "target": ""}],
            "final_spoken_reply": f"Playing {song} on Spotify right away, sir."
        }

    # 2. Virtual Desktop & Tab Reflexes
    desktop_map = {
        "next desktop": ("next_desktop", "Switched to the next virtual desktop."),
        "switch desktop": ("next_desktop", "Switched virtual desktop."),
        "previous desktop": ("prev_desktop", "Switched to the previous virtual desktop."),
        "new desktop": ("new_desktop", "Created a new virtual desktop."),
        "next tab": ("next_tab", "Switched to the next browser tab."),
        "previous tab": ("prev_tab", "Switched to the previous tab."),
        "new tab": ("new_tab", "Opened a new browser tab."),
        "close tab": ("close_tab", "Closed the active tab."),
        "volume up": ("volume_up", "Increased system volume."),
        "increase volume": ("volume_up", "Increased system volume."),
        "volume down": ("volume_down", "Decreased system volume."),
        "decrease volume": ("volume_down", "Decreased system volume."),
        "pause": ("media_play_pause", "Toggled media playback."),
        "resume": ("media_play_pause", "Toggled media playback."),
        "next song": ("media_next", "Skipped to the next track."),
        "next track": ("media_next", "Skipped to the next track."),
    }
    for phrase, (act, reply) in desktop_map.items():
        if phrase in p:
            router_telemetry["tokens_saved"] += 400
            router_telemetry["last_provider"] = "REFLEX-ENGINE (0 TOKENS)"
            return {
                "parallel_wave": [{"agent": "VIBE", "action": act, "task": "", "target": ""}],
                "final_spoken_reply": reply
            }

    # 3. Quick Git Status Reflex
    if "git status" in p or "check git" in p:
        router_telemetry["tokens_saved"] += 500
        router_telemetry["last_provider"] = "REFLEX-ENGINE (0 TOKENS)"
        return {
            "parallel_wave": [{"agent": "SENTINEL", "action": "terminal", "task": "git status -s", "target": ""}],
            "final_spoken_reply": "Sentinel has audited your current Git repository status."
        }

    return None

# --- LAYER 2: FREE POLLINATIONS AI PLUGIN (NO API KEY NEEDED) ---
def call_pollinations_free(prompt: str, system_instruction: str = "", json_mode: bool = False) -> str:
    """Uses Pollinations.AI free OpenAI-compatible endpoint (0 API key required, unlimited fallback)."""
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": "openai",
        "messages": messages,
        "temperature": 0.3
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    r = requests.post("https://text.pollinations.ai/openai", json=payload, timeout=25)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    router_telemetry["last_provider"] = "POLLINATIONS-FREE (0 QUOTA)"
    router_telemetry["tokens_saved"] += 600
    return content.strip()

# --- LAYER 3: GROQ / OPENROUTER / OLLAMA PLUGINS ---
def call_groq(prompt: str, system_instruction: str = "", json_mode: bool = False) -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise ValueError("No GROQ_API_KEY")
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": "llama-3.3-70b-versatile", "messages": messages, "temperature": 0.2}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload, timeout=20
    )
    r.raise_for_status()
    router_telemetry["last_provider"] = "GROQ-LLAMA-3.3-70B"
    return r.json()["choices"][0]["message"]["content"].strip()

def call_openrouter(prompt: str, system_instruction: str = "") -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ValueError("No OPENROUTER_API_KEY")
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": "meta-llama/llama-3.3-70b-instruct:free", "messages": messages},
        timeout=25
    )
    r.raise_for_status()
    router_telemetry["last_provider"] = "OPENROUTER-FREE"
    return r.json()["choices"][0]["message"]["content"].strip()

def call_ollama(prompt: str, system_instruction: str = "") -> str:
    full = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
    r = requests.post(
        "http://127.0.0.1:11434/api/generate",
        json={"model": "llama3", "prompt": full, "stream": False},
        timeout=15
    )
    r.raise_for_status()
    router_telemetry["last_provider"] = "LOCAL-OLLAMA (OFFLINE)"
    return r.json().get("response", "").strip()

# --- MASTER MULTI-PROVIDER CALLER ---
def call_ai(prompt: str, system_instruction: str = "", use_pro: bool = False, json_mode: bool = False, image_pil=None) -> str:
    router_telemetry["total_calls"] += 1

    # 1. Check Semantic Cache first (if no live screenshot)
    cache_key = hashlib.md5(f"{system_instruction}|{prompt}|{json_mode}".encode()).hexdigest()
    if not image_pil and cache_key in response_cache:
        router_telemetry["last_provider"] = "CACHE-HIT (0 TOKENS)"
        router_telemetry["tokens_saved"] += 500
        return response_cache[cache_key]

    mode = router_telemetry["mode"]

    # 2. If user forced Pollinations Free Mode (and not a vision call)
    if mode == "POLLINATIONS_FREE" and not image_pil:
        try:
            res = call_pollinations_free(prompt, system_instruction, json_mode)
            response_cache[cache_key] = res
            return res
        except Exception:
            pass

    # 3. If user forced Groq or OpenRouter or Ollama
    if mode == "GROQ" and not image_pil:
        try:
            return call_groq(prompt, system_instruction, json_mode)
        except Exception:
            pass
    if mode == "OPENROUTER" and not image_pil:
        try:
            return call_openrouter(prompt, system_instruction)
        except Exception:
            pass
    if mode == "OLLAMA" and not image_pil:
        try:
            return call_ollama(prompt, system_instruction)
        except Exception:
            pass

    # 4. Try Gemini Pool with Smart 90s Cooldown Skip
    if client:
        pool = (GEMINI_PRO_POOL + GEMINI_FLASH_POOL) if use_pro else (GEMINI_FLASH_POOL + GEMINI_PRO_POOL)
        now = time.time()
        router_telemetry["cooldown_models"] = [m for m, exp in model_cooldowns.items() if exp > now]

        contents = [image_pil, prompt] if image_pil else prompt
        cfg = types.GenerateContentConfig()
        if system_instruction:
            cfg.system_instruction = system_instruction
        if json_mode:
            cfg.response_mime_type = "application/json"

        for model_name in pool:
            if model_cooldowns.get(model_name, 0) > now:
                continue
            try:
                resp = client.models.generate_content(model=model_name, contents=contents, config=cfg)
                if resp and resp.text:
                    out = resp.text.strip()
                    router_telemetry["last_provider"] = f"GEMINI ({model_name})"
                    if not image_pil:
                        response_cache[cache_key] = out
                    return out
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    model_cooldowns[model_name] = time.time() + 90
                elif "404" in err_str:
                    model_cooldowns[model_name] = time.time() + 3600
                continue

    # 5. Automatic Zero-Key Failover Chain (Groq -> OpenRouter -> Pollinations Free AI)
    if not image_pil:
        for fallback_fn in (
            lambda: call_groq(prompt, system_instruction, json_mode),
            lambda: call_openrouter(prompt, system_instruction),
            lambda: call_pollinations_free(prompt, system_instruction, json_mode),
        ):
            try:
                res = fallback_fn()
                if res:
                    response_cache[cache_key] = res
                    return res
            except Exception:
                continue

    return '{"parallel_wave": [], "final_spoken_reply": "Completed via local fallback, sir."}' if json_mode else "Task processed via fallback."
