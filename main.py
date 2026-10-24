import os, sys, time, ctypes, asyncio, threading, subprocess, webbrowser, tempfile
from datetime import datetime
import speech_recognition as sr
import edge_tts, pygame, pyautogui
import pygetwindow as gw

from config import BASE_DIR, WAKE_WORDS, ACTIVE_WINDOW_SECONDS, SERVER_PORT, CREATE_NO_WINDOW
from server import run_server, app_state, kill_aero_completely
from orchestrator import orchestrate_mission
from plugins.token_router import check_omniroute_health

log_stream = open(os.path.join(BASE_DIR, "aero_runtime.log"), "a", encoding="utf-8", buffering=1)
if sys.stdout is None or "pythonw" in sys.executable.lower(): sys.stdout = log_stream
if sys.stderr is None or "pythonw" in sys.executable.lower(): sys.stderr = log_stream

recognizer = sr.Recognizer(); recognizer.dynamic_energy_threshold = True; pygame.mixer.init()
wake_event = threading.Event(); is_speaking_lock = threading.Event()

def log_bus(agent: str, text: str):
    ts = datetime.now().strftime("%H:%M:%S")
    app_state["logs"].append(f"[{ts}] [{agent}] {text}")
    if len(app_state["logs"]) > 50: app_state["logs"].pop(0)

def set_agent_state(agent: str, status: str, task: str, color: str = "#00f0ff"):
    if agent in app_state["agents"]: app_state["agents"][agent] = {"status": status, "task": str(task)[:48], "color": color}

def set_ui_mode(mode: str): app_state["active_mode"] = mode

def launch_or_focus_hud_window():
    app_state["active_mode"] = "normal"
    sw, sh = pyautogui.size()
    win_w, win_h = 440, 520
    pos_x, pos_y = int((sw - win_w) / 2), int((sh - win_h) / 2) # PERFECTLY CENTERED

    for win in gw.getAllWindows():
        if win.title and "AERO OS // COMMAND DECK" in win.title.upper():
            try:
                hwnd = win._hWnd
                ctypes.windll.user32.ShowWindow(hwnd, 9 if win.isMinimized else 5)
                win.moveTo(pos_x, pos_y); win.resizeTo(win_w, win_h)
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0); ctypes.windll.user32.SetForegroundWindow(hwnd); ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                return
            except Exception: pass

    url = f"http://127.0.0.1:{SERVER_PORT}"
    browser_paths = [r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    profile_dir = os.path.join(tempfile.gettempdir(), "aero_hud_profile")
    for bp in browser_paths:
        if os.path.exists(bp):
            subprocess.Popen([bp, f"--app={url}", f"--user-data-dir={profile_dir}", f"--window-size={win_w},{win_h}", f"--window-position={pos_x},{pos_y}"], creationflags=CREATE_NO_WINDOW)
            return
    webbrowser.open(url)

def win32_hardware_hotkey_poller():
    VK_MENU, VK_SPACE, VK_Q = 0x12, 0x20, 0x51
    last_trig = 0.0
    while True:
        try:
            alt_down = bool(ctypes.windll.user32.GetAsyncKeyState(VK_MENU) & 0x8000)
            if alt_down and bool(ctypes.windll.user32.GetAsyncKeyState(VK_Q) & 0x8000): kill_aero_completely()
            if alt_down and bool(ctypes.windll.user32.GetAsyncKeyState(VK_SPACE) & 0x8000):
                if time.time() - last_trig > 1.2:
                    last_trig = time.time(); wake_event.set()
                    threading.Thread(target=launch_or_focus_hud_window, daemon=True).start()
        except Exception: pass
        time.sleep(0.025)

async def speak(text: str):
    if not text: return
    is_speaking_lock.set(); clean = text.replace("*", "").replace("#", "").replace("`", "").strip()
    log_bus("AERO", clean); set_agent_state("AERO", "SPEAKING", clean[:42], "#c800ff")
    out_file = os.path.join(BASE_DIR, f"tts_{int(time.time()*1000)}.mp3")
    try:
        await edge_tts.Communicate(clean, "en-US-ChristopherNeural", rate="+28%").save(out_file)
        pygame.mixer.music.load(out_file); pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if wake_event.is_set(): pygame.mixer.music.stop(); break
            await asyncio.sleep(0.03)
        pygame.mixer.music.unload()
    except Exception: pass
    finally:
        set_agent_state("AERO", "ONLINE", "Standing by", "#00f0ff")
        try:
            if os.path.exists(out_file): os.remove(out_file)
        except Exception: pass
        await asyncio.sleep(0.35); is_speaking_lock.clear()

def listen_mic():
    if is_speaking_lock.is_set() or wake_event.is_set(): return None
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.15)
        try:
            audio = recognizer.listen(source, timeout=2, phrase_time_limit=10)
            return None if is_speaking_lock.is_set() else recognizer.recognize_google(audio).lower()
        except Exception: return None

async def main():
    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=win32_hardware_hotkey_poller, daemon=True).start()
    threading.Thread(target=check_omniroute_health, daemon=True).start()
    await asyncio.sleep(0.8)
    launch_or_focus_hud_window()
    active_until = 0

    while True:
        await asyncio.sleep(0.04)
        if app_state.get("shutdown_requested"): await speak("Powering down."); kill_aero_completely()
        if app_state.get("wake_requested"): app_state["wake_requested"] = False; wake_event.set()

        if wake_event.is_set():
            wake_event.clear(); active_until = time.time() + ACTIVE_WINDOW_SECONDS; set_ui_mode("normal")
            await speak("Aero online. Go ahead, sir.")
            continue

        if app_state.get("pending_command"):
            cmd = app_state["pending_command"]; app_state["pending_command"] = None; active_until = time.time() + ACTIVE_WINDOW_SECONDS
            await speak(await orchestrate_mission(cmd, set_agent_state, log_bus, launch_or_focus_hud_window, None, set_ui_mode))
            continue

        if time.time() < active_until:
            set_agent_state("AERO", "LISTENING", "Listening (Alt+Space)", "#00ff9d")
            heard = await asyncio.to_thread(listen_mic)
            if wake_event.is_set() or not heard: continue
            
            if any(w in heard for w in ("shutdown aero", "exit aero", "kill aero")): await speak("Powering down."); kill_aero_completely()
            if any(w in heard for w in ("go to sleep", "standby", "stop listening")):
                active_until = 0; set_ui_mode("transparent"); await speak("Entering standby."); set_agent_state("AERO", "STANDBY", "Press Alt+Space to wake", "#64748b")
                continue

            await speak(await orchestrate_mission(heard, set_agent_state, log_bus, launch_or_focus_hud_window, None, set_ui_mode))
            active_until = time.time() + ACTIVE_WINDOW_SECONDS
        else:
            set_agent_state("AERO", "STANDBY", "Press Alt+Space to wake", "#00f0ff")
            heard = await asyncio.to_thread(listen_mic)
            if wake_event.is_set() or not heard: continue
            for ww in WAKE_WORDS:
                if ww in heard:
                    rem = heard.split(ww, 1)[1].strip(); active_until = time.time() + ACTIVE_WINDOW_SECONDS; launch_or_focus_hud_window()
                    if rem: await speak(await orchestrate_mission(rem, set_agent_state, log_bus, launch_or_focus_hud_window, None, set_ui_mode))
                    else: await speak("Online, sir. What's the directive?")
                    break

if __name__ == "__main__": asyncio.run(main())
