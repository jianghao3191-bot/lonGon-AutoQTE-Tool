"""配色与样式表。

参考的是大厂后台工具那套：低饱和深色、单一强调色、克制的高光，
靠字号/字重/间距分层，而不是靠花哨的渐变和阴影。
"""

from __future__ import annotations

from pathlib import Path

BG = "#08090c"
SURFACE = "#101216"
SURFACE_2 = "#151920"
SURFACE_3 = "#1a1f28"
LINE = "#1b2029"
LINE_HI = "#272e3b"
TEXT = "#eef1f6"
DIM = "#98a2b3"
MUTE = "#5f6878"
ACCENT = "#3ddc97"
ACCENT_DK = "#123326"
WARN = "#f5c451"
ERR = "#f2707c"
BLUE = "#6aa8ff"

FONT_UI = "Microsoft YaHei UI"
FONT_MONO = "Consolas"


def build_qss(assets: Path | None = None) -> str:
    """assets 目录里放着两个小图标（下拉箭头、勾），没有就退回纯色样式。"""
    arrow = ""
    check = ""
    if assets:
        p1 = (assets / "chevron-down.png").as_posix()
        p2 = (assets / "check.png").as_posix()
        if (assets / "chevron-down.png").is_file():
            arrow = f'image: url("{p1}"); width: 11px; height: 11px;'
        if (assets / "check.png").is_file():
            check = f'image: url("{p2}");'

    return f"""
* {{
    font-family: "{FONT_UI}";
    font-size: 9pt;
    color: {TEXT};
    outline: none;
}}

QWidget#Root {{ background: {BG}; }}

QFrame#Card {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 16px;
}}

QLabel#CardTitle {{
    color: {DIM};
    font-size: 8.5pt;
    font-weight: 600;
}}

QLabel#AppTitle {{
    font-size: 12.5pt;
    font-weight: 700;
    color: {TEXT};
}}

QLabel#AppMeta {{
    color: {MUTE};
    font-size: 8.5pt;
}}

QLabel#Signature {{
    color: {MUTE};
    font-size: 8.5pt;
}}

QLabel#Key {{
    color: {DIM};
    font-size: 8.5pt;
}}

QLabel#Value {{
    color: {TEXT};
    font-size: 8.5pt;
}}

QLabel#ValueMono {{
    font-family: "{FONT_MONO}";
    font-size: 9pt;
    color: {TEXT};
}}

QLabel#Hint {{
    color: {MUTE};
    font-size: 8pt;
}}

QLabel#Readout {{
    font-family: "{FONT_MONO}";
    font-size: 9.5pt;
    color: {DIM};
}}
QLabel#ReadoutGood {{ font-family: "{FONT_MONO}"; font-size: 9.5pt; color: {ACCENT}; }}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 5px 12px;
    color: {DIM};
}}
QPushButton:hover {{ color: {TEXT}; background: {SURFACE_3}; }}
QPushButton:pressed {{ background: #222834; }}

QPushButton#Primary {{
    background: {ACCENT};
    color: #04140d;
    border: none;
    border-radius: 10px;
    font-size: 9.5pt;
    font-weight: 700;
    padding: 0 20px;
}}
QPushButton#Primary:hover {{ background: #4ae7a5; }}
QPushButton#Primary:pressed {{ background: #2fc384; }}

QPushButton#Danger {{
    background: #2a1418;
    color: {ERR};
    border: 1px solid #4a222a;
    border-radius: 10px;
    font-size: 9.5pt;
    font-weight: 700;
    padding: 0 20px;
}}
QPushButton#Danger:hover {{ background: #35191e; border-color: #63303a; }}

QPushButton#Ghost {{
    background: {SURFACE_2};
    color: {DIM};
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 4px 10px;
}}
QPushButton#Ghost:hover {{ color: {TEXT}; border-color: {LINE_HI}; }}
QPushButton#Ghost:checked {{
    color: {ACCENT};
    border-color: #2b5c46;
    background: #0f201a;
}}

QPushButton#Link {{
    background: transparent;
    border: none;
    color: {MUTE};
    padding: 2px 4px;
    font-size: 8.5pt;
}}
QPushButton#Link:hover {{ color: {TEXT}; }}

/* ---------- 输入控件 ---------- */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {SURFACE_2};
    border: 1px solid {LINE};
    border-radius: 9px;
    padding: 3px 9px;
    min-height: 20px;
    selection-background-color: {ACCENT_DK};
    selection-color: {TEXT};
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{
    border-color: {LINE_HI};
}}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border-color: #2f6b52;
    background: #131a19;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}}
QComboBox::down-arrow {{ {arrow} }}
QComboBox QAbstractItemView {{
    background: {SURFACE_3};
    border: 1px solid {LINE_HI};
    border-radius: 10px;
    padding: 4px;
    selection-background-color: {ACCENT_DK};
    outline: none;
}}
/* 上下箭头是整个隐藏掉的：宽度给 0 才不会被 Qt 把输入区压成 1px */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px;
    border: none;
    background: transparent;
}}

/* ---------- 复选框 ---------- */
QCheckBox {{
    color: {DIM};
    spacing: 8px;
    padding: 2px 0;
}}
QCheckBox:hover {{ color: {TEXT}; }}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid {LINE_HI};
    background: {SURFACE_2};
}}
QCheckBox::indicator:hover {{ border-color: {DIM}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    {check}
}}

/* ---------- 滚动 ---------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #2a3141;
    border-radius: 3px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: #39445a; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

/* ---------- 日志 ---------- */
QPlainTextEdit#Log {{
    background: #0b0d11;
    border: 1px solid {LINE};
    border-radius: 10px;
    padding: 6px 9px;
    font-family: "{FONT_MONO}";
    font-size: 8.5pt;
    color: {DIM};
    selection-background-color: {ACCENT_DK};
    selection-color: {TEXT};
}}
QPlainTextEdit#Log QScrollBar:vertical {{ width: 0px; }}

QToolTip {{
    background: {SURFACE_3};
    color: {TEXT};
    border: 1px solid {LINE_HI};
    border-radius: 8px;
    padding: 6px 9px;
    font-size: 8.5pt;
}}

QMenu {{
    background: {SURFACE_3};
    border: 1px solid {LINE_HI};
    border-radius: 10px;
    padding: 5px;
}}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {SURFACE_2}; }}
"""


QSS = build_qss(Path(__file__).resolve().parents[2] / "assets")
