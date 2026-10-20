import subprocess
from config import CREATE_NO_WINDOW

DANGEROUS_KEYWORDS = ["rm -rf", "del /s", "remove-item -recurse", "format ", "git push --force", "shutdown"]

def run_sentinel(command: str, state_callback=None, approval_callback=None) -> str:
    if state_callback: state_callback("SENTINEL", "AUDITING", command, "#FFB300")
    if any(k in command.lower() for k in DANGEROUS_KEYWORDS):
        if approval_callback and not approval_callback(command):
            return "Denied by user."
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=35, creationflags=CREATE_NO_WINDOW)
        out = (res.stdout + "\n" + res.stderr).strip()[:1500]
        if state_callback: state_callback("SENTINEL", "DONE", "Audited", "#00E676")
        return out
    except Exception as e:
        return f"Error: {e}"
