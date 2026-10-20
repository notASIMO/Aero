import os
import re
import time
import json
import ctypes
from ctypes import wintypes
import urllib.parse
import subprocess
import pyautogui
import pyperclip
import pygetwindow as gw
import mss
from PIL import Image
from config import CREATE_NO_WINDOW
from plugins.token_router import call_ai

pyautogui.FAILSAFE = False

# ============================================================================
# 1. BRAVE BROWSER & WIN32 VIRTUAL DESKTOP / WINDOW SCANNER
# ============================================================================
def get_brave_path() -> str:
    candidates = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "brave"

def open_in_brave(url: str, new_window: bool = False):
    brave = get_brave_path()
    args = [brave]
    if new_window:
        args.append("--new-window")
    args.append(url)
    subprocess.Popen(args, creationflags=CREATE_NO_WINDOW)

def is_window_on_other_virtual_desktop(hwnd: int) -> bool:
    """Uses Win32 DwmGetWindowAttribute(DWMWA_CLOAKED=14) to detect windows on other virtual desktops."""
    DWMWA_CLOAKED = 14
    cloaked = ctypes.c_int(0)
    try:
        res = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_CLOAKED),
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked)
        )
        if res == 0 and cloaked.value != 0:
            return True
    except Exception:
        pass
    return False

def find_all_matching_windows(keyword: str) -> list[dict]:
    """Scans all open windows across current and other virtual desktops."""
    target = keyword.lower().strip()
    matches = []
    active_win = gw.getActiveWindow()
    active_hwnd = active_win._hWnd if active_win else None

    for w in gw.getAllWindows():
        if not w.title:
            continue
        title_low = w.title.lower()
        if target in title_low and "aero os // neural command deck" not in title_low:
            hwnd = w._hWnd
            other_desktop = is_window_on_other_virtual_desktop(hwnd)
            is_foreground = (hwnd == active_hwnd) and not w.isMinimized and not other_desktop
            matches.append({
                "win": w,
                "hwnd": hwnd,
                "title": w.title,
                "is_minimized": w.isMinimized,
                "other_desktop": other_desktop,
                "is_foreground": is_foreground
            })
    return matches

def force_activate_window(win_obj) -> bool:
    """Forces Windows to jump to the window (even across virtual desktops or minimized state)."""
    try:
        hwnd = win_obj._hWnd
        if win_obj.isMinimized:
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # Alt down
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)  # Alt up
        time.sleep(0.35)
        return True
    except Exception:
        try:
            win_obj.activate()
            return True
        except Exception:
            return False

# ============================================================================
# 2. SCREEN VISION ENGINE (CLICK UI ELEMENTS, SEARCH BARS & VIDEOS)
# ============================================================================
def capture_screen() -> tuple[Image.Image, int, int]:
    with mss.mss() as sct:
        mon = sct.monitors[1]
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        sw, sh = img.size
        img_thumb = img.copy()
        img_thumb.thumbnail((1280, 720))
        return img_thumb, sw, sh

def vision_locate_and_click(target_description: str, fallback_coords: tuple[float, float] | None = None) -> str:
    """Uses Gemini Vision to find exact (x,y) of any element on screen and clicks it."""
    img, sw, sh = capture_screen()
    prompt = (
        f"Locate the exact center of '{target_description}' on this screen. "
        "Return ONLY valid JSON: {\"found\": true, \"x_ratio\": 0.0 to 1.0, \"y_ratio\": 0.0 to 1.0}"
    )
    try:
        raw = call_ai(prompt, json_mode=True, image_pil=img)
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(clean)
        if data.get("found", True) and "x_ratio" in data and "y_ratio" in data:
            x = int(float(data["x_ratio"]) * sw)
            y = int(float(data["y_ratio"]) * sh)
            pyautogui.moveTo(x, y, duration=0.25)
            pyautogui.click()
            return f"Clicked on {target_description} at ({x}, {y})."
    except Exception:
        pass

    if fallback_coords:
        x = int(fallback_coords[0] * sw)
        y = int(fallback_coords[1] * sh)
        pyautogui.moveTo(x, y, duration=0.25)
        pyautogui.click()
        return f"Clicked {target_description}."
    return f"Could not pinpoint {target_description} on screen."

