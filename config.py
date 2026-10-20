import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

MEMORY_FILE = os.path.join(BASE_DIR, "company_memory.json")
ENV_FILE = os.path.join(BASE_DIR, ".env")
WAKE_WORDS = ["aero", "arrow", "asimo", "hey aero", "ok aero", "jarvis"]
WAKE_HOTKEY = "shift+alt+space"
ACTIVE_WINDOW_SECONDS = 25
CREATE_NO_WINDOW = 0x08000000
SERVER_PORT = 8765

def load_env_vars():
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()
                elif not os.environ.get("GEMINI_API_KEY"):
                    os.environ["GEMINI_API_KEY"] = line

load_env_vars()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
