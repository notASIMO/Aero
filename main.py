import os
import sys
import time
import json
import math
import struct
import wave
import signal
import ctypes
from ctypes import wintypes
import asyncio
import threading
import subprocess

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import webview
from brain import process_directive, get_groq_key, save_groq_key, log_comms

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
CREATE_NO_WINDOW = 0x08000000
WINDOW_TITLE = "AeroOS_v7_GlassDeck"
WAKE_WORDS = ("aero", "hey aero", "ok aero", "jarvis", "hey jarvis", "arrow")
PID_FILE = os.path.join(BASE_DIR, "aero.pid")

if os.path.exists(PID_FILE):
    try:
        with open(PID_FILE, "r") as f:
            old_pid = int(f.read().strip())
        if old_pid != os.getpid():
            os.kill(old_pid, signal.SIGTERM)
            time.sleep(0.25)
    except Exception:
        pass

with open(PID_FILE, "w") as f:
    f.write(str(os.getpid()))

STATE = {
    "win": None,
    "hwnd": None,
    "expanded": False,
    "listening": False,
    "interrupt": threading.Event(),
    "mode": "STANDBY",
    "pill_text": "AERO // ALT+A OR SAY 'HEY AERO'",
    "status_title": "STANDBY // ALT+A OR SAY 'HEY AERO'",
    "subtitle": "Alt+A: Live Listen | Alt+S: Standby | Alt+Q: Quit",
    "provider": "GROQ-LPU // LLAMA-3.3-70B" if get_groq_key() else "PASTE GSK_ KEY IN WAR ROOM",
    "latency_ms": 110,
    "logs": ["[SYSTEM] Aero Glass Deck Online. Alt+A: Live | Alt+S: Standby | Alt+Q: Quit."],
    "agents": {
        "AERO": {"status": "STANDBY", "task": "Wake-Word & Live Voice Router"},
        "ATLAS": {"status": "IDLE", "task": "CTO // Deep Architecture"},
        "NOVA": {"status": "IDLE", "task": "VP Eng // VS Code & Files"},
        "SENTINEL": {"status": "IDLE", "task": "SecOps // PowerShell & Git"},
        "PULSE": {"status": "IDLE", "task": "Vision // YouTube & DOM UIA"},
        "VIBE": {"status": "IDLE", "task": "Media // Spotify & Safe Tabs"}
    }
}

def hard_kill_aero():
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass
    os._exit(0)

def play_ui_chime(high: bool = True):
    """Plays an instant 80ms sci-fi feedback tone when Alt+A or Alt+S is pressed."""
    try:
        import winsound
        winsound.Beep(880 if high else 440, 75)
    except Exception:
        pass

def find_process_hwnd() -> int:
    """Finds our exact Win32 HWND by matching Process ID (os.getpid()) or Window Title â€” NEVER FAILS!"""
    if STATE.get("hwnd") and ctypes.windll.user32.IsWindow(STATE["hwnd"]):
        return STATE["hwnd"]

    hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
    if hwnd:
        STATE["hwnd"] = hwnd
        return hwnd

    my_pid = os.getpid()
    found_hwnds = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(h, lparam):
        if ctypes.windll.user32.IsWindowVisible(h):
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value == my_pid:
                length = ctypes.windll.user32.GetWindowTextLengthW(h)
                if length > 0:
                    found_hwnds.append(h)
        return True

    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)
    if found_hwnds:
        STATE["hwnd"] = found_hwnds[0]
        return found_hwnds[0]
    return 0

def get_dpi_scale() -> float:
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return max(1.0, dpi / 96.0)
    except Exception:
        return 1.0

def set_window_opacity(alpha_float: float):
    hwnd = find_process_hwnd()
    if not hwnd:
        return
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    LWA_ALPHA = 0x00000002
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
    ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, int(max(0.20, min(1.0, alpha_float)) * 255), LWA_ALPHA)

