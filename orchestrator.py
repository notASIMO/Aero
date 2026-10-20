import json
import asyncio
from config import call_gemini
from agents.atlas import run_atlas
from agents.nova import run_nova
from agents.sentinel import run_sentinel
from agents.pulse import run_pulse
from agents.vibe import run_vibe

async def orchestrate_mission(prompt: str, state_callback=None, log_callback=None, war_room_callback=None, approval_callback=None) -> str:
    if state_callback: state_callback("AERO", "PLANNING", prompt[:30], "#00E5FF")
    if log_callback: log_callback("DEVANG", prompt)

    ceo_prompt = "You are AERO, CEO. Return JSON: {\"parallel_wave\": [{\"agent\": \"ATLAS\"|\"NOVA\"|\"SENTINEL\"|\"PULSE\"|\"VIBE\", \"action\": \"...\", \"task\": \"...\", \"target\": \"\"}], \"final_spoken_reply\": \"...\"}"
    raw = call_gemini(f"Directive: {prompt}", system_instruction=ceo_prompt, json_mode=True)
    try: plan = json.loads(raw.removeprefix("```json").removesuffix("```").strip())
    except: plan = {"parallel_wave": [], "final_spoken_reply": "Right away, sir."}

    for step in (plan.get("parallel_wave") or []):
        ag = step.get("agent", "AERO").upper()
        act = step.get("action", "")
        tsk = step.get("task", "")
        tgt = step.get("target", "")

        if log_callback: log_callback(ag, f"Executing: {tsk}")

        if ag == "ATLAS": await asyncio.to_thread(run_atlas, tsk, "", state_callback)
        elif ag == "NOVA": await asyncio.to_thread(run_nova, act, tsk, tgt, state_callback)
        elif ag == "SENTINEL": await asyncio.to_thread(run_sentinel, tsk, state_callback, approval_callback)
        elif ag == "PULSE": await asyncio.to_thread(run_pulse, act, tsk, state_callback)
        elif ag == "VIBE": await asyncio.to_thread(run_vibe, act, tsk, state_callback, war_room_callback)

    return plan.get("final_spoken_reply", "Mission accomplished.")
