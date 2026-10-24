import os, threading, time, pygetwindow as gw, uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from config import BASE_DIR, SERVER_PORT
from plugins.token_router import router_telemetry

app = FastAPI()
HTML_PATH = os.path.join(BASE_DIR, "templates", "index.html")

app_state = {
    "agents": {
        "AERO":     {"status": "ONLINE", "task": "Wake: Alt+Space | Quit: Alt+Q", "color": "#00f0ff"},
        "ATLAS":    {"status": "IDLE",   "task": "CTO // OmniRoute Frontier", "color": "#c800ff"},
        "NOVA":     {"status": "IDLE",   "task": "VP Eng // VS Code & Files", "color": "#00ff9d"},
        "SENTINEL": {"status": "IDLE",   "task": "SecOps // PowerShell & Git", "color": "#ffb800"},
        "PULSE":    {"status": "IDLE",   "task": "Research // Screen Vision", "color": "#ff5500"},
        "VIBE":     {"status": "IDLE",   "task": "OS Ops // Brave & Spotify", "color": "#1db954"}
    },
    "logs": ["[SYSTEM] OmniRoute Engine Active. Press Alt+Q anytime to shut down."],
    "pending_command": None, "wake_requested": False, "shutdown_requested": False, "active_mode": "normal", "telemetry": router_telemetry
}

def kill_aero_completely():
    for win in gw.getAllWindows():
        if win.title and "AERO OS // COMMAND DECK" in win.title.upper():
            try: win.close()
            except Exception: pass
    time.sleep(0.2)
    os._exit(0)

@app.get("/", response_class=HTMLResponse)
async def get_war_room():
    with open(HTML_PATH, "r", encoding="utf-8") as f: return HTMLResponse(content=f.read(), status_code=200)

@app.get("/state")
async def get_state():
    app_state["telemetry"] = router_telemetry; return app_state

@app.post("/deploy")
async def deploy(request: Request):
    cmd = (await request.json()).get("command", "").strip()
    if cmd:
        if "shutdown" in cmd.lower() or "exit aero" in cmd.lower(): app_state["shutdown_requested"] = True
        else: app_state["pending_command"] = cmd
    return {"status": "queued"}

@app.post("/wake")
async def wake():
    app_state["wake_requested"] = True; app_state["active_mode"] = "normal"; return {"status": "waking"}

@app.post("/shutdown")
async def shutdown():
    app_state["shutdown_requested"] = True; threading.Timer(0.4, kill_aero_completely).start(); return {"status": "shutting_down"}

def run_server(): uvicorn.run(app, host="127.0.0.1", port=SERVER_PORT, log_level="error")