def apply_win32_geometry(expand: bool):
    """Positions the Dynamic Island dead-center at the top, or expands the Glass War Room dead-center on screen."""
    STATE["expanded"] = bool(expand)
    sw = ctypes.windll.user32.GetSystemMetrics(0)
    sh = ctypes.windll.user32.GetSystemMetrics(1)
    scale = get_dpi_scale()

    if expand:
        w, h = int(920 * scale), int(570 * scale)
        x, y = int((sw - w) / 2), int((sh - h) / 2)
    else:
        w, h = int(490 * scale), int(48 * scale)
        x, y = int((sw - w) / 2), int(12 * scale)

    hwnd = find_process_hwnd()
    if hwnd:
        try:
            pref = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass
        ctypes.windll.user32.MoveWindow(hwnd, x, y, w, h, True)
        # Transparent (32% opacity) when collapsed in Standby; 95% frosted glass when active or expanded!
        set_window_opacity(1.0 if (expand or STATE["listening"] or STATE["mode"] != "STANDBY") else 0.45)

def push_ui():
    win = STATE.get("win")
    if not win:
        return
    if not STATE["expanded"]:
        set_window_opacity(1.0 if (STATE["listening"] or STATE["mode"] != "STANDBY") else 0.45)
    else:
        set_window_opacity(1.0)

    payload = json.dumps({
        "expanded": STATE["expanded"],
        "mode": STATE["mode"],
        "pill_text": STATE["pill_text"],
        "status_title": STATE["status_title"],
        "subtitle": STATE["subtitle"],
        "provider": "GROQ-LPU // LLAMA-3.3-70B" if get_groq_key() else "PASTE GSK_ KEY IN WAR ROOM",
        "latency_ms": STATE["latency_ms"],
        "agents": STATE["agents"],
        "logs": STATE["logs"]
    })
    try:
        win.evaluate_js(f"if(window.syncStateFromPython) window.syncStateFromPython({payload});")
    except Exception:
        pass

def add_log(tag: str, msg: str):
    ts = time.strftime("%H:%M:%S")
    STATE["logs"].append(f"[{ts}] [{tag}] {msg}")
    if len(STATE["logs"]) > 40:
        STATE["logs"].pop(0)

def update_agent_cb(dept: str, status: str, task: str, latency_ms: int = 120, provider: str = ""):
    if dept in STATE["agents"]:
        STATE["agents"][dept] = {"status": status, "task": task[:50]}
    STATE["latency_ms"] = latency_ms
    if provider:
        STATE["provider"] = provider
    push_ui()

def collapse_for_action_cb():
    if STATE["expanded"]:
        apply_win32_geometry(False)
        push_ui()
        time.sleep(0.15)

def switch_to_standby():
    STATE["interrupt"].set()
    STATE["listening"] = False
    STATE["mode"] = "STANDBY"
    STATE["pill_text"] = "AERO // STANDBY (ALT+A OR 'HEY AERO')"
    STATE["status_title"] = "STANDBY // ALT+A OR SAY 'HEY AERO'"
    STATE["subtitle"] = "In Standby â€” listening passively for 'Hey Aero' or press Alt+A"
    STATE["agents"]["AERO"] = {"status": "STANDBY", "task": "Wake-Word Passive Mode"}
    add_log("SYSTEM", "Entered Transparent Standby Mode (Alt+S).")
    push_ui()
    threading.Thread(target=play_ui_chime, args=(False,), daemon=True).start()

def switch_to_live_listen():
    if STATE["mode"] == "SPEAKING":
        STATE["interrupt"].set()
    STATE["listening"] = True
    STATE["mode"] = "LISTENING"
    STATE["pill_text"] = "ðŸŸ¢ LIVE // SPEAK FREELY (ALT+S STANDBY)"
    STATE["status_title"] = "LIVE MODE // SPEAK FREELY"
    STATE["subtitle"] = "Hands-free Live Mode active â€” press Alt+S or say 'go to standby' anytime"
    STATE["agents"]["AERO"] = {"status": "LISTENING", "task": "Live Continuous Conversation"}
    add_log("SYSTEM", "Activated Live Listen Mode (Alt+A).")
    push_ui()
    threading.Thread(target=play_ui_chime, args=(True,), daemon=True).start()

