import webbrowser
import mss
from PIL import Image
from config import call_gemini

def run_pulse(action: str, query: str, state_callback=None) -> str:
    if state_callback: state_callback("PULSE", "ACTIVE", query, "#FF6D00")
    if action == "inspect_screen":
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            img.thumbnail((1280, 720))
        return call_gemini(f"Analyze screen: {query}", image_pil=img)
    webbrowser.open(f"[https://www.google.com/search?q=](https://www.google.com/search?q=){query.replace(' ', '+')}")
    return f"Searched Google for {query}"
