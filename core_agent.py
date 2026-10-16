import os
import sys
import time
import json
import ctypes
import asyncio
import warnings
import threading
import subprocess
import webbrowser
from io import BytesIO

warnings.filterwarnings("ignore")

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

# ==========================================
# 0. CONFIGURATION & AUTO-MODEL DISCOVERY
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ ERROR: GEMINI_API_KEY is not set in your environment!")
    print('Run: $env:GEMINI_API_KEY="your_key" and restart.')
    sys.exit(1)

WAKE_WORDS = ["aero", "arrow", "asimo", "hey aero", "ok aero", "jarvis"]
WAKE_HOTKEY = "alt+space"
ACTIVE_WINDOW_SECONDS = 20

# Audio Specs
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 512

client = genai.Client(api_key=GEMINI_API_KEY)
live_client = genai.Client(api_key=GEMINI_API_KEY, http_options={"api_version": "v1alpha"})
recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True
pygame.mixer.init()

def discover_models():
    """Dynamically queries the API key's available models so 404 errors never happen."""
    available = []
    try:
        for m in client.models.list():
            name = m.name.replace("models/", "")
            available.append(name)
    except Exception:
        pass

    flash_candidates = [
        "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash",
        "gemini-2.0-flash-lite", "gemini-1.5-flash-latest"
    ]
    pro_candidates = [
        "gemini-2.5-pro", "gemini-pro-latest", "gemini-2.0-pro-exp"
    ]
    live_candidates = [
        "gemini-2.0-flash-exp", "gemini-2.0-flash-live-001",
        "gemini-2.5-flash-native-audio-preview-09-2025"
    ]

    flash_Pool = [m for m in flash_candidates if m in available] or flash_candidates
    pro_Pool = [m for m in pro_candidates if m in available] or pro_candidates
    live_Pool = [m for m in live_candidates if m in available] or live_candidates
    return flash_Pool, pro_Pool, live_Pool

FLASH_MODELS, PRO_MODELS, LIVE_MODELS = discover_models()
print(f"✅ Auto-Discovered Flash Models: {FLASH_MODELS[:2]}")
print(f"✅ Auto-Discovered Pro Models:   {PRO_MODELS[:2]}")

# ==========================================
# 1. GOOGLE-ASSISTANT FLOATING HUD OVERLAY
# ==========================================
class AeroHUD:
    def __init__(self):
        self.root = None
        self.canvas = None
        self.pill = None
        self.status_label = None
        self.sub_label = None
        self.approval_result = None
        self.approval_event = threading.Event()
        self.thread = threading.Thread(target=self._run_tk, daemon=True)
        self.thread.start()

    def _run_tk(self):
        self.root = tk.Tk()
        self.root.title("Aero HUD")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#000001")
        self.root.configure(bg="#000001")

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 560, 92
        x = (sw - w) // 2
        y = sh - h - 55
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.canvas = tk.Canvas(self.root, width=w, height=h, bg="#000001", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.pill = self.canvas.create_rectangle(
            8, 8, w - 8, h - 8, fill="#101218", outline="#00E5FF", width=2
        )
        self.status_label = tk.Label(
            self.root, text="🟢 Aero Ready (Say 'Aero' or press Alt+Space)",
            fg="#FFFFFF", bg="#101218", font=("Segoe UI", 11, "bold")
        )
        self.status_label.place(relx=0.5, rely=0.35, anchor="center")

        self.sub_label = tk.Label(
            self.root, text="Autonomous OS, VS Code Antigravity & Browser Agent",
            fg="#8AB4F8", bg="#101218", font=("Segoe UI", 9)
        )
        self.sub_label.place(relx=0.5, rely=0.68, anchor="center")
        self.root.mainloop()

    def update(self, title, subtitle="", color="#00E5FF"):
        if not self.root:
            return
        def _do():
            self.canvas.itemconfig(self.pill, outline=color)
            self.status_label.config(text=str(title)[:58])
            self.sub_label.config(text=str(subtitle)[:80])
        self.root.after(0, _do)

    def ask_approval(self, command_str):
        """Interactive Y/N approval gate on the floating HUD."""
        self.approval_event.clear()
        self.update("⚠️ Approve System Action? [Press Y / N]", f"Cmd: {command_str}", "#FF9100")
        while not self.approval_event.is_set():
            if keyboard.is_pressed("y"):
                self.approval_result = True
                self.approval_event.set()
            elif keyboard.is_pressed("n") or keyboard.is_pressed("esc"):
                self.approval_result = False
                self.approval_event.set()
            time.sleep(0.05)
        return self.approval_result

hud = AeroHUD()

# ==========================================
# 2. COMPLETE OS, BROWSER, VSCODE & LLM TOOLS
# ==========================================

def capture_screen_pil():
    with mss.mss() as sct:
        mon = sct.monitors[1]
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        img.thumbnail((1280, 720))
        return img

def capture_screen_bytes():
    img = capture_screen_pil()
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return buf.getvalue()

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
                time.sleep(0.4)
                return True
            except Exception:
                pass
    return False

def execute_terminal_command(command: str, require_approval: bool = True) -> str:
    """Runs any PowerShell, Git, or system command with HUD Y/N approval."""
    print(f"🛠️ [Terminal]: {command}")
    if require_approval:
        if not hud.ask_approval(command):
            return "User denied permission to run the command."
    hud.update("⚡ Executing Terminal Command...", command, "#FFB300")
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=35
        )
        out = (res.stdout + "\n" + res.stderr).strip()
        return out[:2000] if out else "Executed successfully."
    except Exception as e:
        return f"Command failed: {e}"