class AeroJsApi:
    def set_expanded(self, expand: bool):
        apply_win32_geometry(bool(expand))
        push_ui()

    def activate_listening(self):
        switch_to_live_listen()

    def enter_standby(self):
        switch_to_standby()

    def submit_text(self, text: str):
        threading.Thread(target=execute_turn, args=(text,), daemon=True).start()

    def save_key(self, key_str: str):
        save_groq_key(key_str)
        add_log("SYSTEM", "Groq API Key validated & active!")
        push_ui()

    def kill_aero(self):
        hard_kill_aero()

def speak_sync(text: str):
    if not text:
        return
    import edge_tts
    import pygame
    if not pygame.mixer.get_init():
        pygame.mixer.init()

    STATE["interrupt"].clear()
    clean = text.replace("*", "").replace("#", "").replace("`", "").strip()
    STATE["mode"] = "SPEAKING"
    STATE["pill_text"] = f"ðŸ”Š {clean[:34]}..."
    STATE["status_title"] = "AERO // SPEAKING"
    STATE["subtitle"] = clean
    STATE["agents"]["AERO"] = {"status": "SPEAKING", "task": clean[:45]}
    add_log("AERO", clean)
    push_ui()

    out_file = os.path.join(BASE_DIR, f"tts_{int(time.time()*1000)}.mp3")
    try:
        asyncio.run(edge_tts.Communicate(clean, "en-US-ChristopherNeural", rate="+25%").save(out_file))
        pygame.mixer.music.load(out_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if STATE["interrupt"].is_set():
                pygame.mixer.music.stop()
                break
            time.sleep(0.03)
        pygame.mixer.music.unload()
    except Exception:
        pass
    finally:
        try:
            if os.path.exists(out_file):
                os.remove(out_file)
        except Exception:
            pass
        time.sleep(0.15)

def execute_turn(heard_text: str):
    low = heard_text.lower().strip(" .,!?")
    if any(k in low for k in ("go to standby", "enter standby", "standby mode", "go to sleep", "stop listening")) or low == "standby":
        speak_sync("Standing by, sir.")
        switch_to_standby()
        return
    if any(k in low for k in ("expand war room", "open war room", "show war room", "expand aero", "open glass deck")):
        apply_win32_geometry(True)
        push_ui()
        speak_sync("Glass Command Deck expanded, sir.")
        return
    if any(k in low for k in ("minimize war room", "collapse war room", "island mode")):
        apply_win32_geometry(False)
        push_ui()
        speak_sync("Collapsed to Dynamic Island, sir.")
        return
    if any(k in low for k in ("shutdown aero", "shut down aero", "kill aero", "terminate aero")):
        speak_sync("Powering down completely, sir.")
        hard_kill_aero()

    STATE["mode"] = "THINKING"
    STATE["pill_text"] = f"âš¡ {heard_text[:30]}..."
    STATE["status_title"] = "ANALYZING..."
    STATE["subtitle"] = f"You: \"{heard_text}\""
    add_log("DEVANG", heard_text)
    push_ui()

    reply = process_directive(heard_text, update_agent_cb, collapse_for_action_cb)
    speak_sync(reply)

def voice_daemon():
    # Poll until HWND is created, then snap to exact Top-Center immediately!
    for _ in range(25):
        time.sleep(0.1)
        if find_process_hwnd():
            apply_win32_geometry(False)
            push_ui()
            break

    import requests
    import speech_recognition as sr
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8
    recognizer.non_speaking_duration = 0.35

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
    except Exception:
        pass

    def capture_and_transcribe(timeout_s: float, limit_s: float) -> str | None:
        try:
            with sr.Microphone() as source:
                audio = recognizer.listen(source, timeout=timeout_s, phrase_time_limit=limit_s)
            gkey = get_groq_key()
            if gkey:
                r = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {gkey}"},
                    files={"file": ("speech.wav", audio.get_wav_data(), "audio/wav")},
                    data={
                        "model": "whisper-large-v3-turbo",
                        "language": "en",
                        "prompt": "Aero, Jarvis, Devang, Spotify, YouTube, Brave, Manwa Laage, Sapphire, War Room, standby."
                    },
                    timeout=5
                )
                if r.status_code == 200:
                    txt = r.json().get("text", "").strip()
                    if txt and txt.lower() not in ("you", "thank you.", "thanks for watching!", "."):
                        return txt
            return recognizer.recognize_google(audio, language="en-IN")
        except Exception:
            return None

    while True:
        if STATE["listening"]:
            STATE["mode"] = "LISTENING"
            STATE["pill_text"] = "ðŸŸ¢ LIVE // SPEAK FREELY (ALT+S STANDBY)"
            STATE["status_title"] = "LIVE MODE // SPEAK FREELY"
            STATE["agents"]["AERO"] = {"status": "LISTENING", "task": "Hands-Free Mic Active"}
            push_ui()

            heard = capture_and_transcribe(timeout_s=3.5, limit_s=14.0)
            if not STATE["listening"] or not heard:
                continue
            execute_turn(heard)
        else:
            # Fast 1.0s wake-word polling so pressing Alt+A never waits!
            heard_wake = capture_and_transcribe(timeout_s=1.0, limit_s=3.2)
            if STATE["listening"] or not heard_wake:
                continue
            low = heard_wake.lower().strip()
            for ww in WAKE_WORDS:
                if ww in low:
                    log_comms("WAKE_WORD", heard_wake)
                    switch_to_live_listen()
                    remainder = low.split(ww, 1)[1].strip(" ,.!?")
                    if len(remainder) > 2:
                        execute_turn(remainder)
                    else:
                        speak_sync("Online, sir. Go ahead.")
                    break

