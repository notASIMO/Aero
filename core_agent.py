import os
import sys
import time
import json
import queue
import ctypes
import asyncio
import warnings
import threading
import subprocess
import webbrowser
from datetime import datetime

warnings.filterwarnings("ignore")

# Ensure windowless pythonw.exe never crashes on stdout/stderr writes
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
LOG_PATH = os.path.join(BASE_DIR, "aero_runtime.log")
log_stream = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
if sys.stdout is None or "pythonw" in sys.executable.lower():
    sys.stdout = log_stream
if sys.stderr is None or "pythonw" in sys.executable.lower():
    sys.stderr = log_stream

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
import tkinter as tk

from google import genai
from google.genai import types

pyautogui.FAILSAFE = False
CREATE_NO_WINDOW = 0x08000000

# ==========================================
# 0. CONFIGURATION & PERMANENT KEY LOADER
# ==========================================
def load_api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    env_file = os.path.join(BASE_DIR, ".env")
    if not key and os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            key = f.read().strip()
    return key

GEMINI_API_KEY = load_api_key()
if not GEMINI_API_KEY:
    sys.exit(1)

WAKE_WORDS = ["aero", "arrow", "asimo", "hey aero", "ok aero", "jarvis"]
WAKE_HOTKEY = "shift+alt+space"
ACTIVE_WINDOW_SECONDS = 25
MEMORY_FILE = os.path.join(BASE_DIR, "company_memory.json")
DANGEROUS_KEYWORDS = ["rm -rf", "del /s", "remove-item -recurse", "format ", "git push --force", "shutdown"]

client = genai.Client(api_key=GEMINI_API_KEY)
recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True
pygame.mixer.init()

def discover_models():
    available = []
    try:
        for m in client.models.list():
            available.append(m.name.replace("models/", ""))
    except Exception:
        pass

    flash_candidates = [
        "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash",
        "gemini-2.0-flash-lite", "gemini-1.5-flash-latest"
    ]
    pro_candidates = [
        "gemini-2.5-pro", "gemini-pro-latest", "gemini-2.0-pro-exp"
    ]
    flash_pool = [m for m in flash_candidates if m in available] or flash_candidates
    pro_pool = [m for m in pro_candidates if m in available] or pro_candidates
    return flash_pool, pro_pool

FLASH_MODELS, PRO_MODELS = discover_models()

def call_gemini(prompt: str, system_instruction: str = "", use_pro: bool = False, json_mode: bool = False, image_pil=None) -> str:
    pool = (PRO_MODELS + FLASH_MODELS) if use_pro else (FLASH_MODELS + PRO_MODELS)
    contents = [image_pil, prompt] if image_pil else prompt

    cfg = types.GenerateContentConfig()
    if system_instruction:
        cfg.system_instruction = system_instruction
    if json_mode:
        cfg.response_mime_type = "application/json"

    for model_name in pool:
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=cfg
            )
            if resp and resp.text:
                return resp.text.strip()
        except Exception as e:
            print(f"⚠️ [{model_name}] failover: {str(e)[:80]}")
            continue
    return "{}" if json_mode else "All model endpoints are temporarily busy."

# ==========================================
# 1. GEMINI-LIVE FLOATING BUTTON, HUD & WAR ROOM
# ==========================================
AGENTS_META = {
    "AERO":     {"role": "CEO & Orchestrator",     "color": "#00E5FF"},
    "ATLAS":    {"role": "CTO (Deep Thinking)",    "color": "#D500F9"},
    "NOVA":     {"role": "VP Eng (VS Code/Files)", "color": "#00E676"},
    "SENTINEL": {"role": "QA & SecOps (Terminal)", "color": "#FFB300"},
    "PULSE":    {"role": "Research & Web LLMs",    "color": "#FF6D00"},
    "VIBE":     {"role": "OS, Desktops & Media",   "color": "#1DB954"},
}

