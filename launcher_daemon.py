import os, time, socket, ctypes, subprocess

_lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    _lock.bind(("127.0.0.1", 59422))
except socket.error:
    os._exit(0)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYW = os.path.join(BASE_DIR, "venv", "Scripts", "pythonw.exe")
MAIN_PY = os.path.join(BASE_DIR, "main.py")
CREATE_NO_WINDOW = 0x08000000

def is_aero_main_locked() -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 59421))
        s.close()
        return False
    except socket.error:
        return True

VK_MENU, VK_A = 0x12, 0x41
last_boot = 0.0
while True:
    try:
        if bool(ctypes.windll.user32.GetAsyncKeyState(VK_MENU) & 0x8000) and bool(ctypes.windll.user32.GetAsyncKeyState(VK_A) & 0x8000):
            if time.time() - last_boot > 3.0 and not is_aero_main_locked():
                last_boot = time.time()
                subprocess.Popen([PYW, MAIN_PY], cwd=BASE_DIR, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass
    time.sleep(0.04)
