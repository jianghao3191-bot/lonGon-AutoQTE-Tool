import ctypes, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(r"D:\lonGon-AutoQTE-Tool")
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from longon_qte import winutil
winutil.enable_dpi_awareness()
winutil.begin_high_res_timer()

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from longon_qte.theme import QSS
from longon_qte.main_window import MainWindow

user32 = ctypes.windll.user32
env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), TMP=str(ROOT / ".tmp"),
           TEMP=str(ROOT / ".tmp"), PYTHONIOENCODING="utf-8")
py = str(ROOT / ".venv" / "Scripts" / "python.exe")
sim = subprocess.Popen([py, "-m", "longon_qte.sim.qte_sim", "--speed", "150",
                        "--zone", "22", "--accel-after", "8"],
                       cwd=str(ROOT), env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.0)

app = QApplication(sys.argv)
app.setStyleSheet(QSS)
w = MainWindow()
w.w_window.setText("QTE 模拟器")
w.w_target.setText("QTE 模拟器")
w.w_fg_only.setChecked(True)
w._on_change()
w.show()

hwnd = winutil.find_window("QTE 模拟器")
if hwnd:
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)

w.start()

def shot():
    out = ROOT / "build" / "ui_live.png"
    w.grab().save(str(out))
    print("saved", out)
    print("snap:", w.engine.snapshot().frames, w.engine.snapshot().presses)
    w.stop()
    app.quit()

QTimer.singleShot(7000, shot)
rc = app.exec()
sim.terminate()
sys.exit(rc)
