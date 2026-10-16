import * as vscode from 'vscode';
import { WebSocketServer, WebSocket } from 'ws';

interface AeroMessage {
  action: string;
  payload?: any;
  args?: any[];
}

interface AeroResponse {
  status: 'success' | 'error';
  action?: string;
  command?: string;
  message?: string;
  error?: string;
  result?: any;
  timestamp: number;
}

let wss: WebSocketServer | null = null;
let currentPort = 8765;
let connectedClientsCount = 0;
let statusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext) {
  outputChannel = vscode.window.createOutputChannel('Aero Bridge');
  context.subscriptions.push(outputChannel);
  log('Aero Bridge extension activating...');

  // Setup Status Bar Item
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.command = 'aero-bridge.status';
  context.subscriptions.push(statusBarItem);
  updateStatusBar('stopped');

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand('aero-bridge.startServer', async () => {
      const config = vscode.workspace.getConfiguration('aeroBridge');
      const port = config.get<number>('port', 8765);
      await startServer(port);
    }),

    vscode.commands.registerCommand('aero-bridge.stopServer', () => {
      stopServer();
      vscode.window.showInformationMessage('Aero Bridge: WebSocket server stopped.');
    }),

    vscode.commands.registerCommand('aero-bridge.restartServer', async () => {
      stopServer();
      const config = vscode.workspace.getConfiguration('aeroBridge');
      const port = config.get<number>('port', 8765);
      await startServer(port);
      vscode.window.showInformationMessage(`Aero Bridge: WebSocket server restarted on port ${port}.`);
    }),

    vscode.commands.registerCommand('aero-bridge.status', () => {
      showStatusQuickPick();
    })
  );

  // Auto-start server if enabled
  const config = vscode.workspace.getConfiguration('aeroBridge');
  const autoStart = config.get<boolean>('autoStart', true);
  currentPort = config.get<number>('port', 8765);

  if (autoStart) {
    startServer(currentPort);
  }

  // Listen for config changes
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (e.affectsConfiguration('aeroBridge.port')) {
        const newPort = vscode.workspace.getConfiguration('aeroBridge').get<number>('port', 8765);
        if (newPort !== currentPort && wss) {
          log(`Port configuration changed to ${newPort}. Restarting server...`);
          stopServer();
          await startServer(newPort);
        }
      }
    })
  );

  // Register disposal cleanup
  context.subscriptions.push({
    dispose: () => {
      stopServer();
    }
  });

  log('Aero Bridge extension activated successfully.');
}

export function deactivate() {
  stopServer();
}

/**
 * Starts the WebSocket server on the specified port.
 */
function startServer(port: number): Promise<void> {
  return new Promise((resolve) => {
    if (wss) {
      log('Server already running. Stopping previous instance...');
      stopServer();
    }

    currentPort = port;
    updateStatusBar('starting');
    log(`Starting WebSocket server on ws://localhost:${port}...`);

    try {
      wss = new WebSocketServer({ port });

      wss.on('listening', () => {
        log(`⚡ Aero Bridge listening on ws://localhost:${port}`);
        updateStatusBar('running');
        statusBarItem.show();
        resolve();
      });

      wss.on('connection', (ws: WebSocket, req) => {
        connectedClientsCount++;
        const clientIp = req.socket.remoteAddress || 'unknown';
        log(`Client connected from ${clientIp}. Total clients: ${connectedClientsCount}`);
        updateStatusBar('running');

        ws.on('message', async (data: Buffer | string) => {
          await handleIncomingMessage(ws, data.toString());
        });

        ws.on('close', () => {
          connectedClientsCount = Math.max(0, connectedClientsCount - 1);
          log(`Client disconnected. Total clients: ${connectedClientsCount}`);
          updateStatusBar('running');
        });

        ws.on('error', (err) => {
          log(`Client error: ${err.message}`);
        });
      });

      wss.on('error', (err: any) => {
        if (err.code === 'EADDRINUSE') {
          log(`❌ Error: Port ${port} is already in use.`);
          updateStatusBar('error', `Port ${port} in use`);
          vscode.window.showErrorMessage(
            `Aero Bridge: Port ${port} is already in use by another process.`,
            'Change Port',
            'Retry'
          ).then(async (selection) => {
            if (selection === 'Retry') {
              startServer(port);
            } else if (selection === 'Change Port') {
              const input = await vscode.window.showInputBox({
                prompt: 'Enter new port for Aero Bridge WebSocket server',
                value: String(port)
              });
              if (input && !isNaN(Number(input))) {
                const newPort = Number(input);
                await vscode.workspace.getConfiguration('aeroBridge').update('port', newPort, vscode.ConfigurationTarget.Global);
                startServer(newPort);
              }
            }
          });
        } else {
          log(`❌ Server error: ${err.message}`);
          updateStatusBar('error', err.message);
        }
        resolve();
      });

    } catch (err: any) {
      log(`❌ Failed to create WebSocket server: ${err?.message || err}`);
      updateStatusBar('error', err?.message || 'Failed to start');
      resolve();
    }
  });
}