class AeroCommandCenterUI:
    def __init__(self, wake_callback):
        self.wake_callback = wake_callback
        self.ui_queue = queue.Queue()
        self.cmd_queue = queue.Queue()
        self.approval_result = None
        self.approval_event = threading.Event()
        self.war_room_visible = False

        self.root = None
        self.orb_win = None
        self.war_room = None
        self.agent_Badges = {}
        self.agent_Tasks = {}
        self.feed_box = None
        self.entry_var = None

        self.thread = threading.Thread(target=self._run_tk, daemon=True)
        self.thread.start()

    def _run_tk(self):
        self.root = tk.Tk()
        self.root.title("Aero Live HUD")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#000001")
        self.root.configure(bg="#000001")

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        # --- A. Main Gemini-Live Expanded HUD (Bottom Center) ---
        w, h = 650, 96
        x = (sw - w) // 2
        y = sh - h - 52
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.canvas = tk.Canvas(self.root, width=w, height=h, bg="#000001", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.pill = self.canvas.create_rectangle(
            8, 8, w - 8, h - 8, fill="#0D1117", outline="#00E5FF", width=2
        )
        self.status_label = tk.Label(
            self.root, text="👑 AERO LIVE ACTIVE",
            fg="#FFFFFF", bg="#0D1117", font=("Segoe UI", 11, "bold"), cursor="hand2"
        )
        self.status_label.place(relx=0.42, rely=0.35, anchor="center")
        self.status_label.bind("<Button-1>", lambda e: self.wake_callback())

        self.sub_label = tk.Label(
            self.root, text="Shift+Alt+Space to toggle/interrupt | Click WAR ROOM for swarm view",
            fg="#8AB4F8", bg="#0D1117", font=("Segoe UI", 9)
        )
        self.sub_label.place(relx=0.42, rely=0.68, anchor="center")

        war_btn = tk.Button(
            self.root, text="WAR ROOM", bg="#161B22", fg="#00E5FF",
            font=("Consolas", 8, "bold"), relief="flat", activebackground="#21262D",
            command=self._toggle_war_room, cursor="hand2"
        )
        war_btn.place(relx=0.83, rely=0.5, anchor="center", width=82, height=34)

        quit_btn = tk.Button(
            self.root, text="✕", bg="#161B22", fg="#FF5252",
            font=("Segoe UI", 9, "bold"), relief="flat",
            command=lambda: os._exit(0), cursor="hand2"
        )
        quit_btn.place(relx=0.93, rely=0.5, anchor="center", width=32, height=34)

        # --- B. Sleek Floating Activator Button when Asleep (Bottom Right) ---
        self.orb_win = tk.Toplevel(self.root)
        self.orb_win.overrideredirect(True)
        self.orb_win.attributes("-topmost", True)
        self.orb_win.attributes("-alpha", 0.92)
        self.orb_win.configure(bg="#0D1117")
        ow, oh = 215, 44
        ox = sw - ow - 24
        oy = sh - oh - 58
        self.orb_win.geometry(f"{ow}x{oh}+{ox}+{oy}")

        orb_frame = tk.Frame(self.orb_win, bg="#0D1117", highlightthickness=2, highlightbackground="#00E5FF")
        orb_frame.pack(fill="both", expand=True)

        orb_btn = tk.Button(
            orb_frame, text="⚡ AERO LIVE  [Shift+Alt+Space]",
            bg="#0D1117", fg="#00E5FF", activebackground="#161B22", activeforeground="#FFFFFF",
            font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
            command=self.wake_callback
        )
        orb_btn.pack(fill="both", expand=True)

        # --- C. Multi-Agent War Room Dashboard (Top-Right) ---
        self.war_room = tk.Toplevel(self.root)
        self.war_room.title("AERO CORP // MULTI-AGENT WAR ROOM")
        self.war_room.overrideredirect(True)
        self.war_room.attributes("-topmost", True)
        self.war_room.attributes("-alpha", 0.94)
        self.war_room.configure(bg="#090D16")

        ww, wh = 460, 540
        wx = sw - ww - 20
        wy = 30
        self.war_room.geometry(f"{ww}x{wh}+{wx}+{wy}")

        hdr = tk.Frame(self.war_room, bg="#111827", height=36)
        hdr.pack(fill="x")
        tk.Label(
            hdr, text="⚡ AERO CORP // LIVE AGENT SWARM",
            fg="#00E5FF", bg="#111827", font=("Consolas", 10, "bold")
        ).pack(side="left", padx=10, pady=6)

        min_btn = tk.Button(
            hdr, text="HIDE", bg="#1F2937", fg="#9CA3AF", font=("Consolas", 8),
            relief="flat", command=self._toggle_war_room, cursor="hand2"
        )
        min_btn.pack(side="right", padx=8, pady=4)

        grid_frame = tk.Frame(self.war_room, bg="#090D16")
        grid_frame.pack(fill="x", padx=10, pady=6)

        for ag_id, meta in AGENTS_META.items():
            row_f = tk.Frame(grid_frame, bg="#111827", highlightthickness=1, highlightbackground="#1F2937")
            row_f.pack(fill="x", pady=2)

            tk.Label(
                row_f, text=f" {ag_id} ", fg=meta["color"], bg="#111827",
                font=("Consolas", 9, "bold"), width=10, anchor="w"
            ).pack(side="left", padx=4, pady=3)

            lbl_task = tk.Label(
                row_f, text=meta["role"], fg="#D1D5DB", bg="#111827",
                font=("Segoe UI", 8), anchor="w"
            )
            lbl_task.pack(side="left", fill="x", expand=True, padx=4)

            lbl_badge = tk.Label(
                row_f, text="IDLE", fg="#6B7280", bg="#090D16",
                font=("Consolas", 8, "bold"), width=9
            )
            lbl_badge.pack(side="right", padx=6, pady=3)

            self.agent_Badges[ag_id] = lbl_badge
            self.agent_Tasks[ag_id] = lbl_task

        tk.Label(
            self.war_room, text="LIVE COMPANY COMMS & EXECUTION BUS",
            fg="#6B7280", bg="#090D16", font=("Consolas", 8, "bold"), anchor="w"
        ).pack(fill="x", padx=12, pady=(4, 0))

        self.feed_box = tk.Text(
            self.war_room, bg="#05070B", fg="#A7F3D0", font=("Consolas", 8),
            height=14, relief="flat", wrap="word", state="disabled"
        )
        self.feed_box.pack(fill="both", expand=True, padx=10, pady=4)

        inp_frame = tk.Frame(self.war_room, bg="#111827")
        inp_frame.pack(fill="x", padx=10, pady=(2, 8))

        self.entry_var = tk.StringVar()
        entry = tk.Entry(
            inp_frame, textvariable=self.entry_var, bg="#1F2937", fg="#FFFFFF",
            insertbackground="#00E5FF", font=("Segoe UI", 9), relief="flat"
        )
        entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(4, 4), pady=4)
        entry.bind("<Return>", self._submit_text_mission)

        send_btn = tk.Button(
            inp_frame, text="DEPLOY", bg="#00E5FF", fg="#000000",
            font=("Consolas", 8, "bold"), relief="flat", command=self._submit_text_mission, cursor="hand2"
        )
        send_btn.pack(side="right", padx=4, pady=4)

        # Start in minimal floating button mode until triggered
        self.war_room.withdraw()
        self.root.withdraw()

        self.root.after(40, self._poll_queue)
        self.root.mainloop()

    def _toggle_war_room(self):
        if not self.war_room:
            return
        if self.war_room_visible:
            self.war_room.withdraw()
            self.war_room_visible = False
        else:
            self.war_room.deiconify()
            self.war_room_visible = True

    def _submit_text_mission(self, event=None):
        txt = self.entry_var.get().strip()
        if txt:
            self.entry_var.set("")
            self.cmd_queue.put(txt)

    def _poll_queue(self):
        try:
            while not self.ui_queue.empty():
                msg = self.ui_queue.get_nowait()
                mtype = msg.get("type")
                if mtype == "mode":
                    if msg["awake"]:
                        self.orb_win.withdraw()
                        self.root.deiconify()
                    else:
                        self.root.withdraw()
                        self.orb_win.deiconify()
                elif mtype == "hud":
                    self.canvas.itemconfig(self.pill, outline=msg["color"])
                    self.status_label.config(text=str(msg["title"])[:60])
                    self.sub_label.config(text=str(msg["subtitle"])[:85])
                elif mtype == "agent":
                    ag = msg["agent"]
                    if ag in self.agent_Badges:
                        self.agent_Badges[ag].config(text=msg["status"][:9], fg=msg["color"])
                        self.agent_Tasks[ag].config(text=str(msg["task"])[:42])
                elif mtype == "log":
                    self.feed_box.config(state="normal")
                    ts = datetime.now().strftime("%H:%M:%S")
                    self.feed_box.insert("end", f"[{ts}] [{msg['agent']}] {msg['text']}\n")
                    self.feed_box.see("end")
                    self.feed_box.config(state="disabled")
                elif mtype == "war_room":
                    if msg["show"] and not self.war_room_visible:
                        self._toggle_war_room()
                    elif not msg["show"] and self.war_room_visible:
                        self._toggle_war_room()
        except Exception:
            pass
        if self.root:
            self.root.after(40, self._poll_queue)

    def set_awake_mode(self, awake: bool):
        self.ui_queue.put({"type": "mode", "awake": awake})

    def update(self, title, subtitle="", color="#00E5FF"):
        self.ui_queue.put({"type": "hud", "title": title, "subtitle": subtitle, "color": color})

    def set_agent_state(self, agent: str, status: str, task: str, color: str = "#00E5FF"):
        self.ui_queue.put({"type": "agent", "agent": agent, "status": status, "task": task, "color": color})

    def log_bus(self, agent: str, text: str):
        print(f"📡 [{agent}]: {text}")
        self.ui_queue.put({"type": "log", "agent": agent, "text": text})

    def show_war_room(self, show: bool = True):
        self.ui_queue.put({"type": "war_room", "show": show})

    def ask_approval(self, command_str: str) -> bool:
        self.approval_event.clear()
        self.set_awake_mode(True)
        self.update("⚠️ SENTINEL Needs Approval [Press Y / N]", f"Run: {command_str}", "#FF9100")
        self.log_bus("SENTINEL", f"Awaiting Y/N approval for: {command_str}")
        while not self.approval_event.is_set():
            if keyboard.is_pressed("y"):
                self.approval_result = True
                self.approval_event.set()
            elif keyboard.is_pressed("n") or keyboard.is_pressed("esc"):
                self.approval_result = False
                self.approval_event.set()
            time.sleep(0.05)
        return self.approval_result

