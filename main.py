import os
import sys
import time
import ctypes
import asyncio
import threading
import subprocess
import webbrowser
from datetime import datetime
import speech_recognition as sr
import edge_tts
import pygame
import keyboard
import pygetwindow as gw

from config import BASE_DIR, WAKE_WORDS, WAKE_HOTKEY, ACTIVE_WINDOW_SECONDS, SERVER_PORT, CREATE_NO_WINDOW
from server import run_server, app_state
from orchestrator import orchestrate_mission

log_stream = open(os.path.join(BASE_DIR, "aero_runtime.log"), "a", encoding="utf-8", buffering=1)
if sys.stdout is None or "pythonw" in sys.executable.lower():
    sys.stdout = log_stream
if sys.stderr is None or "pythonw" in sys.executable.lower():
    sys.stderr = log_stream

recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True
pygame.mixer.init()

# Thread-safe wake signal (Fixes the previous globals() scope bug!)
wake_event = threading.Event()

def log_bus(agent: str, text: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"<span class='log-ts'>[{ts}]</span> <span class='log-ag'>[{agent}]</span> {text}"
    print(f"[{ts}] [{agent}] {text}")
    app_state["logs"].append(line)
    if len(app_state["logs"]) > 60:
        app_state["logs"].pop(0)

def set_agent_state(agent: str, status: str, task: str, color: str = "#00f0ff"):
    if agent in app_state["agents"]:
        app_state["agents"][agent] = {"status": status, "task": str(task)[:48], "color": color}

def launch_or_focus_hud_window():
    """Launches or focuses the Sci-Fi HUD in frameless Native App Mode (--app) via Edge or Brave."""
    for win in gw.getAllWindows():
        if win.title and "AERO OS // NEURAL COMMAND DECK" in win.title:
            try:
                if win.isMinimized:
                    win.restore()
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                win.activate()
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                return
            except Exception:
                pass

    url = f"http://127.0.0.1:{SERVER_PORT}"
    # Launch as a sleek standalone chromeless desktop window using Edge or Brave --app mode
    browser_paths = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    ]
    for bp in browser_paths:
        if os.path.exists(bp):
            subprocess.Popen([bp, f"--app={url}", "--window-size=480,760", "--window-position=1400,40"], creationflags=CREATE_NO_WINDOW)
            return
    webbrowser.open(url)

async def speak(text: str):
    if not text:
        return
    clean = text.replace("*", "").replace("#", "").replace("`", "").strip()
    log_bus("AERO", clean)
    set_agent_state("AERO", "SPEAKING", clean[:42], "#c800ff")
    out_file = os.path.join(BASE_DIR, "tts.mp3")
    try:
        comm = edge_tts.Communicate(clean, "en-US-ChristopherNeural", rate="+28%")
        await comm.save(out_file)
        pygame.mixer.music.load(out_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if keyboard.is_pressed("space") or wake_event.is_set():
                pygame.mixer.music.stop()
                break
            await asyncio.sleep(0.03)
        pygame.mixer.music.unload()
    except Exception as e:
        print(f"TTS Error: {e}")
    set_agent_state("AERO", "ONLINE", "Standing by", "#00f0ff")
    try:
        os.remove(out_file)
    except Exception:
        pass

def listen_mic(timeout=3, phrase_time_limit=12):
    """Fixed parameter name: phrase_time_limit instead of phrase_limit!"""
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.2)
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            return recognizer.recognize_google(audio).lower()
        except Exception:
            return None

def on_hotkey_pressed():
    wake_event.set()
    threading.Thread(target=launch_or_focus_hud_window, daemon=True).start()

async def main():
    threading.Thread(target=run_server, daemon=True).start()
    await asyncio.sleep(1.2)
    launch_or_focus_hud_window()

    try:
        keyboard.add_hotkey(WAKE_HOTKEY, on_hotkey_pressed)
    except Exception as e:
        log_bus("SYSTEM", f"Hotkey note: {e}")

    log_bus("AERO", f"Sci-Fi Command Deck Ready. Press [{WAKE_HOTKEY.upper()}] or click Reactor Core.")
    active_until = 0

    while True:
        await asyncio.sleep(0.05)

        # 1. Check if user clicked the Reactor Core in the UI
        if app_state.get("wake_requested"):
            app_state["wake_requested"] = False
            wake_event.set()

        # 2. Check if user typed a command in the UI
        if app_state.get("pending_command"):
            cmd = app_state["pending_command"]
            app_state["pending_command"] = None
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
            rep = await orchestrate_mission(cmd, set_agent_state, log_bus, launch_or_focus_hud_window)
            await speak(rep)
            continue

        # 3. Check if Shift+Alt+Space or Reactor Core was triggered
        if wake_event.is_set():
            wake_event.clear()
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
            await speak("Aero online. Go ahead, sir.")

        is_awake = time.time() < active_until

        if is_awake:
            set_agent_state("AERO", "LISTENING", "Speak freely (Active Mode)", "#00ff9d")
            heard = await asyncio.to_thread(listen_mic, 4, 14)
            if not heard:
                continue
            if any(w in heard for w in ("go to sleep", "standby", "stop listening")):
                active_until = 0
                await speak("Entering standby mode, sir.")
                set_agent_state("AERO", "STANDBY", "Press Shift+Alt+Space to wake", "#64748b")
                continue

            rep = await orchestrate_mission(heard, set_agent_state, log_bus, launch_or_focus_hud_window)
            await speak(rep)
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
        else:
            set_agent_state("AERO", "STANDBY", "Say 'Aero' or press Shift+Alt+Space", "#00f0ff")
            heard = await asyncio.to_thread(listen_mic, 2, 5)
            if not heard:
                continue
            for ww in WAKE_WORDS:
                if ww in heard:
                    rem = heard.split(ww, 1)[1].strip()
                    active_until = time.time() + ACTIVE_WINDOW_SECONDS
                    launch_or_focus_hud_window()
                    if rem:
                        rep = await orchestrate_mission(rem, set_agent_state, log_bus, launch_or_focus_hud_window)
                        await speak(rep)
                    else:
                        await speak("Online, sir. What's the directive?")
                    break

if __name__ == "__main__":
    asyncio.run(main())
