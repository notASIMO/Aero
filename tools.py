import os
import time
import ctypes
import urllib.parse
import subprocess
import pyperclip
import pygetwindow as gw

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import pyautogui
pyautogui.FAILSAFE = False

try:
    import uiautomation as auto
    HAS_UIA = True
except Exception:
    HAS_UIA = False

CREATE_NO_WINDOW = 0x08000000

def get_screen_size() -> tuple[int, int]:
    return ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)

def win32_click(x: int, y: int, double: bool = False):
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.06)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    if double:
        time.sleep(0.07)
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

def get_brave_path() -> str:
    for p in (
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe")
    ):
        if os.path.exists(p):
            return p
    return "brave"

def bring_window_to_front(win) -> bool:
    try:
        hwnd = win._hWnd
        ctypes.windll.user32.ShowWindow(hwnd, 9 if win.isMinimized else 5)
        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.22)
        return True
    except Exception:
        return False

def find_windows_by_title(keyword: str):
    kw = keyword.lower().strip()
    return [w for w in gw.getAllWindows() if w.title and kw in w.title.lower() and "aeroos" not in w.title.lower()]

def focus_or_open_browser_tab(tab_keyword: str, target_url: str, navigate_existing_tab: bool = False) -> str:
    """
    SAFE TAB MANAGEMENT:
    1. Scans all open windows and Brave TabItemControls via Windows UIAutomation.
    2. If a tab matching `tab_keyword` (e.g. 'Spotify' or 'YouTube') is already open, clicks that exact tab!
    3. If `navigate_existing_tab` is True AND we are confirmed inside that matching tab, updates its URL or search box.
    4. Otherwise opens a NEW tab in Brave (`brave.exe <url>`) so it NEVER overwrites Devang's current work tab!
    """
    # 1. Check if a window already has tab_keyword as its active title
    matching_wins = find_windows_by_title(tab_keyword)
    if matching_wins:
        bring_window_to_front(matching_wins[0])
        if navigate_existing_tab and target_url:
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.12)
            pyperclip.copy(target_url)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.08)
            pyautogui.press("enter")
        return f"Focused existing {tab_keyword} window."

    # 2. Check inside Brave's tab strip using UIAutomation for a background tab matching tab_keyword
    brave_wins = find_windows_by_title("brave")
    if brave_wins and HAS_UIA:
        bring_window_to_front(brave_wins[0])
        try:
            root = auto.GetForegroundControl()
            if root:
                for ctrl, _ in auto.WalkControl(root, maxDepth=7):
                    if ctrl.ControlTypeName == "TabItemControl" and tab_keyword.lower() in (ctrl.Name or "").lower():
                        rect = ctrl.BoundingRectangle
                        if rect:
                            win32_click((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
                            time.sleep(0.25)
                            if navigate_existing_tab and target_url:
                                pyautogui.hotkey("ctrl", "l")
                                time.sleep(0.12)
                                pyperclip.copy(target_url)
                                pyautogui.hotkey("ctrl", "v")
                                time.sleep(0.08)
                                pyautogui.press("enter")
                            return f"Switched to existing {tab_keyword} tab."
        except Exception:
            pass

    # 3. Open in a brand-new tab via Brave CLI (never overwrites active tab!)
    if target_url:
        subprocess.Popen([get_brave_path(), "--force-renderer-accessibility", target_url], creationflags=CREATE_NO_WINDOW)
        return f"Opened {tab_keyword} in a new Brave tab."
    return f"Could not find {tab_keyword}."

def scan_live_dom_elements(role_filter: str = "any", text_query: str = "", main_viewport_only: bool = True) -> list[dict]:
    """
    Walks the live Windows Accessibility / Browser DOM tree of the foreground window
    and returns real interactive UI elements with their exact screen coordinates.
    """
    if not HAS_UIA:
        return []
    sw, sh = get_screen_size()
    elements = []
    try:
        root = auto.GetForegroundControl()
        if not root:
            return []
        allowed_types = {
            "button": ("ButtonControl",),
            "link": ("HyperlinkControl", "ListItemControl"),
            "input": ("EditControl", "ComboBoxControl"),
            "any": ("ButtonControl", "HyperlinkControl", "ListItemControl", "EditControl", "TabItemControl")
        }.get(role_filter.lower(), ("ButtonControl", "HyperlinkControl", "ListItemControl", "EditControl"))

        for ctrl, _ in auto.WalkControl(root, maxDepth=14):
            if ctrl.ControlTypeName not in allowed_types:
                continue
            name = (ctrl.Name or "").strip()
            if not name:
                continue
            rect = ctrl.BoundingRectangle
            if not rect:
                continue
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            if w < 14 or h < 14:
                continue
            if main_viewport_only:
                # Exclude top browser chrome & left sidebars when looking for main content items
                if cy < int(sh * 0.17) or cy > int(sh * 0.90) or cx < int(sw * 0.18):
                    continue
            if text_query and text_query.lower() not in name.lower():
                continue
            elements.append({
                "type": ctrl.ControlTypeName,
                "name": name[:80],
                "x": cx,
                "y": cy,
                "w": w,
                "h": h
            })
    except Exception:
        pass

    # Sort top-to-bottom, left-to-right, and deduplicate overlapping nodes
    elements.sort(key=lambda e: (e["y"] // 28, e["x"]))
    deduped = []
    for el in elements:
        if not deduped or abs(el["y"] - deduped[-1]["y"]) > 24 or abs(el["x"] - deduped[-1]["x"]) > 45:
            deduped.append(el)
    return deduped

def resolve_ordinal(ordinal_str: str, total: int) -> int:
    if total <= 0:
        return 0
    s = str(ordinal_str).lower().strip()
    if "last" in s or "bottom" in s:
        return total - 1
    if any(k in s for k in ("second", "2nd", "two", "2")):
        return min(1, total - 1)
    if any(k in s for k in ("third", "3rd", "three", "3")):
        return min(2, total - 1)
    if any(k in s for k in ("fourth", "4th", "four", "4")):
        return min(3, total - 1)
    return 0

def execute_spotify_tool(action: str, song_query: str = "", ordinal: str = "first") -> str:
    act = action.lower().strip()
    if act in ("pause", "resume", "toggle"):
        pyautogui.press("playpause")
        return "Toggled media playback, sir."
    if act == "next":
        pyautogui.press("nexttrack")
        return "Skipped to next track, sir."
    if act == "previous":
        pyautogui.press("prevtrack")
        return "Previous track, sir."

    if act == "open" and not song_query:
        return focus_or_open_browser_tab("spotify", "https://open.spotify.com", navigate_existing_tab=False)

    if song_query:
        enc = urllib.parse.quote(song_query.strip())
        url = f"https://open.spotify.com/search/{enc}/tracks"
        focus_or_open_browser_tab("spotify", url, navigate_existing_tab=True)
        # Poll DOM up to 4.5s until Spotify renders the track list
        for _ in range(9):
            time.sleep(0.5)
            play_btns = scan_live_dom_elements(role_filter="button", text_query="Play", main_viewport_only=True)
            if play_btns:
                idx = resolve_ordinal(ordinal, len(play_btns))
                target = play_btns[idx]
                win32_click(target["x"], target["y"])
                return f"Playing '{target['name'].replace('Play ', '')}' on Spotify, sir."

    # If user asked to play the 1st / 2nd / last visible option on an already-open Spotify screen
    sp_wins = find_windows_by_title("spotify")
    if sp_wins:
        bring_window_to_front(sp_wins[0])
    play_btns = scan_live_dom_elements(role_filter="button", text_query="Play", main_viewport_only=True)
    if play_btns:
        idx = resolve_ordinal(ordinal, len(play_btns))
        target = play_btns[idx]
        win32_click(target["x"], target["y"])
        return f"Clicked {target['name']} on Spotify, sir."

    # Also check link/list items if Spotify rendered track titles as links before hover
    links = scan_live_dom_elements(role_filter="link", text_query=song_query, main_viewport_only=True)
    if links:
        idx = resolve_ordinal(ordinal, len(links))
        target = links[idx]
        # Hover over track title to reveal Spotify's Play button, then click the Play button
        ctypes.windll.user32.SetCursorPos(int(target["x"]), int(target["y"]))
        time.sleep(0.35)
        hover_play = scan_live_dom_elements(role_filter="button", text_query="Play", main_viewport_only=True)
        if hover_play:
            win32_click(hover_play[0]["x"], hover_play[0]["y"])
            return f"Playing {target['name']} on Spotify, sir."
        win32_click(target["x"], target["y"], double=True)
        return f"Selected {target['name']} on Spotify, sir."

    return f"Opened Spotify search for {song_query or ordinal}, sir."

def execute_youtube_tool(action: str, search_query: str = "", ordinal: str = "first") -> str:
    act = action.lower().strip()
    if act == "open" and not search_query:
        return focus_or_open_browser_tab("youtube", "https://www.youtube.com", navigate_existing_tab=False)

    if act == "search" or (search_query and act != "play_video"):
        enc = urllib.parse.quote(search_query.strip())
        url = f"https://www.youtube.com/results?search_query={enc}"
        focus_or_open_browser_tab("youtube", url, navigate_existing_tab=True)
        if act == "search":
            return f"Searched YouTube for '{search_query}', sir."
        time.sleep(2.8)

    # Play video by live DOM inspection (first, second, third, last, or matching title)
    yt_wins = find_windows_by_title("youtube")
    if yt_wins:
        bring_window_to_front(yt_wins[0])
        time.sleep(0.2)

    links = scan_live_dom_elements(role_filter="link", text_query="", main_viewport_only=True)
    # Filter to real video title links (length > 10 chars, not 'Home'/'Shorts')
    video_links = [el for el in links if len(el["name"]) > 10 and not el["name"].lower().startswith(("home", "shorts", "subscriptions", "filters"))]
    if video_links:
        idx = resolve_ordinal(ordinal, len(video_links))
        target = video_links[idx]
        win32_click(target["x"], target["y"])
        return f"Playing '{target['name'][:45]}' on YouTube, sir."

    return "Could not find a clickable video on the current YouTube screen, sir."

def execute_ui_click_tool(target_text: str = "", ordinal: str = "first", action: str = "click") -> str:
    if action == "scroll_down":
        pyautogui.scroll(-650)
        return "Scrolled down, sir."
    if action == "scroll_up":
        pyautogui.scroll(650)
        return "Scrolled up, sir."

    matches = scan_live_dom_elements(role_filter="any", text_query=target_text, main_viewport_only=False)
    if matches:
        idx = resolve_ordinal(ordinal, len(matches))
        chosen = matches[idx]
        win32_click(chosen["x"], chosen["y"])
        return f"Clicked '{chosen['name'][:40]}', sir."
    return f"Could not find an element matching '{target_text}' in the active window's accessibility tree, sir."

def execute_os_tool(action: str, target: str = "") -> str:
    act = action.lower().strip()
    if act == "new_tab":
        url = target if target.startswith("http") else "https://www.google.com"
        subprocess.Popen([get_brave_path(), url], creationflags=CREATE_NO_WINDOW)
        return "Opened a new tab in Brave, sir."
    if act == "close_tab":
        pyautogui.hotkey("ctrl", "w")
        return "Closed the active tab, sir."
    if act == "next_tab":
        pyautogui.hotkey("ctrl", "tab")
        return "Switched to the next tab, sir."
    if act == "prev_tab":
        pyautogui.hotkey("ctrl", "shift", "tab")
        return "Switched to the previous tab, sir."
    if act == "next_desktop":
        pyautogui.hotkey("win", "ctrl", "right")
        return "Switched to the next virtual desktop, sir."
    if act == "prev_desktop":
        pyautogui.hotkey("win", "ctrl", "left")
        return "Switched to the previous virtual desktop, sir."
    if act == "switch_window":
        if target:
            wins = find_windows_by_title(target)
            if wins:
                bring_window_to_front(wins[0])
                return f"Focused {target}, sir."
        pyautogui.hotkey("alt", "tab")
        return "Switched active window, sir."
    if act == "volume_up":
        for _ in range(6): pyautogui.press("volumeup")
        return "Increased volume, sir."
    if act == "volume_down":
        for _ in range(6): pyautogui.press("volumedown")
        return "Decreased volume, sir."
    if act == "volume_mute":
        pyautogui.press("volumemute")
        return "Toggled audio mute, sir."
    if "brightness" in act:
        import re
        m = re.search(r"(\d+)", str(target))
        val = int(m.group(1)) if m else (80 if "up" in act else 30)
        subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {val})"], capture_output=True, creationflags=CREATE_NO_WINDOW)
        return f"Brightness set to {val} percent, sir."
    return f"Executed OS command {act}, sir."

def execute_subagent_tool(department: str, command: str) -> str:
    dept = department.upper()
    if dept == "SENTINEL":
        try:
            res = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=15, creationflags=CREATE_NO_WINDOW)
            out = (res.stdout + "\n" + res.stderr).strip()[:350]
            return f"Sentinel completed execution: {out if out else 'Success.'}"
        except Exception as e:
            return f"Sentinel error: {e}"
    if dept == "NOVA":
        subprocess.Popen("code .", shell=True, creationflags=CREATE_NO_WINDOW)
        return f"Nova launched VS Code for: {command[:40]}"
    return f"{dept} finished task."
