import os, subprocess, sys, time
from pathlib import Path

ROOT = Path(r"D:\lonGon-AutoQTE-Tool")
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from longon_qte import winutil
winutil.enable_dpi_awareness()

from longon_qte.config import Settings
from longon_qte.capture import Capture
from longon_qte.detector import QteDetector, DetectorConfig

env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), TMP=str(ROOT / ".tmp"),
           TEMP=str(ROOT / ".tmp"), PYTHONIOENCODING="utf-8")
py = str(ROOT / ".venv" / "Scripts" / "python.exe")
sim = subprocess.Popen([py, "-m", "longon_qte.sim.qte_sim", "--speed", "120",
                        "--zone", "24"], cwd=str(ROOT), env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

s = Settings()
s.capture_mode = "dxgi"; s.crop_size = 224
cap = Capture(s); cap.open()
frames = []
t0 = time.time()
while time.time() - t0 < 4 and len(frames) < 30:
    f, ts = cap.grab()
    if f is not None:
        frames.append(f.copy())
cap.close()
print("frames:", len(frames), "rect:", s.crop_size)

f = frames[-1]
from PySide6.QtGui import QImage
h, w = f.shape[:2]
img = QImage(f.tobytes(), w, h, w * 4, QImage.Format_ARGB32).copy()
img.save(str(ROOT / "build" / "frame.png"))

det = QteDetector(224)
det.configure(DetectorConfig())
res = None
for fr in frames[-8:]:
    res = det.update(fr)
print("result:", res)
print("zone_px:", det.zone_px, "band_n:", det.band_n, "z_n:", det.z_n, "zr0:", det.zr0)

# 鍙犲姞鍥撅細鐧?鐧芥帺鐮侊紝缁?闈欐€?鐧藉尯)
import numpy as np
ov = f[..., :3].copy()
ov[det.last_white] = (0, 220, 255)
ov[det.last_zone_full] = (0, 255, 0)
img2 = QImage(ov.tobytes(), w, h, w * 3, QImage.Format_BGR888).copy()
img2.save(str(ROOT / "build" / "frame_overlay.png"))
sim.terminate()
print("saved")