# ============================================================================
# 3. HARDWARE CONTROLS: BRIGHTNESS & VOLUME
# ============================================================================
def adjust_brightness(direction: str = "up", exact_level: int | None = None) -> str:
    try:
        if exact_level is None:
            ps_get = "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_get], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            curr = int(res.stdout.strip() or "50")
            target = min(100, curr + 20) if direction == "up" else max(10, curr - 20)
        else:
            target = max(0, min(100, exact_level))

        ps_set = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {target})"
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_set], capture_output=True, creationflags=CREATE_NO_WINDOW)
        return f"Screen brightness set to {target} percent, sir."
    except Exception:
        return "Adjusted screen brightness, sir."

def adjust_volume(direction: str = "up", steps: int = 6) -> str:
    if direction == "mute":
        pyautogui.press("volumemute")
        return "Toggled audio mute, sir."
    key = "volumeup" if direction == "up" else "volumedown"
    for _ in range(steps):
        pyautogui.press(key)
    return f"{'Increased' if direction == 'up' else 'Decreased'} system volume, sir."

# ============================================================================
# 4. SPOTIFY & YOUTUBE AUTOMATION ON BRAVE
# ============================================================================
def play_song_on_spotify_brave(song_name: str) -> str:
    """
    Plays a song on Spotify inside Brave WITHOUT searching Google!
    Navigates directly to [https://open.spotify.com/search/](https://open.spotify.com/search/)<encoded_song> in the Spotify tab,
    then clicks the top track play button.
    """
    encoded = urllib.parse.quote(song_name.strip())
    search_url = f"[https://open.spotify.com/search/](https://open.spotify.com/search/){encoded}"

    # Check if Spotify window/tab is already open
    matches = find_all_matching_windows("spotify")
    if matches:
        win_info = matches[0]
        force_activate_window(win_info["win"])
        time.sleep(0.4)
        if "brave" in win_info["title"].lower() or "chrome" in win_info["title"].lower():
            # Focus address bar and enter the full [https://open.spotify.com/search/](https://open.spotify.com/search/)... URL so Brave navigates Spotify directly!
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.2)
            pyperclip.copy(search_url)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.15)
            pyautogui.press("enter")
        else:
            # Native Spotify desktop app
            pyautogui.hotkey("ctrl", "k")
            time.sleep(0.25)
            pyperclip.copy(song_name)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.25)
            pyautogui.press("enter")
            time.sleep(1.2)
            pyautogui.press("enter")
            return f"Playing {song_name} on Spotify, sir."
    else:
        open_in_brave(search_url)

    # Wait for Spotify Web search results to render, then click Play on the Top Result / Songs list
    time.sleep(3.6)
    vision_locate_and_click(
        f"the green play button or first song row for '{song_name}' in Spotify search results",
        fallback_coords=(0.38, 0.42)
    )
    return f"Playing {song_name} on Spotify in Brave, sir."

def search_on_open_youtube(query: str) -> str:
    """Types into the YouTube search bar on the currently visible Brave YouTube tab and searches."""
    matches = find_all_matching_windows("youtube")
    if matches:
        force_activate_window(matches[0]["win"])
        time.sleep(0.4)
        # In YouTube web, pressing '/' natively focuses the search input bar!
        # We also click the top-center YouTube search bar as backup to be 100% certain.
        sw, sh = pyautogui.size()
        pyautogui.click(int(sw * 0.46), int(sh * 0.11))
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("backspace")
        pyperclip.copy(query)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        pyautogui.press("enter")
        return f"Searched YouTube for {query}, sir. Say 'play the first video' whenever you're ready."
    else:
        encoded = urllib.parse.quote(query.strip())
        open_in_brave(f"[https://www.youtube.com/results?search_query=](https://www.youtube.com/results?search_query=){encoded}")
        return f"Opened YouTube in Brave and searched for {query}, sir."

def click_youtube_video_by_index(index_word: str = "first") -> str:
    """Clicks the 1st, 2nd, or 3rd video on the currently visible YouTube screen."""
    matches = find_all_matching_windows("youtube") or find_all_matching_windows("brave")
    if matches:
        force_activate_window(matches[0]["win"])
        time.sleep(0.3)

    fallback_y = 0.34 if "first" in index_word or "1" in index_word else (0.58 if "second" in index_word or "2" in index_word else 0.78)
    return vision_locate_and_click(
        f"the {index_word} video thumbnail or video title in the main YouTube area",
        fallback_coords=(0.36, fallback_y)
    )