# ==========================================
# 2. SHARED COMPANY MEMORY
# ==========================================
def load_company_memory() -> dict:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"missions_completed": 0, "notes": [], "recent_conversations": []}

def save_company_memory(mem: dict):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2)
    except Exception:
        pass

company_memory = load_company_memory()
hud = None

# ==========================================
# 3. SPECIALIZED DEPARTMENT AGENT ENGINES
# ==========================================
def capture_screen_pil():
    with mss.mss() as sct:
        mon = sct.monitors[1]
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        img.thumbnail((1280, 720))
        return img

def focus_window_by_title(keyword: str) -> bool:
    target = keyword.lower().strip()
    for win in gw.getAllWindows():
        if win.title and target in win.title.lower():
            try:
                if win.isMinimized:
                    win.restore()
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                win.activate()
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                time.sleep(0.35)
                return True
            except Exception:
                pass
    return False

def run_atlas_agent(task: str, shared_context: str = "") -> str:
    hud.set_agent_state("ATLAS", "THINKING", task, "#D500F9")
    hud.log_bus("ATLAS", f"Analyzing complex task: {task}")
    sys_inst = (
        "You are ATLAS, CTO of Devang's AI Laptop Company. Provide high-level technical solutions, "
        "clean architecture, or exact code. Keep your summary crisp so the CEO and VP Eng can action it."
    )
    res = call_gemini(f"Context:\n{shared_context}\n\nCTO Task:\n{task}", system_instruction=sys_inst, use_pro=True)
    hud.set_agent_state("ATLAS", "DONE", "Architecture ready", "#00E676")
    hud.log_bus("ATLAS", f"Completed analysis ({len(res)} chars).")
    return res

