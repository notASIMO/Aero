from plugins.token_router import call_ai

def run_atlas(task: str, ctx: str = "", state_callback=None) -> str:
    if state_callback: state_callback("ATLAS", "THINKING", task, "#D500F9")
    res = call_ai(
        f"Context:\n{ctx}\n\nCTO Task:\n{task}",
        system_instruction="You are ATLAS, CTO of Aero Corp. Provide crisp architecture, code, or technical answers in 2-3 sentences.",
        use_pro=True
    )
    if state_callback: state_callback("ATLAS", "DONE", "Architecture ready", "#00E676")
    return res