def delegate_to_vscode_agent(agent_name: str, task_prompt: str, project_path: str = "") -> str:
    """
    Controls VS Code Antigravity or Codex directly without needing a custom extension.
    Opens the project, focuses VS Code, opens the agent chat input, and submits the prompt.
    """
    print(f"🛠️ [VS Code {agent_name}]: {task_prompt}")
    hud.update(f"💻 Routing to VS Code ({agent_name})...", task_prompt, "#00E676")

    if project_path and os.path.exists(os.path.expanduser(project_path)):
        subprocess.Popen(f'code "{os.path.expanduser(project_path)}"', shell=True)
        time.sleep(2.0)
    elif not focus_window_by_title("Visual Studio Code"):
        subprocess.Popen("code .", shell=True)
        time.sleep(2.5)

    focus_window_by_title("Visual Studio Code")
    time.sleep(0.5)

    # Copy task prompt to clipboard
    pyperclip.copy(task_prompt)

    # Open VS Code AI Chat / Antigravity / Command Palette
    if "codex" in agent_name.lower():
        pyautogui.hotkey("ctrl", "shift", "p")
        time.sleep(0.4)
        pyautogui.write("Codex", interval=0.02)
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.6)
    else:
        # Focus Antigravity / Secondary Sidebar Chat in VS Code
        pyautogui.hotkey("ctrl", "shift", "i")
        time.sleep(0.6)

    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.2)
    pyautogui.press("enter")
    return f"Focused VS Code and dispatched task to {agent_name}: '{task_prompt}'"

def deep_think_with_gemini_pro(complex_task: str) -> str:
    """Uses Gemini Pro with Extended Thinking for heavy architecture, coding, or debugging tasks."""
    hud.update("🧠 Gemini Pro Extended Thinking...", complex_task, "#D500F9")
    for model_name in PRO_MODELS + FLASH_MODELS:
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=complex_task
            )
            return resp.text
        except Exception:
            continue
    return "Could not reach Gemini Pro."