def run_nova_agent(action: str, task_prompt: str, target_path: str = "", file_content: str = "", shared_context: str = "") -> str:
    hud.set_agent_state("NOVA", "CODING", f"{action}: {task_prompt}", "#00E676")
    hud.log_bus("NOVA", f"Engineering Action [{action}] -> {task_prompt}")

    if action == "write_file" and target_path:
        full_p = os.path.expanduser(target_path)
        os.makedirs(os.path.dirname(os.path.abspath(full_p)), exist_ok=True)
        content_to_write = file_content
        if not content_to_write:
            code_prompt = f"Write the complete, raw production code for file '{target_path}'. Task: {task_prompt}\nContext: {shared_context}\nOutput ONLY raw code without markdown fences."
            content_to_write = call_gemini(code_prompt, use_pro=True)
            content_to_write = content_to_write.removeprefix("```python").removeprefix("```javascript").removeprefix("```").removesuffix("```").strip()
        with open(full_p, "w", encoding="utf-8") as f:
            f.write(content_to_write)
        hud.set_agent_state("NOVA", "DONE", f"Wrote {os.path.basename(full_p)}", "#00E676")
        hud.log_bus("NOVA", f"Wrote file: {full_p}")
        return f"Created/updated file {full_p}"

    if target_path and os.path.exists(os.path.expanduser(target_path)):
        subprocess.Popen(f'code "{os.path.expanduser(target_path)}"', shell=True, creationflags=CREATE_NO_WINDOW)
        time.sleep(2.0)
    elif not focus_window_by_title("Visual Studio Code"):
        subprocess.Popen("code .", shell=True, creationflags=CREATE_NO_WINDOW)
        time.sleep(2.2)

    focus_window_by_title("Visual Studio Code")
    time.sleep(0.4)

    enriched_prompt = task_prompt if not shared_context else f"{task_prompt}\n\nContext:\n{shared_context[:1000]}"
    pyperclip.copy(enriched_prompt)

    if "codex" in action.lower():
        pyautogui.hotkey("ctrl", "shift", "p")
        time.sleep(0.4)
        pyautogui.write("Codex", interval=0.02)
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.5)
    else:
        pyautogui.hotkey("ctrl", "shift", "i")
        time.sleep(0.5)

    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.2)
    pyautogui.press("enter")

    hud.set_agent_state("NOVA", "DONE", "Dispatched to VS Code", "#00E676")
    return f"Dispatched to VS Code ({action}): {task_prompt}"

