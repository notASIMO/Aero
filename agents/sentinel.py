import subprocess
from config import CREATE_NO_WINDOW

DANGEROUS_KEYWORDS = ["rm -rf", "del /s", "remove-item -recurse", "format ", "git push --force", "shutdown"]

def run_sentinel(command: str, state_callback=None, approval_callback=None) -> str:
    if state_callback: state_callback("SENTINEL", "AUDITING", command, "#FFB300")
    if any(k in command.lower() for k in DANGEROUS_KEYWORDS):
        if approval_callback and not approval_callback(command):
            if state_callback: state_callback("SENTINEL", "BLOCKED", "Rejected", "#FF5252")
            return "Denied by user."
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW
        )
        out = (res.stdout + "\n" + res.stderr).strip()[:1200]
        if state_callback: state_callback("SENTINEL", "DONE", "Audit complete", "#00E676")
        return out if out else "Command executed (0 output)."
    except Exception as e:
        if state_callback: state_callback("SENTINEL", "ERROR", "Failed", "#FF5252")
        return f"Error: {e}"