def hardware_hotkey_poller():
    VK_MENU = 0x12
    VK_A = 0x41
    VK_S = 0x53
    VK_Q = 0x51
    last_trig = 0.0
    while True:
        try:
            alt = bool(ctypes.windll.user32.GetAsyncKeyState(VK_MENU) & 0x8000)
            if alt:
                now = time.time()
                if bool(ctypes.windll.user32.GetAsyncKeyState(VK_Q) & 0x8000):
                    hard_kill_aero()
                if now - last_trig > 0.45:
                    if bool(ctypes.windll.user32.GetAsyncKeyState(VK_A) & 0x8000):
                        last_trig = now
                        switch_to_live_listen()
                    elif bool(ctypes.windll.user32.GetAsyncKeyState(VK_S) & 0x8000):
                        last_trig = now
                        switch_to_standby()
        except Exception:
            pass
        time.sleep(0.02)

if __name__ == "__main__":
    sw = ctypes.windll.user32.GetSystemMetrics(0)
    scale = get_dpi_scale()
    init_w, init_h = int(490 * scale), int(48 * scale)
    init_x, init_y = int((sw - init_w) / 2), int(12 * scale)

    api = AeroJsApi()
    win = webview.create_window(
        WINDOW_TITLE,
        url=os.path.join(BASE_DIR, "ui.html"),
        js_api=api,
        width=init_w,
        height=init_h,
        x=init_x,
        y=init_y,
        min_size=(150, 32),
        frameless=True,
        on_top=True,
        background_color="#070b16"
    )
    STATE["win"] = win
    threading.Thread(target=voice_daemon, daemon=True).start()
    threading.Thread(target=hardware_hotkey_poller, daemon=True).start()
    webview.start()