def run_sentinel_agent(command: str) -> str:
    hud.set_agent_state("SENTINEL", "AUDITING", command, "#FFB300")
    hud.log_bus("SENTINEL", f"Executing Shell/Git: {command}")

    if any(k in command.lower() for k in DANGEROUS_KEYWORDS):
        if not hud.ask_approval(command):
            hud.set_agent_state("SENTINEL", "BLOCKED", "User rejected cmd", "#FF5252")
            return "Command rejected by Devang."

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=35, creationflags=CREATE_NO_WINDOW
        )
        out = (res.stdout + "\n" + res.stderr).strip()
        summary = out[:1500] if out else "Command succeeded."
        hud.set_agent_state("SENTINEL", "DONE", "Audit complete", "#00E676")
        hud.log_bus("SENTINEL", f"Output: {summary[:140]}")
        return summary
    except Exception as e:
        hud.set_agent_state("SENTINEL", "ERROR", str(e)[:25], "#FF5252")
        return f"Terminal error: {e}"

def run_pulse_agent(action: str, query_or_prompt: str, shared_context: str = "") -> str:
    hud.set_agent_state("PULSE", "ACTIVE", f"{action}: {query_or_prompt}", "#FF6D00")
    hud.log_bus("PULSE", f"Running [{action}] -> {query_or_prompt}")

    if action == "inspect_screen":
        img = capture_screen_pil()
        ans = call_gemini(f"Analyze Devang's screen and answer concisely: {query_or_prompt}", image_pil=img)
        hud.set_agent_state("PULSE", "DONE", "Screen analyzed", "#00E676")
        return ans

    elif action == "vision_click":
        img = capture_screen_pil()
        sw, sh = pyautogui.size()
        prompt = f"Locate UI element '{query_or_prompt}'. Return JSON: {{\"x_ratio\": float, \"y_ratio\": float}}"
        raw = call_gemini(prompt, json_mode=True, image_pil=img)
        try:
            coords = json.loads(raw)
            pyautogui.click(int(coords["x_ratio"] * sw), int(coords["y_ratio"] * sh))
            hud.set_agent_state("PULSE", "DONE", f"Clicked {query_or_prompt}", "#00E676")
            return f"Clicked '{query_or_prompt}' on screen."
        except Exception:
            return f"Could not locate '{query_or_prompt}' on screen."

    elif action in ("claude_web", "chatgpt_web"):
        url = "https://claude.ai/new" if "claude" in action else "https://chatgpt.com/"
        webbrowser.open(url)
        time.sleep(4.5)
        full_p = query_or_prompt if not shared_context else f"{query_or_prompt}\n\nContext:\n{shared_context[:1000]}"
        pyperclip.copy(full_p)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(5.0)

        img = capture_screen_pil()
        chk = call_gemini(
            "Did this web LLM hit a usage/rate limit wall? Return JSON: {\"rate_limited\": bool, \"visible_context\": \"string\"}",
            json_mode=True, image_pil=img
        )
        try:
            d = json.loads(chk)
            if d.get("rate_limited"):
                hud.log_bus("PULSE", "⚠️ Web LLM hit rate limit! Handing context to ATLAS (Gemini Pro)...")
                return run_atlas_agent(f"Continue this rate-limited task: {query_or_prompt}", d.get("visible_context", ""))
        except Exception:
            pass
        hud.set_agent_state("PULSE", "DONE", "Web LLM running", "#00E676")
        return f"Dispatched task to {action} in browser."

    elif action == "youtube_search":
        webbrowser.open(f"https://www.youtube.com/results?search_query={query_or_prompt.replace(' ', '+')}")
        hud.set_agent_state("PULSE", "DONE", "YouTube opened", "#00E676")
        return f"Searched YouTube for {query_or_prompt}"

    else:
        webbrowser.open(f"https://www.google.com/search?q={query_or_prompt.replace(' ', '+')}")
        hud.set_agent_state("PULSE", "DONE", "Google searched", "#00E676")
        return f"Searched Google for {query_or_prompt}"

