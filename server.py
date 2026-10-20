import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import uvicorn
from config import BASE_DIR, SERVER_PORT
from plugins.token_router import router_telemetry, set_router_mode

app = FastAPI()
HTML_PATH = os.path.join(BASE_DIR, "templates", "index.html")

app_state = {
    "agents": {
        "AERO":     {"status": "ONLINE", "task": "Press Shift+Alt+Space or click Reactor", "color": "#00f0ff"},
        "ATLAS":    {"status": "IDLE",   "task": "CTO // Deep Architecture", "color": "#c800ff"},
        "NOVA":     {"status": "IDLE",   "task": "VP Eng // VS Code & Files", "color": "#00ff9d"},
        "SENTINEL": {"status": "IDLE",   "task": "SecOps // PowerShell & Git", "color": "#ffb800"},
        "PULSE":    {"status": "IDLE",   "task": "Research // Screen Vision", "color": "#ff5500"},
        "VIBE":     {"status": "IDLE",   "task": "OS Ops // Desktops & Spotify", "color": "#1db954"}
    },
    "logs": ["[SYSTEM] Aero Neural OS & Infinite-Token Plugin Router Online."],
    "pending_command": None,
    "wake_requested": False,
    "telemetry": router_telemetry
}

@app.get("/", response_class=HTMLResponse)
async def get_war_room():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/state")
async def get_state():
    app_state["telemetry"] = router_telemetry
    return app_state

@app.post("/deploy")
async def deploy(request: Request):
    data = await request.json()
    cmd = data.get("command", "").strip()
    if cmd:
        app_state["pending_command"] = cmd
    return {"status": "queued"}

@app.post("/wake")
async def wake():
    app_state["wake_requested"] = True
    return {"status": "waking"}

@app.post("/router_mode")
async def update_mode(request: Request):
    data = await request.json()
    mode = data.get("mode", "AUTO")
    set_router_mode(mode)
    return {"status": "ok", "mode": mode}

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=SERVER_PORT, log_level="error")