/**
 * Stops the WebSocket server and disconnects clients.
 */
function stopServer() {
  if (wss) {
    try {
      for (const client of wss.clients) {
        if (client.readyState === WebSocket.OPEN) {
          client.close(1000, 'Server stopping');
        }
      }
      wss.close();
      log('WebSocket server stopped.');
    } catch (err: any) {
      log(`Error while closing server: ${err?.message || err}`);
    } finally {
      wss = null;
      connectedClientsCount = 0;
      updateStatusBar('stopped');
    }
  }
}

/**
 * Handles incoming WebSocket text messages from Aero.
 */
async function handleIncomingMessage(ws: WebSocket, rawMessage: string) {
  log(`📥 Received message: ${rawMessage}`);

  let parsed: AeroMessage;
  try {
    parsed = JSON.parse(rawMessage);
  } catch (err) {
    const errorResponse: AeroResponse = {
      status: 'error',
      error: `Invalid JSON format: ${err instanceof Error ? err.message : String(err)}`,
      timestamp: Date.now()
    };
    sendJson(ws, errorResponse);
    return;
  }

  if (!parsed.action || typeof parsed.action !== 'string') {
    const errorResponse: AeroResponse = {
      status: 'error',
      error: "Message must contain an 'action' string property. E.g.: { \"action\": \"trigger_review\", \"payload\": \"...\" }",
      timestamp: Date.now()
    };
    sendJson(ws, errorResponse);
    return;
  }

  const { action, payload, args } = parsed;

  try {
    const executionResult = await executeAction(action, payload, args);

    const successResponse: AeroResponse = {
      status: 'success',
      action: action,
      command: executionResult.commandId,
      message: executionResult.message,
      result: executionResult.result,
      timestamp: Date.now()
    };

    sendJson(ws, successResponse);

    // Notify user in status bar or toast
    const config = vscode.workspace.getConfiguration('aeroBridge');
    if (config.get<boolean>('showNotifications', true)) {
      vscode.window.setStatusBarMessage(`$(zap) Aero: Executed '${action}'`, 4000);
    }

  } catch (err: any) {
    const errorMessage = err?.message || String(err);
    log(`❌ Execution error for action '${action}': ${errorMessage}`);

    const errorResponse: AeroResponse = {
      status: 'error',
      action: action,
      error: errorMessage,
      timestamp: Date.now()
    };

    sendJson(ws, errorResponse);
  }
}

/**
 * Maps an Aero action to VS Code command(s) and executes it.
 */
