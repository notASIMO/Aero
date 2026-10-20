import json
import asyncio
from plugins.token_router import call_ai, check_local_reflex
from agents.atlas import run_atlas
from agents.nova import run_nova
from agents.sentinel import run_sentinel
from agents.pulse import run_pulse
from agents.vibe import run_vibe

async def orchestrate_mission(prompt: str, state_callback=None, log_callback=None, war_room_callback=None, approval_callback=None) -> str:
    if state_callback: state_callback("AERO", "PLANNING", prompt[:36], "#00E5FF")
    if log_callback: log_callback("DEVANG", prompt)

    # 1. Check Zero-Token Local Reflex Plugin first!
    plan = check_local_reflex(prompt)
    if plan and log_callback:
        log_callback("PLUGIN", "⚡ Zero-Token Reflex matched! Bypassed LLM API.")

    # 2. Otherwise route through Multi-Provider Free Token Router
    if not plan:
        ceo_prompt = (
            "You are AERO, Jarvis-style CEO of Devang's AI Laptop Company. "
            "Assign tasks to agents: ATLAS (architect/solve), NOVA (antigravity/codex/write_file), "
            "SENTINEL (terminal command), PULSE (inspect_screen/google_search/youtube_search), "
            "VIBE (spotify/next_desktop/prev_desktop/next_tab/close_tab/volume_up/volume_down/focus_app). "
            "Return ONLY valid JSON: "
            "{\"parallel_wave\": [{\"agent\": \"ATLAS\"|\"NOVA\"|\"SENTINEL\"|\"PULSE\"|\"VIBE\", \"action\": \"...\", \"task\": \"...\", \"target\": \"\"}], "
            "\"final_spoken_reply\": \"Concise 1-2 sentence Jarvis reply.\"}"
        )
        raw = await asyncio.to_thread(call_ai, f"Directive: {prompt}", ceo_prompt, False, True)
        try:
            clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            plan = json.loads(clean)
        except Exception:
            plan = {"parallel_wave": [], "final_spoken_reply": raw if len(raw) < 220 else "Directive processed, sir."}

    outputs = []
    for step in (plan.get("parallel_wave") or []):
        ag = step.get("agent", "AERO").upper()
        act = step.get("action", "")
        tsk = step.get("task", "")
        tgt = step.get("target", "")

        if log_callback: log_callback(ag, f"[{act}] -> {tsk}")

        if ag == "ATLAS":
            out = await asyncio.to_thread(run_atlas, tsk, "", state_callback)
        elif ag == "NOVA":
            out = await asyncio.to_thread(run_nova, act, tsk, tgt, state_callback)
        elif ag == "SENTINEL":
            out = await asyncio.to_thread(run_sentinel, tsk, state_callback, approval_callback)
        elif ag == "PULSE":
            out = await asyncio.to_thread(run_pulse, act, tsk, state_callback)
        elif ag == "VIBE":
            out = await asyncio.to_thread(run_vibe, act, tsk, state_callback, war_room_callback)
        else:
            out = "Done."

        outputs.append(f"{ag}: {out}")
        if log_callback and out:
            log_callback(ag, str(out)[:180])

    reply = plan.get("final_spoken_reply", "Mission accomplished, sir.")
    # If PULSE inspected screen or ATLAS answered a question, speak the actual finding
    if outputs and any(s.get("agent") in ("PULSE", "ATLAS") for s in (plan.get("parallel_wave") or [])):
        first_out = outputs[0].split(": ", 1)[-1]
        if len(first_out) < 280:
            reply = first_out

    if state_callback: state_callback("AERO", "ONLINE", "Standing by", "#00E5FF")
    return reply