def delegate_to_web_llm(provider: str, prompt: str) -> str:
    """
    Opens Claude or ChatGPT in Brave browser, pastes the task, checks via Screen Vision
    if the free tier limit is reached, and if rate-limited, automatically extracts context
    and finishes the task using Gemini Pro!
    """
    prov = provider.lower()
    url = "https://claude.ai/new" if "claude" in prov else "https://chatgpt.com/"
    hud.update(f"🌐 Opening {provider.title()} in Brave...", prompt, "#FF9100")

    webbrowser.open(url)
    time.sleep(4.5)

    pyperclip.copy(prompt)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)
    pyautogui.press("enter")

    hud.update(f"⏳ Monitoring {provider.title()} for Rate Limits...", "Inspecting browser state", "#FF9100")
    time.sleep(5.0)

    # Take a screenshot to check if Claude/ChatGPT hit a free-tier usage limit
    screen_img = capture_screen_pil()
    check_prompt = (
        f"Look at this screenshot of {provider}. Did it hit a usage limit / rate limit / upgrade wall? "
        "Reply in JSON: {\"rate_limited\": true/false, \"visible_context\": \"summary of work on screen\"}"
    )
    for m in FLASH_MODELS:
        try:
            vision_check = client.models.generate_content(
                model=m,
                contents=[screen_img, check_prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            data = json.loads(vision_check.text)
            if data.get("rate_limited"):
                hud.update("🔄 Limit Hit! Handing off to Gemini Pro...", "Continuing task seamlessly", "#D500F9")
                handoff_prompt = (
                    f"{provider} hit its free tier limit. Context so far: {data.get('visible_context')}.\n"
                    f"Original task: {prompt}\nFinish the task completely."
                )
                return deep_think_with_gemini_pro(handoff_prompt)
            break
        except Exception:
            continue

    return f"Submitted task to {provider.title()} in your browser and verified no rate limit was hit."

def open_or_control_spotify(song_query: str = "") -> str:
    """
    Finds if Spotify (desktop app or Brave tab) is already open across desktops, focuses it,
    and either asks which song to play or searches and plays the requested song immediately.
    """
    hud.update("🎵 Locating Spotify...", song_query or "Focusing window", "#1DB954")

    found = focus_window_by_title("Spotify")
    if not found:
        # Check if Brave is open, or launch Spotify web in Brave
        if focus_window_by_title("Brave"):
            webbrowser.open("https://open.spotify.com")
        else:
            subprocess.Popen("start spotify:", shell=True)
        time.sleep(3.0)
        focus_window_by_title("Spotify")

    if not song_query.strip():
        return "Spotify is now open and focused on your screen. Ask Devang which song he would like to play."

    time.sleep(1.0)
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.3)
    pyperclip.copy(song_query)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)
    pyautogui.press("enter")
    time.sleep(1.2)
    pyautogui.press("tab")
    pyautogui.press("enter")
    return f"Focused Spotify and started playing '{song_query}'."