async function executeAction(action: string, payload?: any, args?: any[]): Promise<{ commandId: string; message: string; result?: any }> {
  // 1. Check custom user configuration mappings
  const config = vscode.workspace.getConfiguration('aeroBridge');
  const customMap = config.get<Record<string, string>>('customActionMap', {});
  if (customMap[action]) {
    const targetCommand = customMap[action];
    log(`Executing mapped command '${targetCommand}' for action '${action}'...`);
    const cmdArgs = args ?? (payload !== undefined ? [payload] : []);
    const res = await vscode.commands.executeCommand(targetCommand, ...cmdArgs);
    return {
      commandId: targetCommand,
      message: `Executed custom mapped command: ${targetCommand}`,
      result: res
    };
  }

  // 2. Built-in action resolvers
  const availableCommands = new Set(await vscode.commands.getCommands(true));

  switch (action) {
    case 'trigger_review': {
      // Prioritized list of review commands
      const candidateCommands = [
        'antigravity.review',
        'antigravity.codeReview',
        'workbench.action.chat.openReview',
        'workbench.action.chat.open'
      ];

      const commandToRun = candidateCommands.find(cmd => availableCommands.has(cmd));

      if (commandToRun) {
        log(`Running review command: ${commandToRun}`);
        let cmdArg: any = undefined;
        if (payload) {
          cmdArg = typeof payload === 'string' ? { query: `Review this code: ${payload}` } : payload;
        } else {
          cmdArg = { query: 'Review the current file for issues and optimizations.' };
        }
        const res = await vscode.commands.executeCommand(commandToRun, cmdArg);
        return {
          commandId: commandToRun,
          message: `Triggered code review using '${commandToRun}'`,
          result: res
        };
      }

      // Fallback: If no AI review command found, open chat panel or show active document notification
      const fallbackChat = 'workbench.action.chat.open';
      if (availableCommands.has(fallbackChat)) {
        const res = await vscode.commands.executeCommand(fallbackChat, { query: 'Review this file' });
        return {
          commandId: fallbackChat,
          message: 'Opened Chat panel for code review',
          result: res
        };
      }

      // If active editor exists, notify
      const editor = vscode.window.activeTextEditor;
      const fileName = editor ? editor.document.fileName : 'No file open';
      vscode.window.showInformationMessage(`[Aero Voice] Trigger Review received for: ${fileName}`);
      return {
        commandId: 'vscode.window.showInformationMessage',
        message: `Review requested for ${fileName}`
      };
    }

    case 'trigger_chat': {
      // Prioritized list of chat commands
      const candidateCommands = [
        'antigravity.openChat',
        'antigravity.focus',
        'workbench.action.chat.open',
        'workbench.action.quickChat.toggle'
      ];

      const commandToRun = candidateCommands.find(cmd => availableCommands.has(cmd));

      if (commandToRun) {
        log(`Opening chat via: ${commandToRun}`);
        let cmdArg: any = undefined;
        if (payload) {
          cmdArg = typeof payload === 'string' ? { query: payload } : payload;
        }
        const res = await vscode.commands.executeCommand(commandToRun, cmdArg);
        return {
          commandId: commandToRun,
          message: `Chat opened via '${commandToRun}'`,
          result: res
        };
      }

      vscode.window.showInformationMessage(`[Aero Voice] Chat triggered with prompt: ${payload || '(none)'}`);
      return {
        commandId: 'vscode.window.showInformationMessage',
        message: 'Chat triggered'
      };
    }

    // Additional common editor voice actions
    case 'save':
    case 'save_file': {
      await vscode.commands.executeCommand('workbench.action.files.save');
      return { commandId: 'workbench.action.files.save', message: 'Current file saved' };
    }

    case 'save_all': {
      await vscode.commands.executeCommand('workbench.action.files.saveAll');
      return { commandId: 'workbench.action.files.saveAll', message: 'All files saved' };
    }

    case 'format_document':
    case 'format': {
      await vscode.commands.executeCommand('editor.action.formatDocument');
      return { commandId: 'editor.action.formatDocument', message: 'Document formatted' };
    }

    case 'toggle_terminal':
    case 'terminal': {
      await vscode.commands.executeCommand('workbench.action.terminal.toggleTerminal');
      return { commandId: 'workbench.action.terminal.toggleTerminal', message: 'Terminal toggled' };
    }

    case 'quick_open': {
      await vscode.commands.executeCommand('workbench.action.quickOpen');
      return { commandId: 'workbench.action.quickOpen', message: 'Quick Open triggered' };
    }

    case 'command_palette': {
      await vscode.commands.executeCommand('workbench.action.showCommands');
      return { commandId: 'workbench.action.showCommands', message: 'Command Palette opened' };
    }

    default: {
      // 3. Direct execution: If the action is already an exact registered VS Code command ID
      if (availableCommands.has(action)) {
        log(`Executing exact VS Code command: ${action}`);
        const cmdArgs = args ?? (payload !== undefined ? [payload] : []);
        const res = await vscode.commands.executeCommand(action, ...cmdArgs);
        return {
          commandId: action,
          message: `Executed command: ${action}`,
          result: res
        };
      }

      // If action wasn't found
      throw new Error(
        `Unknown action '${action}'. Configure it in 'aeroBridge.customActionMap' or send a valid VS Code command ID.`
      );
    }
  }
}

