import os
import sys
import time
import ctypes
import asyncio
import threading
import subprocess
import webbrowser
import tempfile
from datetime import datetime
import speech_recognition as sr
import edge_tts
import pygame
import pyautogui
import pygetwindow as gw

from config import BASE_DIR, WAKE_WORDS, ACTIVE_WINDOW_SECONDS, SERVER_PORT, CREATE_NO_WINDOW
from server import run_server, app_state, kill_aero_completely
from orchestrator import orchestrate_mission
from plugins.token_router import check_omniroute_health

log_stream = open(os.path.join(BASE_DIR, "aero_runtime.log"), "a", encoding="utf-8", buffering=1)
if sys.stdout is None or "pythonw" in sys.executable.lower(): sys.stdout = log_stream
if sys.stderr is None or "pythonw" in sys.executable.lower(): sys.stderr = log_stream

recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True
pygame.mixer.init()

wake_event = threading.Event()
is_speaking_lock = threading.Event()

def log_bus(agent: str, text: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [{agent}] {text}"
    print(line)
    app_state["logs"].append(line)
    if len(app_state["logs"]) > 50: app_state["logs"].pop(0)

def set_agent_state(agent: str, status: str, task: str, color: str = "#00f0ff"):
    if agent in app_state["agents"]:
        app_state["agents"][agent] = {"status": status, "task": str(task)[:48], "color": color}

def set_ui_mode(mode: str):
    app_state["active_mode"] = mode

def launch_or_focus_hud_window():
    """Calculates EXACT CENTER of the screen and docks the frameless UI there."""
    app_state["active_mode"] = "normal"
    sw, sh = pyautogui.size()
    win_w, win_h = 440, 520
    # Perfect Center Coordinates
    pos_x = int((sw - win_w) / 2)
    pos_y = int((sh - win_h) / 2)

    for win in gw.getAllWindows():
        if win.title and "AERO OS // COMMAND DECK" in win.title.upper():
            try:
                hwnd = win._hWnd
                if win.isMinimized: ctypes.windll.user32.ShowWindow(hwnd, 9)
                else: ctypes.windll.user32.ShowWindow(hwnd, 5)
                win.moveTo(pos_x, pos_y)
                win.resizeTo(win_w, win_h)
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                return
            except Exception: pass

    url = f"http://127.0.0.1:{SERVER_PORT}"
    browser_paths = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    # Uses isolated Temp folder so Git never breaks!
    profile_dir = os.path.join(tempfile.gettempdir(), "aero_hud_profile")
    
    for bp in browser_paths:
        if os.path.exists(bp):
            subprocess.Popen(
                [bp, f"--app={url}", f"--user-data-dir={profile_dir}", f"--window-size={win_w},{win_h}", f"--window-position={pos_x},{pos_y}"],
                creationflags=CREATE_NO_WINDOW
            )
            return
    webbrowser.open(url)

def win32_hardware_hotkey_poller():
    """Polls for [Shift+Alt+Space] to Wake and [Shift+Alt+Q] to Kill."""
    VK_SHIFT = 0x10
    VK_MENU = 0x12
    VK_SPACE = 0x20
    VK_Q = 0x51
    last_trig = 0.0
    while True:
        try:
            shift_down = bool(ctypes.windll.user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
            alt_down   = bool(ctypes.windll.user32.GetAsyncKeyState(VK_MENU) & 0x8000)
            space_down = bool(ctypes.windll.user32.GetAsyncKeyState(VK_SPACE) & 0x8000)
            q_down     = bool(ctypes.windll.user32.GetAsyncKeyState(VK_Q) & 0x8000)
            
            # THE HARDWARE KILL SWITCH
            if shift_down and alt_down and q_down:
                kill_aero_completely()

            if shift_down and alt_down and space_down:
                now = time.time()
                if now - last_trig > 1.2:
                    last_trig = now
                    wake_event.set()
                    threading.Thread(target=launch_or_focus_hud_window, daemon=True).start()
        except Exception:
            pass
        time.sleep(0.025)

async def speak(text: str):
    if not text: return
    is_speaking_lock.set()
    clean = text.replace("*", "").replace("#", "").replace("`", "").strip()
    log_bus("AERO", clean)
    set_agent_state("AERO", "SPEAKING", clean[:42], "#c800ff")
    out_file = os.path.join(BASE_DIR, f"tts_{int(time.time()*1000)}.mp3")
    try:
        comm = edge_tts.Communicate(clean, "en-US-ChristopherNeural", rate="+28%")
        await comm.save(out_file)
        pygame.mixer.music.load(out_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if wake_event.is_set():
                pygame.mixer.music.stop()
                break
            await asyncio.sleep(0.03)
        pygame.mixer.music.unload()
    except Exception: pass
    finally:
        set_agent_state("AERO", "ONLINE", "Standing by", "#00f0ff")
        try:
            if os.path.exists(out_file): os.remove(out_file)
        except Exception: pass
        await asyncio.sleep(0.35)
        is_speaking_lock.clear()

def listen_mic(timeout=2, phrase_time_limit=10):
    if is_speaking_lock.is_set() or wake_event.is_set(): return None
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.15)
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            if is_speaking_lock.is_set(): return None
            return recognizer.recognize_google(audio).lower()
        except Exception: return None

async def main():
    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=win32_hardware_hotkey_poller, daemon=True).start()
    await asyncio.sleep(0.8)
    launch_or_focus_hud_window()
    threading.Thread(target=check_omniroute_health, daemon=True).start()

    active_until = 0
    while True:
        await asyncio.sleep(0.04)

        if app_state.get("shutdown_requested"):
            await speak("Powering down completely, sir.")
            kill_aero_completely()

        if app_state.get("wake_requested"):
            app_state["wake_requested"] = False
            wake_event.set()

        if wake_event.is_set():
            wake_event.clear()
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
            set_ui_mode("normal")
            await speak("Aero online. Go ahead, sir.")
            continue

        if app_state.get("pending_command"):
            cmd = app_state["pending_command"]
            app_state["pending_command"] = None
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
            rep = await orchestrate_mission(cmd, set_agent_state, log_bus, launch_or_focus_hud_window, None, set_ui_mode)
            await speak(rep)
            continue

        is_awake = time.time() < active_until

        if is_awake:
            set_agent_state("AERO", "LISTENING", "Listening (Shift+Alt+Space)", "#00ff9d")
            heard = await asyncio.to_thread(listen_mic, 2, 12)
            if wake_event.is_set() or not heard: continue
            
            if any(w in heard for w in ("shutdown aero", "shut down aero", "exit aero", "kill aero", "terminate aero")):
                await speak("Powering down completely, sir.")
                kill_aero_completely()

            if any(w in heard for w in ("go to sleep", "standby", "stop listening")):
                active_until = 0
                set_ui_mode("transparent")
                await speak("Entering standby mode, sir.")
                set_agent_state("AERO", "STANDBY", "Press Shift+Alt+Space to wake", "#64748b")
                continue

            rep = await orchestrate_mission(heard, set_agent_state, log_bus, launch_or_focus_hud_window, None, set_ui_mode)
            await speak(rep)
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
        else:
            set_agent_state("AERO", "STANDBY", "Press Shift+Alt+Space to wake", "#00f0ff")
            heard = await asyncio.to_thread(listen_mic, 1.5, 4)
            if wake_event.is_set() or not heard: continue
            for ww in WAKE_WORDS:
                if ww in heard:
                    rem = heard.split(ww, 1)[1].strip()
                    active_until = time.time() + ACTIVE_WINDOW_SECONDS
                    launch_or_focus_hud_window()
                    if rem:
                        rep = await orchestrate_mission(rem, set_agent_state, log_bus, launch_or_focus_hud_window, None, set_ui_mode)
                        await speak(rep)
                    else:
                        await speak("Online, sir. What's the directive?")
                    break

if __name__ == "__main__":
    asyncio.run(main())
