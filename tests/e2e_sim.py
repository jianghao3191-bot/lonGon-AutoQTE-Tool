"""端到端测试：真实截图 + 真实识别 + 真实 SendInput，打到模拟器里。"""

import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(r"D:\lonGon-AutoQTE-Tool")
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from longon_qte import winutil  # noqa: E402

winutil.enable_dpi_awareness()
winutil.begin_high_res_timer()

from longon_qte.config import Settings  # noqa: E402
from longon_qte.engine import Engine  # noqa: E402

user32 = ctypes.windll.user32

SPEED = float(sys.argv[1]) if len(sys.argv) > 1 else 150.0
ZONE = float(sys.argv[2]) if len(sys.argv) > 2 else 24.0
DURATION = float(sys.argv[3]) if len(sys.argv) > 3 else 18.0
ACCEL = int(sys.argv[4]) if len(sys.argv) > 4 else 50

env = dict(os.environ)
env["PYTHONPATH"] = str(ROOT / "src")
env["TMP"] = str(ROOT / ".tmp")
env["TEMP"] = str(ROOT / ".tmp")
env["PYTHONIOENCODING"] = "utf-8"
py = str(ROOT / ".venv" / "Scripts" / "python.exe")

sim = subprocess.Popen(
    [py, "-m", "longon_qte.sim.qte_sim", "--speed", str(SPEED),
     "--zone", str(ZONE), "--accel-after", str(ACCEL)],
    cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    text=True, encoding="utf-8", errors="replace")

lines = []
def _reader():
    for ln in sim.stdout:
        lines.append(ln.rstrip())
        print(ln.rstrip(), flush=True)

threading.Thread(target=_reader, daemon=True).start()

time.sleep(2.5)
hwnd = winutil.find_window("QTE 模拟器")
print("sim hwnd:", hwnd, "fg:", winutil.foreground_title(), flush=True)
if hwnd:
    user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
print("fg after:", winutil.foreground_title(), flush=True)

s = Settings()
s.capture_mode = "dxgi"
s.monitor = 0
s.crop_size = 224
s.key = "space"
s.lead_ms = 6.0
s.horizon_ms = 240
s.cooldown_ms = 260
s.hold_ms = 12
s.only_foreground = True
s.target_title = "QTE 模拟器"
s.detect_only = False
s.min_confidence = 0.45
s.sample_window = 9

eng = Engine()
eng.start(s)
t0 = time.time()
last = 0
try:
    while time.time() - t0 < DURATION:
        time.sleep(0.5)
        snap = eng.snapshot()
        for ts, level, text in eng.drain_logs():
            print(f"[log:{level}] {text}", flush=True)
        if snap.error or not snap.running:
            print(f"!! running={snap.running} status={snap.status} error={snap.error}", flush=True)
            time.sleep(0.2)
            continue
        if time.time() - last >= 2:
            last = time.time()
            print(f"[eng] fps={snap.detect_fps:5.1f} cap={snap.capture_ms:5.3f}ms "
                  f"det={snap.detect_ms:5.3f}ms frames={snap.frames} presses={snap.presses} "
                  f"zone={snap.result.zone_start_deg} needle={snap.result.needle_deg} "
                  f"conf={snap.result.confidence:.2f} pred={None if snap.prediction is None else round(snap.prediction.confidence,2)}",
                  flush=True)
finally:
    eng.stop()
    print("engine stopped", flush=True)
    time.sleep(0.5)
    sim.terminate()
    try:
        sim.wait(timeout=3)
    except Exception:
        sim.kill()
    print("---- sim output ----")
    for ln in lines[-40:]:
        print(ln)
