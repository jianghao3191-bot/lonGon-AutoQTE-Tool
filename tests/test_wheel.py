"""验证：滚轮划过未聚焦的数值框不会改数；聚焦后才生效。"""

import sys
from pathlib import Path

sys.path.insert(0, r"D:\lonGon-AutoQTE-Tool\src")
from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from longon_qte.main_window import MainWindow  # noqa: E402
from longon_qte.theme import build_qss  # noqa: E402

app = QApplication([])
app.setStyleSheet(build_qss(Path(r"D:\lonGon-AutoQTE-Tool\assets")))
w = MainWindow()
w.show()
app.processEvents()


def wheel(target, delta: int) -> None:
    pos = QPointF(10, 10)
    ev = QWheelEvent(pos, target.mapToGlobal(QPoint(10, 10)),
                     QPoint(0, 0), QPoint(0, delta),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(target, ev)


for name in ("w_white", "w_offx", "w_lead", "w_hole" if False else "w_hold"):
    sb = getattr(w, name)
    before = sb.value()
    w.setFocus()                       # 焦点在主窗口，不在输入框
    app.processEvents()
    wheel(sb, -120)
    wheel(sb, -120)
    app.processEvents()
    ok = sb.value() == before
    print(f"{name}: 未聚焦滚轮 -> {before} => {sb.value()}  {'OK' if ok else 'FAIL'}")

sb = w.w_white
sb.setFocus()
app.processEvents()
before = sb.value()
wheel(sb, -120)
app.processEvents()
print(f"w_white: 聚焦后滚轮 -> {before} => {sb.value()}  "
      f"{'OK' if sb.value() != before else 'FAIL'}")

# 拖动窗口时暂停预览不应崩
w._on_window_moving(True)
w._tick()
w._on_window_moving(False)
w._tick()
print("drag pause: OK")
app.quit()
