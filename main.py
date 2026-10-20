import os
import sys
import time
import asyncio
import threading
import webbrowser
from datetime import datetime
import speech_recognition as sr
import edge_tts
import pygame
import keyboard

from config import BASE_DIR, WAKE_WORDS, WAKE_HOTKEY, ACTIVE_WINDOW_SECONDS
from server import run_server, app_state
from orchestrator import orchestrate_mission

log_stream = open(os.path.join(BASE_DIR, "aero_runtime.log"), "a", encoding="utf-8", buffering=1)
if sys.stdout is None or "pythonw" in sys.executable.lower(): sys.stdout = log_stream
if sys.stderr is None or "pythonw" in sys.executable.lower(): sys.stderr = log_stream

recognizer = sr.Recognizer()
pygame.mixer.init()

def log_bus(agent, text):
    ts = datetime.now().strftime("%H:%M:%S")
    app_state["logs"].append(f"[{ts}] [{agent}] {text}")
    if len(app_state["logs"]) > 50: app_state["logs"].pop(0)

def set_agent_state(agent, status, task, color="#00E5FF"):
    if agent in app_state["agents"]:
        app_state["agents"][agent] = {"status": status, "task": task, "color": color}

async def speak(text):
    if not text: return
    clean = text.replace("*", "").replace("#", "").replace("`", "").strip()
    log_bus("AERO", clean)
    set_agent_state("AERO", "SPEAKING", clean[:30], "#D500F9")
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
    set_agent_state("AERO", "ONLINE", "Ready", "#00E5FF")
    try: os.remove(out_file)
    except: pass

def listen_mic():
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.2)
        try:
            audio = recognizer.listen(source, timeout=3, phrase_limit=12)
            return recognizer.recognize_google(audio).lower()
        except: return None

async def main():
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(1.0)
    webbrowser.open("[http://127.0.0.1:8765](http://127.0.0.1:8765)")

    hotkey_triggered = False
    keyboard.add_hotkey(WAKE_HOTKEY, lambda: globals().update({'hotkey_triggered': True}))
    log_bus("AERO", f"Modular daemon active. Press {WAKE_HOTKEY.upper()} or use War Room web UI.")

    active_until = 0

    while True:
        await asyncio.sleep(0.05)
        if app_state["pending_command"]:
            cmd = app_state["pending_command"]
            app_state["pending_command"] = None
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
            rep = await orchestrate_mission(cmd, set_agent_state, log_bus, lambda: webbrowser.open("[http://127.0.0.1:8765](http://127.0.0.1:8765)"))
            await speak(rep)
            continue

        is_awake = (time.time() < active_until) or hotkey_triggered
        if hotkey_triggered:
            hotkey_triggered = False
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
            await speak("Aero live online. Go ahead, sir.")
            is_awake = True

        if is_awake:
            set_agent_state("AERO", "LISTENING", "Active Mode", "#00E5FF")
            heard = await asyncio.to_thread(listen_mic)
            if not heard: continue
            rep = await orchestrate_mission(heard, set_agent_state, log_bus, lambda: webbrowser.open("[http://127.0.0.1:8765](http://127.0.0.1:8765)"))
            await speak(rep)
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
        else:
            set_agent_state("AERO", "STANDBY", "Sleeping", "#444746")
            heard = await asyncio.to_thread(listen_mic)
            if not heard: continue
            for ww in WAKE_WORDS:
                if ww in heard:
                    rem = heard.split(ww, 1)[1].strip()
                    active_until = time.time() + ACTIVE_WINDOW_SECONDS
                    if rem:
                        rep = await orchestrate_mission(rem, set_agent_state, log_bus, lambda: webbrowser.open("[http://127.0.0.1:8765](http://127.0.0.1:8765)"))
                        await speak(rep)
                    else:
                        await speak("Online. What's your directive?")
                    break

if __name__ == "__main__":
    asyncio.run(main())