def run_vibe_agent(action: str, value: str = "") -> str:
    hud.set_agent_state("VIBE", "OPS", f"{action} {value}", "#1DB954")
    hud.log_bus("VIBE", f"OS/Media Operation: {action} ({value})")

    if action == "spotify":
        found = focus_window_by_title("Spotify")
        if not found:
            if focus_window_by_title("Brave"):
                webbrowser.open("https://open.spotify.com")
            else:
                subprocess.Popen("start spotify:", shell=True, creationflags=CREATE_NO_WINDOW)
            time.sleep(3.0)
            focus_window_by_title("Spotify")

        if not value.strip():
            hud.set_agent_state("VIBE", "WAITING", "Awaiting song choice", "#1DB954")
            return "Spotify is focused. Ask Devang which song to play."

        time.sleep(0.9)
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.3)
        pyperclip.copy(value)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.35)
        pyautogui.press("enter")
        time.sleep(1.1)
        pyautogui.press("tab")
        pyautogui.press("enter")
        hud.set_agent_state("VIBE", "PLAYING", value, "#1DB954")
        return f"Playing '{value}' on Spotify."

    elif action == "next_desktop":
        pyautogui.hotkey("win", "ctrl", "right")
    elif action == "prev_desktop":
        pyautogui.hotkey("win", "ctrl", "left")
    elif action == "new_desktop":
        pyautogui.hotkey("win", "ctrl", "d")
    elif action == "next_tab":
        pyautogui.hotkey("ctrl", "tab")
    elif action == "prev_tab":
        pyautogui.hotkey("ctrl", "shift", "tab")
    elif action == "new_tab":
        pyautogui.hotkey("ctrl", "t")
    elif action == "close_tab":
        pyautogui.hotkey("ctrl", "w")
    elif action == "focus_app":
        if not focus_window_by_title(value):
            subprocess.Popen(f"start {value}", shell=True, creationflags=CREATE_NO_WINDOW)
    elif action == "media_play_pause":
        pyautogui.press("playpause")
    elif action == "media_next":
        pyautogui.press("nexttrack")
    elif action == "volume_up":
        for _ in range(5): pyautogui.press("volumeup")
    elif action == "volume_down":
        for _ in range(5): pyautogui.press("volumedown")
    elif action == "show_war_room":
        hud.show_war_room(True)
    elif action == "hide_war_room":
        hud.show_war_room(False)

    hud.set_agent_state("VIBE", "DONE", action, "#00E676")
    return f"Executed OS action: {action} {value}"

# ==========================================
# 4. AERO (CEO): MULTI-AGENT ORCHESTRATOR
# ==========================================
async def speak_with_barge_in(text: str):
    if not text:
        return
    clean_text = text.replace("*", "").replace("#", "").replace("`", "").strip()
    hud.log_bus("AERO", clean_text)
    hud.update("🟣 AERO Speaking...", "Press Shift+Alt+Space or Spacebar to interrupt", "#D500F9")
    hud.set_agent_state("AERO", "SPEAKING", clean_text[:35], "#D500F9")

    out_file = os.path.join(BASE_DIR, "aero_tts.mp3")
    communicate = edge_tts.Communicate(clean_text, "en-US-ChristopherNeural", rate="+28%")
    await communicate.save(out_file)

    pygame.mixer.music.load(out_file)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        if keyboard.is_pressed("space") or keyboard.is_pressed(WAKE_HOTKEY):
            pygame.mixer.music.stop()
            break
        await asyncio.sleep(0.03)

    pygame.mixer.music.unload()
    hud.set_agent_state("AERO", "ONLINE", "Awaiting directive", "#00E5FF")
    try:
        os.remove(out_file)
    except Exception:
        pass

