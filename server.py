import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import uvicorn

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app_state = {
    "agents": {
        "AERO": {"status": "ONLINE", "task": "Awaiting directive", "color": "#00E5FF"},
        "ATLAS": {"status": "IDLE", "task": "CTO (Deep Thinking)", "color": "#D500F9"},
        "NOVA": {"status": "IDLE", "task": "VP Eng (VS Code/Files)", "color": "#00E676"},
        "SENTINEL": {"status": "IDLE", "task": "QA & SecOps", "color": "#FFB300"},
        "PULSE": {"status": "IDLE", "task": "Research & Vision", "color": "#FF6D00"},
        "VIBE": {"status": "IDLE", "task": "OS & Spotify Ops", "color": "#1DB954"}
    },
    "logs": [" [AERO] Glassmorphism War Room Online."],
    "pending_command": None
}

@app.get("/", response_class=HTMLResponse)
async def get_war_room(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/state")
async def get_state():
    return app_state

@app.post("/deploy")
async def deploy(request: Request):
    data = await request.json()
    cmd = data.get("command")
    if cmd:
        app_state["pending_command"] = cmd
    return {"status": "queued"}

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