/**
 * Sends a JSON string to a WebSocket client.
 */
function sendJson(ws: WebSocket, data: AeroResponse) {
  if (ws.readyState === WebSocket.OPEN) {
    const jsonStr = JSON.stringify(data);
    ws.send(jsonStr);
    log(`📤 Replied: ${jsonStr}`);
  }
}

/**
 * Logs messages to the Aero Bridge OutputChannel and console.
 */
function log(msg: string) {
  const timestamp = new Date().toLocaleTimeString();
  const line = `[${timestamp}] ${msg}`;
  outputChannel.appendLine(line);
  console.log(`[Aero Bridge] ${line}`);
}

/**
 * Updates the status bar UI.
 */
function updateStatusBar(status: 'running' | 'stopped' | 'starting' | 'error', errorDetail?: string) {
  switch (status) {
    case 'running':
      statusBarItem.text = `$(radio-tower) Aero: ${currentPort}`;
      statusBarItem.tooltip = `Aero Bridge: Active on ws://localhost:${currentPort}\nConnected clients: ${connectedClientsCount}\nClick to view options`;
      statusBarItem.backgroundColor = undefined;
      statusBarItem.show();
      break;
    case 'starting':
      statusBarItem.text = `$(sync~spin) Aero: Starting...`;
      statusBarItem.tooltip = `Aero Bridge: Initializing server on port ${currentPort}...`;
      statusBarItem.show();
      break;
    case 'stopped':
      statusBarItem.text = `$(circle-slash) Aero: Stopped`;
      statusBarItem.tooltip = `Aero Bridge: Server stopped. Click to start.`;
      statusBarItem.show();
      break;
    case 'error':
      statusBarItem.text = `$(error) Aero: Error`;
      statusBarItem.tooltip = `Aero Bridge: ${errorDetail || 'Error occurred'}. Click for options.`;
      statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
      statusBarItem.show();
      break;
  }
}

/**
 * Shows interactive quick pick menu when clicking the status bar item.
 */
async function showStatusQuickPick() {
  const isRunning = wss !== null;
  const items: vscode.QuickPickItem[] = [
    {
      label: isRunning ? '$(stop) Stop Server' : '$(play) Start Server',
      description: isRunning ? `Stop server on port ${currentPort}` : `Start server on port ${currentPort}`,
      detail: isRunning ? 'Stops listening for Aero voice commands' : 'Starts listening on ws://localhost:' + currentPort
    },
    {
      label: '$(sync) Restart Server',
      description: `Restart server on port ${currentPort}`,
      detail: 'Re-binds the WebSocket port'
    },
    {
      label: '$(output) Show Output Logs',
      description: 'Open the Aero Bridge output channel',
      detail: 'View connection and message history'
    },
    {
      label: '$(gear) Configure Port',
      description: `Current port: ${currentPort}`,
      detail: 'Change the listening port in settings'
    }
  ];

  const selected = await vscode.window.showQuickPick(items, {
    placeHolder: `Aero Bridge Status: ${isRunning ? `Active (ws://localhost:${currentPort}, ${connectedClientsCount} clients)` : 'Stopped'}`
  });

  if (!selected) {
    return;
  }

  if (selected.label.includes('Start Server')) {
    await startServer(currentPort);
  } else if (selected.label.includes('Stop Server')) {
    stopServer();
  } else if (selected.label.includes('Restart Server')) {
    stopServer();
    await startServer(currentPort);
  } else if (selected.label.includes('Show Output Logs')) {
    outputChannel.show();
  } else if (selected.label.includes('Configure Port')) {
    const input = await vscode.window.showInputBox({
      prompt: 'Enter new port for Aero Bridge WebSocket server',
      value: String(currentPort)
    });
    if (input && !isNaN(Number(input))) {
      const newPort = Number(input);
      await vscode.workspace.getConfiguration('aeroBridge').update('port', newPort, vscode.ConfigurationTarget.Global);
      stopServer();
      await startServer(newPort);
    }
  }
}

