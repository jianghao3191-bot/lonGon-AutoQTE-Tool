import sys
from pathlib import Path

ROOT = Path(r"D:\lonGon-AutoQTE-Tool")
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from longon_qte.theme import build_qss  # noqa: E402
from longon_qte.main_window import MainWindow  # noqa: E402

app = QApplication(sys.argv)
app.setStyleSheet(build_qss(ROOT / "assets"))
w = MainWindow()
w.show()
w.raise_()


def shot():
    out = ROOT / "build" / "ui.png"
    w.grab().save(str(out))
    print("saved", out, w.size())
    app.quit()


QTimer.singleShot(1500, shot)
sys.exit(app.exec())
