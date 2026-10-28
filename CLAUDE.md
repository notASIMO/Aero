# AERO OS — AUTONOMOUS AI AGENT HANDOFF & PR BRIEF

## 1. Project Overview
**Aero** is a production-grade, voice-controlled autonomous AI OS executive and computer-use agent for Windows 11 (`C:\Users\devan\desktop\Aero`, Python 3.12 venv at `.\venv`, NVIDIA RTX 4050 GPU, Windows High-DPI scaling at 150%).

Do NOT use hardcoded screen coordinate ratios or brittle regex hacks. Implement a clean, autonomous architecture where the agent inspects the live Windows Accessibility Tree / Browser DOM and executes actions with sub-second responsiveness.

---

## 2. Current Repository Status (What Works vs. What Needs Fixing)

### What Is Currently Implemented & Working:
- **`main.py` (Windowing, Hotkeys & Audio Loop):**
  - Runs a frameless `pywebview` window (`AeroOS_v7_GlassDeck`) with Per-Monitor High-DPI awareness (`SetProcessDpiAwareness(2)`) and PID-based `HWND` lookup so the collapsed Dynamic Island centers at the top of the screen.
  - PID lock (`aero.pid`) prevents duplicate overlapping instances.
  - Hardware key state poller (`GetAsyncKeyState`) for:
    - **`Alt + A`**: Activate Continuous Live Listen Mode (with audio chime feedback).
    - **`Alt + S`**: Enter Standby Mode (passive wake-word listening).
    - **`Alt + Q`**: Hard kill process and release microphone lock.
  - `edge_tts` + `pygame` speech synthesis with barge-in interruption support.
- **`brain.py` (LLM Dispatcher & Telemetry):**
  - BOM-proof `.env` loader for `GROQ_API_KEY` (`gsk_...`).
  - Logs all user speech, tool calls, and agent responses to `aero_comms_history.log`.
- **`tools.py` (OS & UIAutomation Engine):**
  - Uses `uiautomation` (`WalkControl`) to inspect open Brave tabs (`TabItemControl`) so existing Spotify/YouTube tabs are focused instead of overwriting active work tabs.
  - Includes functions for Spotify playback, YouTube search/video clicking, DOM element clicking, scrolling, browser tab controls, virtual desktops, volume, and brightness.
- **`ui.html` (Two-Stage Interface):**
  - Stage 1: Collapsed top-center Dynamic Island pill (`#island-view`).
  - Stage 2: Expanded 6-Agent War Room (`#warroom-view`) with a 3D particle canvas (`#nebulaCanvas`) and status cards for `AERO`, `ATLAS`, `NOVA`, `SENTINEL`, `PULSE`, and `VIBE`.
- **`launcher_daemon.py` (Cold-Start Watchdog):**
  - Background listener that launches `main.py` when `Alt + A` is pressed if Aero is not running.

### Bugs & Remaining Tasks to Fix Immediately:
1. **Groq Model 404 Error in `brain.py`:**
   - The fallback model ID `llama-3.1-8b-instant` returned `HTTP 404: The model llama-3.1-8b-instant does not exist or you do not have access to it`.
   - *Fix Required:* Query `GET https://api.groq.com/openai/v1/models` dynamically or use verified active model IDs with native tool-calling / structured output so conversational turns ("Hello", debugging questions) and tool calls never fail.
2. **Whisper Prompt Echo Hallucination in `main.py`:**
   - Passing `"prompt": "Aero, Jarvis..."` to `whisper-large-v3-turbo` caused Whisper to hallucinate `[DEVANG] Aero, Aero, Aero, Aero, Aero, Aero, Aero.` during brief silence.
   - *Fix Required:* Remove the prompt echo trigger, add pre-transcription RMS/VAD silence filtering, and ensure fast, accurate streaming/chunked transcription without cutting off the first word.
3. **End-to-End Autonomous DOM/UIA Execution (`tools.py`):**
   - Eliminate all fallback coordinate guessing. Ensure commands like *"play Sapphire on Spotify"*, *"play the first music option on Spotify"*, and *"play the last video on YouTube"* reliably inspect the live DOM / UIA tree, locate the exact element/play button, and trigger playback without ever overwriting active work tabs.
4. **Two-Stage UI Polish (`ui.html` & `main.py`):**
   - Collapsed Dynamic Island must be sleek and translucent when idle in Standby Mode, and smooth when expanding.
   - Expanded War Room must feature a high-contrast Frosted Glassmorphism theme (no desktop/browser text bleeding through the cards) and an impressive 3D WebGL reactive avatar/core matching the reference reels below.

---

## 3. Benchmark Videos & Reference Links

- **Primary Latency & OS Integration Benchmark (CRITICAL):**
  - https://www.instagram.com/reel/DdkX_7KxKUl/?xtok=MXMxOTI1ajZhbjFnNg==
- **Agent Specifications, Task Execution & Visual Vibe:**
  - https://www.instagram.com/reel/De0UhkhSVSm/?psln=MWp4bGJhbHE4bW1mOA==
- **Architecture & Tooling Reference Repo:**
  - https://github.com/adewaskar/jarvis.git
- **Glassmorphism Dashboard Theme Reference:**
  - https://www.instagram.com/reel/De6yRJZTglH/?dlrf=MWR6cW56bnp2Z2duNQ==
- **Expanded Multi-Agent Orchestrator UI References:**
  - https://www.instagram.com/reel/DeIQfJsz2vc/?exln=b29pYXhhNjRsdGxt
  - https://www.instagram.com/reel/Dd9g4biMnS4/?obrf=ZTVvcGozeWdhYzc=
- **3D Reactive Avatar Reference:**
  - https://www.instagram.com/reel/Dc5YDjKI9ta/?exln=M3QyNnAyMDBmdzNq
- **Futuristic 3D UI Build References:**
  - https://www.instagram.com/reel/Dap3IoNo4Kt/?exln=MTM3cWl6bjUwMW9oZg==
  - https://www.instagram.com/reel/DeMbYQAMsV1/?mdxt=OWlpNnc2ZXZhZ20=
  - https://www.instagram.com/reel/Dc8liotuP-S/?rpxt=MWQ0NnUyZm44Z2xkbA==
  - https://www.instagram.com/reel/Dbd6PFPq3-c/?cplk=ZWpnMnFva29hZWxq
- **End-Goal Full Work Automation Reference:**
  - https://www.instagram.com/reel/DexBiR-T4ZW/?obrf=NXdlMGo3Njhkc3Fq