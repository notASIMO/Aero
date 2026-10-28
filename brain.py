import os
import re
import json
import time
import requests
from tools import (
    execute_spotify_tool, execute_youtube_tool, execute_ui_click_tool,
    execute_os_tool, execute_subagent_tool
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
COMMS_LOG_FILE = os.path.join(BASE_DIR, "aero_comms_history.log")

conversation_history = []

def log_comms(speaker: str, text: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(COMMS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{speaker}]: {text}\n")
    except Exception:
        pass

def get_groq_key() -> str:
    k = os.environ.get("GROQ_API_KEY", "").strip()
    m = re.search(r"(gsk_[A-Za-z0-9_\-]{20,})", k)
    if m:
        return m.group(1)
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8-sig", errors="ignore") as f:
                content = f.read()
            m2 = re.search(r"(gsk_[A-Za-z0-9_\-]{20,})", content)
            if m2:
                os.environ["GROQ_API_KEY"] = m2.group(1)
                return m2.group(1)
        except Exception:
            pass
    return ""

def save_groq_key(new_key: str):
    m = re.search(r"(gsk_[A-Za-z0-9_\-]{20,})", new_key.strip())
    if not m:
        return
    clean_key = m.group(1)
    os.environ["GROQ_API_KEY"] = clean_key
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(f"GROQ_API_KEY={clean_key}\n")

SYSTEM_PROMPT = """You are AERO (Jarvis), Devang's real-time AI Executive and Windows 11 Computer-Use Agent.
You MUST respond with ONLY a valid JSON object matching this exact structure:
{
  "department": "AERO" | "ATLAS" | "NOVA" | "SENTINEL" | "PULSE" | "VIBE",
  "tool": "none" | "spotify" | "youtube" | "dom_click" | "os" | "subagent",
  "action": "string",
  "query": "string",
  "ordinal": "first" | "second" | "third" | "fourth" | "last",
  "reply": "Your natural, concise 1-2 sentence spoken response to Devang."
}

RULES FOR TOOL SELECTION:
1. CONVERSATION & QUESTIONS (tool = "none"):
   - If Devang says "Hello", asks a general question, discusses a bug, or talks about what happened earlier, set "tool": "none" and answer naturally in "reply".
2. SPOTIFY (tool = "spotify", department = "VIBE"):
   - action: "open" (just open/focus Spotify) | "search_and_play" (search & play a specific song) | "play_visible_option" (click the 1st/2nd/last song currently on screen) | "pause" | "next" | "previous"
   - query: ONLY the song/artist name (e.g. "Manwa Laage", "Sapphire"). Leave "" if just opening or clicking a visible option.
   - ordinal: "first" | "second" | "third" | "last"
3. YOUTUBE (tool = "youtube", department = "PULSE"):
   - action: "open" | "search" | "play_video"
   - query: search topic if searching, otherwise ""
   - ordinal: "first" | "second" | "third" | "last"
4. CLICK ANY SCREEN ELEMENT OR SCROLL (tool = "dom_click", department = "PULSE"):
   - action: "click" | "scroll_down" | "scroll_up"
   - query: visible text of the button/link to click on screen
   - ordinal: "first" | "second" | "third" | "last"
5. OS, TABS, WINDOWS, VOLUME, BRIGHTNESS (tool = "os", department = "VIBE"):
   - action: "new_tab" | "close_tab" | "next_tab" | "prev_tab" | "next_desktop" | "prev_desktop" | "switch_window" | "volume_up" | "volume_down" | "volume_mute" | "brightness_up" | "brightness_down"
   - query: optional window name to focus or brightness level (0-100)
6. CODING OR TERMINAL (tool = "subagent", department = "NOVA" or "SENTINEL"):
   - action: "NOVA" (open VS Code) | "SENTINEL" (run PowerShell command)
   - query: the command or task."""

def call_groq_json(messages: list, groq_key: str) -> tuple[dict, int, str]:
    t0 = time.time()
    last_err = ""
    # Try Llama-3.3-70B first, instant failover to Llama-3.1-8B-Instant if rate-limited or busy
    for model_name in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": model_name,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 350,
                    "response_format": {"type": "json_object"}
                },
                timeout=8
            )
            if r.status_code == 200:
                raw = r.json()["choices"][0]["message"]["content"].strip()
                ms = int((time.time() - t0) * 1000)
                return json.loads(raw), ms, f"GROQ // {model_name[:12].upper()}"
            else:
                last_err = f"HTTP {r.status_code}: {r.text[:120]}"
                log_comms("GROQ_WARN", last_err)
        except Exception as e:
            last_err = str(e)
            log_comms("GROQ_ERR", last_err)

    ms = int((time.time() - t0) * 1000)
    return {
        "department": "AERO",
        "tool": "none",
        "action": "",
        "query": "",
        "ordinal": "first",
        "reply": f"API error: {last_err[:90]}"
    }, ms, "ERROR"

def process_directive(user_text: str, notify_fn, collapse_fn) -> str:
    log_comms("DEVANG", user_text)
    groq_key = get_groq_key()
    if not groq_key:
        msg = "Sir, please paste your gsk Groq key in the bottom-right box and press Enter."
        log_comms("AERO", msg)
        return msg

    conversation_history.append({"role": "user", "content": user_text})
    if len(conversation_history) > 10:
        conversation_history[:] = conversation_history[-10:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history
    plan, latency_ms, provider = call_groq_json(messages, groq_key)

    dept = str(plan.get("department", "AERO")).upper()
    tool = str(plan.get("tool", "none")).lower()
    action = str(plan.get("action", "")).strip()
    query = str(plan.get("query", "")).strip()
    ordinal = str(plan.get("ordinal", "first")).strip()
    spoken_reply = str(plan.get("reply", "Done, sir.")).strip()

    if tool != "none":
        notify_fn(dept, "EXECUTING", f"{tool}: {action} {query}".strip(), latency_ms, provider)
        log_comms(f"TOOL [{dept}]", f"{tool} | action={action} | query={query} | ordinal={ordinal}")
        collapse_fn()
        try:
            if tool == "spotify":
                tool_out = execute_spotify_tool(action or "open", query, ordinal)
            elif tool == "youtube":
                tool_out = execute_youtube_tool(action or "open", query, ordinal)
            elif tool == "dom_click":
                tool_out = execute_ui_click_tool(query, ordinal, action or "click")
            elif tool == "os":
                tool_out = execute_os_tool(action, query)
            elif tool == "subagent":
                tool_out = execute_subagent_tool(action or dept, query)
            else:
                tool_out = ""
            if tool_out and not spoken_reply:
                spoken_reply = tool_out
        except Exception as e:
            log_comms("TOOL_ERROR", str(e))

    notify_fn(dept, "ONLINE" if dept == "AERO" else "DONE", spoken_reply[:48], latency_ms, provider)
    conversation_history.append({"role": "assistant", "content": json.dumps(plan)})
    log_comms("AERO", spoken_reply)
    return spoken_reply