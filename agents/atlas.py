from config import call_gemini

def run_atlas(task: str, ctx: str = "", state_callback=None) -> str:
    if state_callback: state_callback("ATLAS", "THINKING", task, "#D500F9")
    res = call_gemini(f"Context:\n{ctx}\n\nTask:\n{task}", system_instruction="You are ATLAS, CTO. Provide crisp architecture/code.", use_pro=True)
    if state_callback: state_callback("ATLAS", "DONE", "Ready", "#00E676")
    return res
