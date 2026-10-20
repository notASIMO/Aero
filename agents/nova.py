import os
import time
import subprocess
import pyperclip
import pyautogui
from config import CREATE_NO_WINDOW
from plugins.token_router import call_ai

def run_nova(action: str, task_prompt: str, target_path: str = "", state_callback=None) -> str:
    if state_callback: state_callback("NOVA", "CODING", task_prompt, "#00E676")
    if action == "write_file" and target_path:
        fp = os.path.expanduser(target_path)
        os.makedirs(os.path.dirname(os.path.abspath(fp)), exist_ok=True)
        code = call_ai(f"Write raw production code for '{target_path}'. Task: {task_prompt}. Output ONLY raw code.", use_pro=True)
        code = code.removeprefix("```python").removeprefix("```").removesuffix("```").strip()
        with open(fp, "w", encoding="utf-8") as f:
            f.write(code)
        if state_callback: state_callback("NOVA", "DONE", f"Wrote {os.path.basename(fp)}", "#00E676")
        return f"Wrote {fp}"

    subprocess.Popen("code .", shell=True, creationflags=CREATE_NO_WINDOW)
    time.sleep(1.5)
    pyperclip.copy(task_prompt)
    pyautogui.hotkey("ctrl", "shift", "i")
    time.sleep(0.4)
    pyautogui.hotkey("ctrl", "v")
    pyautogui.press("enter")
    if state_callback: state_callback("NOVA", "DONE", "Sent to VS Code", "#00E676")
    return f"Dispatched to VS Code: {task_prompt}"