async def execute_single_agent_step(step: dict, shared_bus: list) -> str:
    agent = step.get("agent", "AERO").upper()
    action = step.get("action", "")
    task = step.get("task", "")
    target = step.get("target", "")
    ctx = "\n".join(shared_bus[-5:]) if shared_bus else ""

    if agent == "ATLAS":
        out = await asyncio.to_thread(run_atlas_agent, task, ctx)
    elif agent == "NOVA":
        out = await asyncio.to_thread(run_nova_agent, action, task, target, "", ctx)
    elif agent == "SENTINEL":
        out = await asyncio.to_thread(run_sentinel_agent, task)
    elif agent == "PULSE":
        out = await asyncio.to_thread(run_pulse_agent, action, task, ctx)
    elif agent == "VIBE":
        out = await asyncio.to_thread(run_vibe_agent, action, task)
    else:
        out = f"AERO handled: {task}"

    entry = f"[{agent} REPORT]: {out[:600]}"
    shared_bus.append(entry)
    return entry

async def orchestrate_company_mission(user_prompt: str) -> tuple[str, bool]:
    global company_memory

    desktop_projects = []
    try:
        dp = os.path.expanduser("~/Desktop")
        desktop_projects = [d for d in os.listdir(dp) if os.path.isdir(os.path.join(dp, d))][:15]
    except Exception:
        pass

    hud.set_agent_state("AERO", "PLANNING", user_prompt[:35], "#00E5FF")
    hud.update("🧠 AERO Orchestrating Swarm...", user_prompt, "#00E5FF")
    hud.log_bus("DEVANG", user_prompt)

    ceo_system_prompt = f"""
    You are AERO, CEO & Chief Orchestrator of Devang's autonomous AI company running natively on his Windows laptop.
    You command 5 department heads that execute in PARALLEL or SEQUENCE:
    1. "ATLAS" (CTO - Gemini Pro): Deep coding, system design, debugging, math, rate-limit failover.
       - actions: "architect", "solve"
    2. "NOVA" (VP Eng - VS Code & Files): Controls VS Code Antigravity ("antigravity"), Codex ("codex"), or writes code files directly to disk ("write_file" with target="path/to/file.py").
       - actions: "antigravity", "codex", "write_file"
    3. "SENTINEL" (QA & SecOps - PowerShell/Git): Runs terminal commands, git status/diff/log, directory checks, pytest.
       - actions: "terminal" (put the exact PowerShell/git command in "task")
    4. "PULSE" (Research, Vision & Web LLMs): Screen vision ("inspect_screen"), clicking UI via vision ("vision_click"), running tasks on Claude ("claude_web") or ChatGPT ("chatgpt_web"), or searching ("google_search", "youtube_search").
       - actions: "inspect_screen", "vision_click", "claude_web", "chatgpt_web", "google_search", "youtube_search"
    5. "VIBE" (Chief of Ops - OS & Spotify): Controls Spotify ("spotify" - put song name in "task", or "" if just opening Spotify), desktops ("next_desktop", "prev_desktop", "new_desktop"), tabs ("next_tab", "prev_tab", "new_tab", "close_tab"), windows ("focus_app"), volume ("volume_up", "volume_down"), or dashboard ("show_war_room", "hide_war_room").

    Known Desktop Projects: {desktop_projects}
    Recent Conversation History: {company_memory.get("recent_conversations", [])[-6:]}

    Return ONLY a valid JSON object matching this exact schema:
    {{
        "is_sleep": false,
        "initial_spoken_ack": "Short 1-sentence Jarvis-style announcement if launching multiple agents, or empty string if fast single action",
        "parallel_wave": [
            {{
                "agent": "ATLAS" | "NOVA" | "SENTINEL" | "PULSE" | "VIBE",
                "action": "specific action name from above",
                "task": "exact command, song name, search query, or prompt",
                "target": "optional file/project path for NOVA"
            }}
        ],
        "followup_wave": [
            {{
                "agent": "ATLAS" | "NOVA" | "SENTINEL" | "PULSE" | "VIBE",
                "action": "specific action name",
                "task": "task that uses outputs from parallel_wave",
                "target": "optional path"
            }}
        ],
        "final_spoken_reply": "Concise, natural spoken response to Devang (1-2 sentences)."
    }}
    """

    raw_plan = call_gemini(f"Devang's Directive: {user_prompt}", system_instruction=ceo_system_prompt, json_mode=True)
    raw_plan = raw_plan.removeprefix("```json").removesuffix("```").strip()

    try:
        plan = json.loads(raw_plan)
    except Exception:
        plan = {"is_sleep": False, "parallel_wave": [], "followup_wave": [], "final_spoken_reply": "Right away, sir."}

    if plan.get("is_sleep"):
        return plan.get("final_spoken_reply", "Entering standby mode, sir."), True

    p_wave = plan.get("parallel_wave") or []
    f_wave = plan.get("followup_wave") or []
    shared_bus = []

    if len(p_wave) + len(f_wave) >= 2:
        hud.show_war_room(True)
        if plan.get("initial_spoken_ack"):
            await speak_with_barge_in(plan["initial_spoken_ack"])

    if p_wave:
        hud.update(f"⚡ Running {len(p_wave)} Agent(s)...", ", ".join(s.get("agent","") for s in p_wave), "#00E676")
        await asyncio.gather(*(execute_single_agent_step(step, shared_bus) for step in p_wave))

    if f_wave:
        hud.update(f"⚡ Follow-up Wave ({len(f_wave)} Agent(s))...", ", ".join(s.get("agent","") for s in f_wave), "#D500F9")
        await asyncio.gather(*(execute_single_agent_step(step, shared_bus) for step in f_wave))

    final_reply = plan.get("final_spoken_reply", "Mission completed, sir.")

    if shared_bus and any(s.get("agent") in ("PULSE", "ATLAS", "SENTINEL") for s in (p_wave + f_wave)):
        synth_prompt = (
            f"Devang asked: '{user_prompt}'\n"
            f"Agent Reports:\n" + "\n".join(shared_bus) + "\n"
            "Give a crisp, 1-to-2 sentence spoken executive summary for Devang."
        )
        synthesized = await asyncio.to_thread(call_gemini, synth_prompt)
        if synthesized and "temporarily busy" not in synthesized:
            final_reply = synthesized

    company_memory["missions_completed"] = company_memory.get("missions_completed", 0) + 1
    company_memory.setdefault("recent_conversations", []).append(f"Devang: {user_prompt} -> Aero: {final_reply}")
    company_memory["recent_conversations"] = company_memory["recent_conversations"][-12:]
    save_company_memory(company_memory)

    return final_reply, False

