import os
import sys
import time
import json
import asyncio
import threading
import subprocess
import webbrowser
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import uvicorn

import pyaudio
import keyboard
import pyautogui
import pyperclip
import pygetwindow as gw
import speech_recognition as sr
import edge_tts
import pygame
from PIL import Image
import mss

from google import genai
from google.genai import types

pyautogui.FAILSAFE = False
CREATE_NO_WINDOW = 0x08000000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
MEMORY_FILE = os.path.join(BASE_DIR, "company_memory.json")
WAKE_WORDS = ["aero", "arrow", "asimo", "hey aero", "ok aero", "jarvis"]
WAKE_HOTKEY = "shift+alt+space"
ACTIVE_WINDOW_SECONDS = 25
DANGEROUS_KEYWORDS = ["rm -rf", "del /s", "remove-item -recurse", "format ", "git push --force", "shutdown"]

def load_api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    env_file = os.path.join(BASE_DIR, ".env")
    if not key and os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f: key = f.read().strip()
    return key

GEMINI_API_KEY = load_api_key()
if not GEMINI_API_KEY: sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)
recognizer = sr.Recognizer()
pygame.mixer.init()

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

# Global State for Web UI
app_state = {
    "agents": {
        "AERO": {"status": "ONLINE", "task": "Awaiting directive", "color": "#00E5FF"},
        "ATLAS": {"status": "IDLE", "task": "CTO (Deep Thinking)", "color": "#D500F9"},
        "NOVA": {"status": "IDLE", "task": "VP Eng (VS Code/Files)", "color": "#00E676"},
        "SENTINEL": {"status": "IDLE", "task": "QA & SecOps", "color": "#FFB300"},
        "PULSE": {"status": "IDLE", "task": "Research & Vision", "color": "#FF6D00"},
        "VIBE": {"status": "IDLE", "task": "OS & Spotify Ops", "color": "#1DB954"}
    },
    "logs": ["[00:00:00] [AERO] Glassmorphism War Room Online."],
    "pending_command": None
}

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get_war_room(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/state")
async def get_state():
    return app_state

@app.post("/deploy")
async def deploy(request: Request):
    data = await request.json()
    cmd = data.get("command")
    if cmd:
        app_state["pending_command"] = cmd
    return {"status": "queued"}

def start_server():
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")

# Background thread for web server & browser overlay
threading.Thread(target=start_server, daemon=True).start()
time.sleep(1.0)
webbrowser.open("http://127.0.0.1:8765")

# Agent logic helpers
def log_bus(agent, text):
    ts = datetime.now().strftime("%H:%M:%S")
    app_state["logs"].append(f"[{ts}] [{agent}] {text}")
    if len(app_state["logs"]) > 50: app_state["logs"].pop(0)

def set_agent(agent, status, task, color="#00E5FF"):
    if agent in app_state["agents"]:
        app_state["agents"][agent] = {"status": status, "task": task, "color": color}

def run_atlas(task, ctx=""):
    set_agent("ATLAS", "THINKING", task, "#D500F9")
    log_bus("ATLAS", f"Analyzing: {task}")
    res = call_gemini(f"Context:\n{ctx}\n\nTask:\n{task}", system_instruction="You are ATLAS, CTO. Provide crisp architecture/code.", use_pro=True)
    set_agent("ATLAS", "DONE", "Ready", "#00E676")
    return res

def run_nova(action, task_prompt, target_path=""):
    set_agent("NOVA", "CODING", task_prompt, "#00E676")
    log_bus("NOVA", f"{action} -> {task_prompt}")
    if action == "write_file" and target_path:
        fp = os.path.expanduser(target_path)
        os.makedirs(os.path.dirname(os.path.abspath(fp)), exist_ok=True)
        code = call_gemini(f"Write raw production code for '{target_path}'. Task: {task_prompt}", use_pro=True)
        code = code.removeprefix("```python").removeprefix("```").removesuffix("```").strip()
        with open(fp, "w", encoding="utf-8") as f: f.write(code)
        return f"Wrote {fp}"
    subprocess.Popen("code .", shell=True, creationflags=CREATE_NO_WINDOW)
    time.sleep(1.5)
    pyperclip.copy(task_prompt)
    pyautogui.hotkey("ctrl", "shift", "i")
    time.sleep(0.4)
    pyautogui.hotkey("ctrl", "v")
    pyautogui.press("enter")
    return "Dispatched to VS Code"

def run_sentinel(command):
    set_agent("SENTINEL", "AUDITING", command, "#FFB300")
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=35, creationflags=CREATE_NO_WINDOW)
        out = (res.stdout + "\n" + res.stderr).strip()[:1500]
        set_agent("SENTINEL", "DONE", "Audited", "#00E676")
        return out
    except Exception as e:
        return f"Error: {e}"

