"""
test_bridge.py - Quick test client to verify Aero Bridge WebSocket server.
Sends sample commands to ws://localhost:8765 and prints responses.
"""
import asyncio
import json
import websockets

URI = "ws://localhost:8766"

async def test_action(action, payload=None):
    print(f"\n--- Testing action: '{action}' ---")
    try:
        async with websockets.connect(URI) as websocket:
            msg = {"action": action, "payload": payload}
            print(f"📤 Sending: {json.dumps(msg)}")
            await websocket.send(json.dumps(msg))
            response = await websocket.recv()
            print(f"📥 Received from VS Code: {response}")
            res_data = json.loads(response)
            if res_data.get("status") == "success":
                print(f"✅ Success! Executed: {res_data.get('command')}")
            else:
                print(f"⚠️ Error response: {res_data.get('error')}")
    except ConnectionRefusedError:
        print("❌ Connection refused! Ensure the Aero Bridge extension is active in VS Code.")
    except Exception as e:
        print(f"❌ Error: {e}")

async def main():
    print("🛰️ Connecting to Aero Bridge at", URI)
    # Test 1: trigger_chat
    await test_action("trigger_chat", "Hello Antigravity! Can you help explain this file?")
    await asyncio.sleep(1)

    # Test 2: trigger_review
    await test_action("trigger_review", "Please check for memory leaks or syntax bugs.")
    await asyncio.sleep(1)

    # Test 3: direct VS Code command
    await test_action("save")

if __name__ == "__main__":
    asyncio.run(main())

