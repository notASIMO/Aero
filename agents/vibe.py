import time
import ctypes
import subprocess
import webbrowser
import pyautogui
import pyperclip
import pygetwindow as gw
from config import CREATE_NO_WINDOW

def focus_window(keyword: str) -> bool:
    target = keyword.lower().strip()
    for win in gw.getAllWindows():
        if win.title and target in win.title.lower():
            try:
                if win.isMinimized:
                    win.restore()
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                win.activate()
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                time.sleep(0.3)
                return True
            except Exception:
                pass
    return False

def run_vibe(action: str, val: str = "", state_callback=None, war_room_callback=None) -> str:
    if state_callback: state_callback("VIBE", "OPS", f"{action} {val}".strip(), "#1DB954")

    if action == "spotify":
        if not focus_window("Spotify"):
            subprocess.Popen("start spotify:", shell=True, creationflags=CREATE_NO_WINDOW)
            time.sleep(2.8)
            focus_window("Spotify")
        if val.strip():
            time.sleep(0.8)
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.25)
            pyperclip.copy(val.strip())
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(1.0)
            pyautogui.press("tab")
            pyautogui.press("enter")
            if state_callback: state_callback("VIBE", "PLAYING", val, "#1DB954")
            return f"Playing {val} on Spotify."
        if state_callback: state_callback("VIBE", "READY", "Spotify focused", "#1DB954")
        return "Spotify focused."

    elif action == "next_desktop": pyautogui.hotkey("win", "ctrl", "right")
    elif action == "prev_desktop": pyautogui.hotkey("win", "ctrl", "left")
    elif action == "new_desktop": pyautogui.hotkey("win", "ctrl", "d")
    elif action == "next_tab": pyautogui.hotkey("ctrl", "tab")
    elif action == "prev_tab": pyautogui.hotkey("ctrl", "shift", "tab")
    elif action == "new_tab": pyautogui.hotkey("ctrl", "t")
    elif action == "close_tab": pyautogui.hotkey("ctrl", "w")
    elif action == "media_play_pause": pyautogui.press("playpause")
    elif action == "media_next": pyautogui.press("nexttrack")
    elif action == "volume_up":
        for _ in range(5): pyautogui.press("volumeup")
    elif action == "volume_down":
        for _ in range(5): pyautogui.press("volumedown")
    elif action == "focus_app" and val:
        if not focus_window(val):
            subprocess.Popen(f"start {val}", shell=True, creationflags=CREATE_NO_WINDOW)

    if state_callback: state_callback("VIBE", "DONE", action, "#00E676")
    return f"Executed {action}"