# ==========================================
# 5. ALWAYS-ON HOTKEY, BUTTON & VOICE LOOP
# ==========================================
def listen_mic(timeout=4, phrase_limit=14):
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.2)
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            return recognizer.recognize_google(audio).lower()
        except Exception:
            return None

async def main():
    global hud
    hotkey_pressed = False

    def trigger_wake():
        nonlocal hotkey_pressed
        hotkey_pressed = True

    hud = AeroCommandCenterUI(wake_callback=trigger_wake)
    keyboard.add_hotkey(WAKE_HOTKEY, trigger_wake)
    hud.log_bus("AERO", f"Standalone daemon active. Press {WAKE_HOTKEY.upper()} or click ⚡ AERO button.")

    active_until = 0

    while True:
        if not hud.cmd_queue.empty():
            typed_cmd = hud.cmd_queue.get_nowait()
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
            hud.set_awake_mode(True)
            reply, should_sleep = await orchestrate_company_mission(typed_cmd)
            await speak_with_barge_in(reply)
            if should_sleep:
                active_until = 0
                hud.set_awake_mode(False)
            continue

        is_awake = (time.time() < active_until) or hotkey_pressed

        if hotkey_pressed:
            hotkey_pressed = False
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
            hud.set_awake_mode(True)
            await speak_with_barge_in("Aero Live online. Go ahead, sir.")
            is_awake = True

        if is_awake:
            hud.set_awake_mode(True)
            hud.update("🔵 AERO Live Listening...", "Speak freely | Shift+Alt+Space to interrupt | WAR ROOM for swarm", "#00E5FF")
            heard = await asyncio.to_thread(listen_mic, 4, 15)
            if not heard:
                continue

            reply, should_sleep = await orchestrate_company_mission(heard)
            await speak_with_barge_in(reply)

            if should_sleep:
                active_until = 0
                hud.set_awake_mode(False)
            else:
                active_until = time.time() + ACTIVE_WINDOW_SECONDS
        else:
            hud.set_awake_mode(False)
            heard = await asyncio.to_thread(listen_mic, 2, 5)
            if not heard:
                continue

            for ww in WAKE_WORDS:
                if ww in heard:
                    remainder = heard.split(ww, 1)[1].strip()
                    active_until = time.time() + ACTIVE_WINDOW_SECONDS
                    hud.set_awake_mode(True)
                    if remainder:
                        reply, should_sleep = await orchestrate_company_mission(remainder)
                        await speak_with_barge_in(reply)
                        if should_sleep:
                            active_until = 0
                            hud.set_awake_mode(False)
                    else:
                        await speak_with_barge_in("Aero Live online. What's the directive, sir?")
                    break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