def run_pulse(action, query):
    set_agent("PULSE", "ACTIVE", query, "#FF6D00")
    webbrowser.open(f"[https://www.google.com/search?q=](https://www.google.com/search?q=){query.replace(' ', '+')}")
    return f"Searched Google for {query}"

def run_vibe(action, val=""):
    set_agent("VIBE", "OPS", action, "#1DB954")
    if action == "spotify":
        subprocess.Popen("start spotify:", shell=True, creationflags=CREATE_NO_WINDOW)
        return "Opened Spotify"
    return f"OS Action: {action}"

async def speak(text):
    if not text: return
    clean = text.replace("*", "").replace("#", "").replace("`", "").strip()
    log_bus("AERO", clean)
    set_agent("AERO", "SPEAKING", clean[:30], "#D500F9")
    out_file = os.path.join(BASE_DIR, "tts.mp3")
    comm = edge_tts.Communicate(clean, "en-US-ChristopherNeural", rate="+28%")
    await comm.save(out_file)
    pygame.mixer.music.load(out_file)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        if keyboard.is_pressed("space") or keyboard.is_pressed(WAKE_HOTKEY):
            pygame.mixer.music.stop()
            break
        await asyncio.sleep(0.03)
    pygame.mixer.music.unload()
    set_agent("AERO", "ONLINE", "Ready", "#00E5FF")
    try: os.remove(out_file)
    except: pass

async def orchestrate(prompt):
    set_agent("AERO", "PLANNING", prompt[:30], "#00E5FF")
    log_bus("DEVANG", prompt)
    ceo_prompt = "You are AERO, CEO. Return JSON: {\"parallel_wave\": [{\"agent\": \"ATLAS\"|\"NOVA\"|\"SENTINEL\"|\"PULSE\"|\"VIBE\", \"action\": \"...\", \"task\": \"...\", \"target\": \"\"}], \"final_spoken_reply\": \"...\"}"
    raw = call_gemini(f"Directive: {prompt}", system_instruction=ceo_prompt, json_mode=True)
    try: plan = json.loads(raw.removeprefix("```json").removesuffix("```").strip())
    except: plan = {"parallel_wave": [], "final_spoken_reply": "Right away, sir."}

    for step in (plan.get("parallel_wave") or []):
        ag = step.get("agent", "AERO").upper()
        act = step.get("action", "")
        tsk = step.get("task", "")
        tgt = step.get("target", "")
        if ag == "ATLAS": await asyncio.to_thread(run_atlas, tsk)
        elif ag == "NOVA": await asyncio.to_thread(run_nova, act, tsk, tgt)
        elif ag == "SENTINEL": await asyncio.to_thread(run_sentinel, tsk)
        elif ag == "PULSE": await asyncio.to_thread(run_pulse, act, tsk)
        elif ag == "VIBE": await asyncio.to_thread(run_vibe, act, tsk)

    return plan.get("final_spoken_reply", "Mission accomplished.")

def listen_mic():
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.2)
        try:
            audio = recognizer.listen(source, timeout=3, phrase_limit=12)
            return recognizer.recognize_google(audio).lower()
        except: return None

async def main():
    hotkey_triggered = False
    keyboard.add_hotkey(WAKE_HOTKEY, lambda: globals().update({'hotkey_triggered': True}))
    log_bus("AERO", f"Daemon active. Press {WAKE_HOTKEY.upper()} or use War Room web UI.")

    while True:
        await asyncio.sleep(0.05)
        if app_state["pending_command"]:
            cmd = app_state["pending_command"]
            app_state["pending_command"] = None
            rep = await orchestrate(cmd)
            await speak(rep)
            continue

        if hotkey_triggered:
            hotkey_triggered = False
            await speak("Aero live online. Go ahead, sir.")
            heard = await asyncio.to_thread(listen_mic)
            if heard:
                rep = await orchestrate(heard)
                await speak(rep)

if __name__ == "__main__":
    asyncio.run(main())
