# Aero Bridge (VS Code Extension)

Local WebSocket bridge connecting the **Aero** voice orchestrator to Visual Studio Code / Antigravity IDE.

---

## ⚡ Overview

When Aero parses a voice command (e.g. *"Aero, review this file"* or *"Aero, open chat"*), it sends a WebSocket JSON message to `ws://localhost:8765`. 
This extension:
1. Runs a lightweight WebSocket server inside VS Code listening on port **8765**.
2. Dispatches incoming actions to VS Code commands via `vscode.commands.executeCommand()`.
3. Sends a JSON acknowledgment back to Aero.

---

## 🛰️ Message Protocol

### Incoming Message (from Aero)
```json
{
  "action": "trigger_review",
  "payload": "Review this function for potential edge cases"
}
```

### Response (sent back to Aero)
```json
{
  "status": "success",
  "action": "trigger_review",
  "command": "antigravity.review",
  "message": "Triggered code review using 'antigravity.review'",
  "result": null,
  "timestamp": 1728720000000
}
```

---

## 🎯 Supported Actions

| Action | Maps To / Behavior |
| :--- | :--- |
| `trigger_review` | Runs `antigravity.review`, `antigravity.codeReview`, or `workbench.action.chat.openReview` (with payload prompt) |
| `trigger_chat` | Opens Antigravity AI / VS Code Chat panel (`antigravity.openChat` or `workbench.action.chat.open`) |
| `save` / `save_file` | Saves current active file (`workbench.action.files.save`) |
| `save_all` | Saves all open files (`workbench.action.files.saveAll`) |
| `format` / `format_document` | Formats current document (`editor.action.formatDocument`) |
| `terminal` / `toggle_terminal` | Toggles integrated terminal (`workbench.action.terminal.toggleTerminal`) |
| `quick_open` | Opens file picker (`workbench.action.quickOpen`) |
| `command_palette` | Opens command palette (`workbench.action.showCommands`) |
| *Direct Command ID* | Any valid VS Code command ID (e.g. `workbench.action.splitEditor`) |

You can also define custom mappings in your VS Code `settings.json`:
```json
{
  "aeroBridge.customActionMap": {
    "my_custom_voice_command": "editor.action.commentLine"
  }
}
```

---

## 🚀 Setup and Run Instructions

### Step 1: Install Dependencies
Open a terminal in the `aero-bridge` directory:
```bash
cd aero-bridge
npm install
```

### Step 2: Compile TypeScript
```bash
npm run compile
```

### Step 3: Run Extension in VS Code

#### Option A: Debug / Extension Host (Quickest for Development)
1. In VS Code, open the `aero-bridge` folder (or open the root `Aero` workspace).
2. Press `F5` (or go to **Run and Debug** -> click **Run Aero Bridge Extension**).
3. A new **Extension Development Host** window will open with Aero Bridge active.
4. You will see `$(radio-tower) Aero: 8765` in the bottom status bar!

#### Option B: Install Locally into your Main VS Code
To have Aero Bridge permanently running in your primary VS Code window:
1. Install `vsce` if needed:
   ```bash
   npm install -g @vscode/vsce
   ```
2. Package the extension:
   ```bash
   npx @vscode/vsce package --no-dependencies
   ```
   *(Or simply run `npx @vscode/vsce package`)*
3. Install the resulting `.vsix` file:
   ```bash
   code --install-extension aero-bridge-0.0.1.vsix
   ```
   *(Or in VS Code: press `Ctrl+Shift+P` -> search **Extensions: Install from VSIX...** -> select `aero-bridge-0.0.1.vsix`)*
4. Reload VS Code. The extension will automatically activate and start listening on port 8765.

---

## 🧪 Testing the Bridge

Run the test script from the Aero workspace:
```bash
python test_bridge.py
```
Or start Aero:
```bash
python core_agent.py
```
And say: *"Aero, review this code"* or *"Aero, open chat"*.