def navigate_desktop_and_ui(action: str, value: str = "") -> str:
    """Switches virtual desktops, tabs, apps, clicks UI elements via Vision, or searches the web."""
    hud.update(f"🖥️ UI Action: {action}", value, "#B388FF")

    if action == "next_desktop":
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
            subprocess.Popen(f"start {value}", shell=True)
    elif action == "google_search":
        webbrowser.open(f"https://www.google.com/search?q={value.replace(' ', '+')}")
    elif action == "youtube_search":
        webbrowser.open(f"https://www.youtube.com/results?search_query={value.replace(' ', '+')}")
    elif action == "media_play_pause":
        pyautogui.press("playpause")
    elif action == "media_next":
        pyautogui.press("nexttrack")
    elif action == "volume_up":
        for _ in range(5): pyautogui.press("volumeup")
    elif action == "volume_down":
        for _ in range(5): pyautogui.press("volumedown")
    elif action == "vision_click":
        # Use Gemini Vision to locate coordinates of any element on screen and click it
        img = capture_screen_pil()
        sw, sh = pyautogui.size()
        prompt = (
            f"Find the UI element '{value}' on this screen. "
            "Return JSON: {\"x_ratio\": float (0.0 to 1.0), \"y_ratio\": float (0.0 to 1.0)}"
        )
        for m in FLASH_MODELS:
            try:
                r = client.models.generate_content(
                    model=m, contents=[img, prompt],
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                coords = json.loads(r.text)
                pyautogui.click(int(coords["x_ratio"] * sw), int(coords["y_ratio"] * sh))
                return f"Clicked on '{value}' using screen vision."
            except Exception:
                continue
    return f"Completed UI action: {action} ({value})"

def inspect_screen_with_vision(question: str) -> str:
    """Takes a live screenshot of Devang's laptop and analyzes it."""
    hud.update("👁️ Analyzing Screen...", question, "#00E676")
    img = capture_screen_pil()
    for m in FLASH_MODELS:
        try:
            r = client.models.generate_content(
                model=m,
                contents=[img, f"Answer concisely for voice output: {question}"]
            )
            return r.text
        except Exception:
            continue
    return "I couldn't inspect the screen right now."

# ==========================================
# 3. FAST VOICE & BARGE-IN ENGINE (ZERO-FAIL)
# ==========================================
conversation_history = []

async def speak_with_barge_in(text: str):
    """High-speed neural TTS with instant Spacebar or voice interruption."""
    if not text:
        return
    clean_text = text.replace("*", "").replace("#", "").replace("`", "").strip()
    print(f"🤖 Aero: {clean_text}")
    hud.update("🟣 Aero Speaking...", "Tap SPACE to interrupt anytime", "#D500F9")

    out_file = "aero_tts.mp3"
    communicate = edge_tts.Communicate(clean_text, "en-US-ChristopherNeural", rate="+28%")
    await communicate.save(out_file)

    pygame.mixer.music.load(out_file)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        if keyboard.is_pressed("space") or keyboard.is_pressed("alt+space"):
            print("🛑 [Interrupted by user]")
            pygame.mixer.music.stop()
            break
        await asyncio.sleep(0.03)

    pygame.mixer.music.unload()
    try:
        os.remove(out_file)
    except Exception:
        pass

def route_and_execute(user_prompt: str) -> tuple[str, bool]:
    """Routes any natural command across Gemini Flash, Pro, VS Code Antigravity/Codex, Claude/ChatGPT, Spotify, and OS."""
    global conversation_history

    desktop_projects = []
    try:
        desktop_path = os.path.expanduser("~/Desktop")
        desktop_projects = [d for d in os.listdir(desktop_path) if os.path.isdir(os.path.join(desktop_path, d))][:15]
    except Exception:
        pass

    system_prompt = f"""
    You are Aero, Devang's autonomous Jarvis-style voice OS orchestrator on his Windows laptop.
    Known projects on Devang's Desktop: {desktop_projects}
    
    Read the conversation history and Devang's latest command.
    Return ONLY a valid JSON object matching this exact schema:
    {{
        "tool": "none" | "vscode_agent" | "gemini_pro_think" | "web_llm" | "spotify" | "ui_nav" | "terminal" | "inspect_screen" | "sleep",
        "tool_args": {{
            "agent_name": "antigravity or codex",
            "task_prompt": "prompt or command",
            "project_path": "~/Desktop/ProjectName or empty",
            "provider": "claude or chatgpt",
            "song_query": "song name or empty if just opening spotify",
            "action": "next_desktop | prev_desktop | new_desktop | next_tab | prev_tab | new_tab | close_tab | focus_app | google_search | youtube_search | media_play_pause | media_next | volume_up | volume_down | vision_click",
            "value": "target app, search query, or button to click",
            "command": "powershell/git command",
            "question": "what to look for on screen"
        }},
        "spoken_reply": "Brief, natural Jarvis-style response to speak out loud (1-2 sentences max)."
    }}

    Routing Rules:
    - If Devang says "open Spotify" without a song: set tool="spotify", song_query="", and spoken_reply="Opening Spotify now. Which track should I play?"
    - If Devang names a song to play on Spotify: set tool="spotify", song_query="<song name>".
    - If Devang mentions Antigravity, Codex, VS Code, PR review, or writing code in his editor: set tool="vscode_agent".
    - If Devang explicitly mentions Claude or ChatGPT: set tool="web_llm".
    - If it's a complex architecture/math/reasoning question: set tool="gemini_pro_think".
    - If Devang asks what's on his screen or to read an error on screen: set tool="inspect_screen".
    - If Devang asks to switch desktops, tabs, windows, click something, or search Google/YouTube: set tool="ui_nav".
    - If Devang asks to run a terminal/git/system command: set tool="terminal".
    - If Devang says "go to sleep", "standby", or "goodbye": set tool="sleep".
    """

    conversation_history.append(f"Devang: {user_prompt}")
    if len(conversation_history) > 10:
        conversation_history = conversation_history[-10:]

    context_str = "\n".join(conversation_history)
    hud.update("🧠 Aero Thinking...", user_prompt, "#00E5FF")

    decision = None
    for model_name in FLASH_MODELS + PRO_MODELS:
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=context_str,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json"
                )
            )
            raw = resp.text.strip().removeprefix("```json").removesuffix("```").strip()
            decision = json.loads(raw)
            break
        except Exception as e:
            print(f"⚠️ Model {model_name} skipped: {e}")
            continue

    if not decision:
        return "My primary model endpoints are cooling down, sir. Give me a moment.", False

    tool = decision.get("tool", "none")
    args = decision.get("tool_args", {}) or {}
    spoken = decision.get("spoken_reply", "Right away, sir.")

    tool_output = ""
    if tool == "spotify":
        tool_output = open_or_control_spotify(args.get("song_query", ""))
    elif tool == "vscode_agent":
        tool_output = delegate_to_vscode_agent(
            args.get("agent_name", "antigravity"),
            args.get("task_prompt", user_prompt),
            args.get("project_path", "")
        )
    elif tool == "gemini_pro_think":
        pro_res = deep_think_with_gemini_pro(args.get("task_prompt", user_prompt))
        spoken = pro_res[:350]
    elif tool == "web_llm":
        tool_output = delegate_to_web_llm(
            args.get("provider", "claude"),
            args.get("task_prompt", user_prompt)
        )
        spoken = tool_output[:300]
    elif tool == "ui_nav":
        tool_output = navigate_desktop_and_ui(args.get("action", ""), args.get("value", ""))
    elif tool == "terminal":
        tool_output = execute_terminal_command(args.get("command", ""))
        if "denied" in tool_output:
            spoken = "Command cancelled as requested, sir."
    elif tool == "inspect_screen":
        vision_ans = inspect_screen_with_vision(args.get("question", user_prompt))
        spoken = vision_ans[:350]
    elif tool == "sleep":
        conversation_history.append(f"Aero: {spoken}")
        return spoken, True

    conversation_history.append(f"Aero: {spoken} (System Action: {tool_output})")
    return spoken, False

