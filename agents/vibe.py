import subprocess
import time
import pyautogui
import pyperclip
import pygetwindow as gw
import webbrowser
from config import CREATE_NO_WINDOW

def run_vibe(action: str, val: str = "", state_callback=None, war_room_callback=None) -> str:
    if state_callback: state_callback("VIBE", "OPS", action, "#1DB954")
    if action == "spotify":
        subprocess.Popen("start spotify:", shell=True, creationflags=CREATE_NO_WINDOW)
        return "Opened Spotify"
    elif action == "show_war_room" and war_room_callback:
        war_room_callback()
    return f"OS Action: {action}"
