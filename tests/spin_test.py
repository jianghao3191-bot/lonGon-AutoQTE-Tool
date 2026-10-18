import sys
from pathlib import Path

sys.path.insert(0, r"D:\lonGon-AutoQTE-Tool\src")
from PySide6.QtWidgets import QApplication, QSpinBox  # noqa: E402

from longon_qte.theme import build_qss  # noqa: E402

app = QApplication([])
base = build_qss(Path(r"D:\lonGon-AutoQTE-Tool\assets"))

app.setStyleSheet(base)
s = QSpinBox(); s.setRange(0, 100); s.setValue(42); s.resize(150, 30); s.show()
app.processEvents()
print("default buttons   :", s.lineEdit().geometry())

app.setStyleSheet(base + "\nQSpinBox::up-button,QSpinBox::down-button{width:0px;border:none;background:transparent;}")
s = QSpinBox(); s.setRange(0, 100); s.setValue(42); s.resize(150, 30); s.show()
app.processEvents()
print("qss width 0       :", s.lineEdit().geometry(), s.sizeHint())

app.setStyleSheet(base)
s = QSpinBox(); s.setButtonSymbols(QSpinBox.NoButtons); s.setRange(0, 100); s.setValue(42)
s.resize(150, 30); s.show()
app.processEvents()
print("NoButtons + qss   :", s.lineEdit().geometry())

app.setStyleSheet("")
s = QSpinBox(); s.setButtonSymbols(QSpinBox.NoButtons); s.setRange(0, 100); s.setValue(42)
s.resize(150, 30); s.show()
app.processEvents()
print("NoButtons no qss  :", s.lineEdit().geometry())
app.quit()
