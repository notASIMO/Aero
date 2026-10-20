import webbrowser
import mss
from PIL import Image
from plugins.token_router import call_ai

def run_pulse(action: str, query: str, state_callback=None) -> str:
    if state_callback: state_callback("PULSE", "ACTIVE", query, "#FF6D00")
    if action == "inspect_screen":
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            img.thumbnail((1280, 720))
        res = call_ai(f"Analyze Devang's screen concisely: {query}", image_pil=img)
        if state_callback: state_callback("PULSE", "DONE", "Screen analyzed", "#00E676")
        return res
    elif action == "youtube_search":
        webbrowser.open(f"[https://www.youtube.com/results?search_query=](https://www.youtube.com/results?search_query=){query.replace(' ', '+')}")
    else:
        webbrowser.open(f"[https://www.google.com/search?q=](https://www.google.com/search?q=){query.replace(' ', '+')}")
    if state_callback: state_callback("PULSE", "DONE", f"Searched {query[:18]}", "#00E676")
    return f"Opened browser search for {query}"