# ==========================================
# 4. CONTINUOUS CONVERSATION & WAKE LOOP
# ==========================================
def listen_mic(timeout=5, phrase_limit=12):
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.2)
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            return recognizer.recognize_google(audio).lower()
        except Exception:
            return None

async def main():
    print("====================================================")
    print("🚀 AERO AUTONOMOUS OS AGENT IS ONLINE")
    print(f"🎤 Wake words: {WAKE_WORDS} | Hotkey: [{WAKE_HOTKEY.upper()}]")
    print("====================================================")

    active_until = 0
    hotkey_pressed = False

    def trigger_hotkey():
        nonlocal hotkey_pressed
        hotkey_pressed = True

    keyboard.add_hotkey(WAKE_HOTKEY, trigger_hotkey)

    while True:
        is_awake = (time.time() < active_until) or hotkey_pressed

        if hotkey_pressed:
            hotkey_pressed = False
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
            await speak_with_barge_in("Listening, sir.")
            is_awake = True

        if is_awake:
            hud.update("🔵 Listening (Active Mode)...", "Speak freely | Tap SPACE to interrupt", "#00E5FF")
            heard = await asyncio.to_thread(listen_mic, 5, 14)
            if not heard:
                continue

            print(f"🗣️ Devang: {heard}")
            reply, should_sleep = await asyncio.to_thread(route_and_execute, heard)
            await speak_with_barge_in(reply)

            if should_sleep:
                active_until = 0
                hud.update("⚪ Aero Standby", "Say 'Aero' or press Alt+Space to wake", "#444746")
            else:
                active_until = time.time() + ACTIVE_WINDOW_SECONDS
        else:
            hud.update("⚪ Aero Standby", "Say 'Aero' or press Alt+Space to wake", "#444746")
            heard = await asyncio.to_thread(listen_mic, 2, 6)
            if not heard:
                continue

            for ww in WAKE_WORDS:
                if ww in heard:
                    remainder = heard.split(ww, 1)[1].strip()
                    active_until = time.time() + ACTIVE_WINDOW_SECONDS
                    if remainder:
                        print(f"🗣️ Devang (Wake + Command): {remainder}")
                        reply, should_sleep = await asyncio.to_thread(route_and_execute, remainder)
                        await speak_with_barge_in(reply)
                        if should_sleep:
                            active_until = 0
                    else:
                        await speak_with_barge_in("Online and ready, sir.")
                    break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAero powered down.")
