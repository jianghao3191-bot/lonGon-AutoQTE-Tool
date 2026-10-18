"""自绘控件：卡片、检测画面、进度条、大数字、日志。"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QImage, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout,
                               QLabel, QPlainTextEdit, QSizePolicy, QSpinBox,
                               QVBoxLayout, QWidget)

from .theme import (ACCENT, BG, BLUE, DIM, FONT_MONO, FONT_UI, LINE, LINE_HI,
                    MUTE, SURFACE, SURFACE_2, TEXT, WARN)


# --------------------------------------------------------------------------- #
# 滚轮保护：只有控件已经有焦点时，滚轮才改数值，否则把滚轮让给页面滚动
# --------------------------------------------------------------------------- #
class _NoWheel:
    def wheelEvent(self, e):  # noqa: N802
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class SpinBox(_NoWheel, QSpinBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setKeyboardTracking(False)


class DoubleSpinBox(_NoWheel, QDoubleSpinBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setKeyboardTracking(False)


class ComboBox(_NoWheel, QComboBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # 默认是 WheelFocus，滚一下就会抢焦点并改值，这里改成必须点击/键盘
        self.setFocusPolicy(Qt.StrongFocus)


# --------------------------------------------------------------------------- #
class Card(QFrame):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        head.addWidget(self.title)
        head.addStretch(1)
        self.head_extra = head
        outer.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8)
        outer.addLayout(self.body, 1)


class Meter(QWidget):
    """标签 + 数值 + 一根 3px 的进度线。"""

    def __init__(self, label: str, color: str = ACCENT, parent=None) -> None:
        super().__init__(parent)
        self._label = label
        self._color = QColor(color)
        self._value = 0.0
        self._text = "--"
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, v: float, text: str = "") -> None:
        v = max(0.0, min(1.0, float(v)))
        t = text or f"{v * 100:.0f}%"
        if abs(v - self._value) > 0.003 or t != self._text:
            self._value = v
            self._text = t
            self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setFont(QFont(FONT_UI, 8))
        p.setPen(QColor(DIM))
        p.drawText(QRect(0, 0, w - 60, 18), Qt.AlignLeft | Qt.AlignVCenter, self._label)
        p.setFont(QFont(FONT_MONO, 8))
        p.setPen(QColor(TEXT if self._value > 0.02 else MUTE))
        p.drawText(QRect(w - 60, 0, 60, 18), Qt.AlignRight | Qt.AlignVCenter, self._text)

        track = QRectF(0, 24, w, 3)
        path = QPainterPath()
        path.addRoundedRect(track, 1.5, 1.5)
        p.fillPath(path, QColor(SURFACE_2))
        if self._value > 0:
            fill = QRectF(0, 24, max(3.0, w * self._value), 3)
            fp = QPainterPath()
            fp.addRoundedRect(fill, 1.5, 1.5)
            p.fillPath(fp, self._color)


class Stat(QWidget):
    """一个大数字 + 一行说明。"""

    def __init__(self, caption: str, unit: str = "", parent=None) -> None:
        super().__init__(parent)
        self._caption = caption
        self._unit = unit
        self._value = "--"
        self._color = TEXT
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(52)

    def set_value(self, text: str, color: str = TEXT) -> None:
        if text != self._value or color != self._color:
            self._value = text
            self._color = color
            self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(FONT_MONO)
        f.setPixelSize(21)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(self._color))
        p.drawText(QRect(0, 0, self.width(), 30), Qt.AlignLeft | Qt.AlignVCenter, self._value)

        p.setFont(QFont(FONT_UI, 8))
        p.setPen(QColor(MUTE))
        p.drawText(QRect(0, 30, self.width(), 18), Qt.AlignLeft | Qt.AlignVCenter, self._caption)


class Preview(QWidget):
    """检测画面：原始帧 + 识别叠加层。"""

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._img: Optional[QImage] = None
        self._thumb: Optional[QPixmap] = None
        self._mask_img: Optional[QImage] = None
        self._thumb_w = -1
        self._fast = False
        self.result = None
        self.prediction = None
        self.show_overlay = True
        self.show_mask = False
        self._placeholder = "等待画面"

    # ------------------------------------------------------------------ #
    def set_frame(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        self._img = QImage(frame.tobytes(), w, h, w * 4,
                           QImage.Format_ARGB32).copy()
        self._thumb = None
        self._thumb_w = -1
        self.update()

    def set_result(self, result, prediction) -> None:
        self.result = result
        self.prediction = prediction
        self.update()

    def set_masks(self, white: Optional[np.ndarray], zone: Optional[np.ndarray]) -> None:
        self._mask_img = None
        if not self.show_mask or white is None:
            return
        h, w = white.shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[white] = (255, 226, 90, 46)
        if zone is not None:
            rgba[zone] = (90, 255, 140, 100)
        self._mask_img = QImage(rgba.tobytes(), w, h, w * 4,
                                QImage.Format_ARGB32).copy()

    def set_overlay(self, on: bool) -> None:
        self.show_overlay = on
        self.update()

    def set_show_mask(self, on: bool) -> None:
        self.show_mask = on
        self._mask_img = None
        self.update()

    def set_fast(self, fast: bool) -> None:
        """拖动窗口时用最近邻缩放，省掉平滑缩放的开销。"""
        self._fast = fast
        if fast:
            self._thumb = None

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.update()

    # ------------------------------------------------------------------ #
    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, w: int) -> int:  # noqa: N802
        return int(w)

    def _square(self) -> QRect:
        side = min(self.width(), self.height())
        return QRect((self.width() - side) // 2, (self.height() - side) // 2, side, side)

    def _ensure_thumb(self) -> None:
        if self._img is None:
            return
        sq = self._square()
        if self._thumb is not None and self._thumb_w == sq.width():
            return
        mode = Qt.FastTransformation if self._fast else Qt.SmoothTransformation
        self._thumb = QPixmap.fromImage(
            self._img.scaled(sq.width(), sq.height(), Qt.IgnoreAspectRatio, mode))
        self._thumb_w = sq.width()

    def resizeEvent(self, e) -> None:  # noqa: N802
        self._thumb = None
        self._thumb_w = -1
        super().resizeEvent(e)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    # ------------------------------------------------------------------ #
    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(SURFACE))
        p.setRenderHint(QPainter.Antialiasing)

        sq = self._square()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(sq), 12, 12)
        p.setClipPath(clip)
        p.fillPath(clip, QColor("#07080b"))

        self._ensure_thumb()
        if self._thumb is not None:
            p.drawPixmap(sq, self._thumb)
            if self.show_mask and self._mask_img is not None:
                mode = Qt.FastTransformation if self._fast else Qt.SmoothTransformation
                p.drawPixmap(sq, QPixmap.fromImage(self._mask_img.scaled(
                    sq.width(), sq.height(), Qt.IgnoreAspectRatio, mode)))
            if self.show_overlay:
                self._paint_overlay(p, sq)
        else:
            self._paint_empty(p, sq)

        p.setClipping(False)
        p.setPen(QPen(QColor(LINE), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(sq).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)

    def _paint_empty(self, p: QPainter, sq: QRect) -> None:
        cx, cy = sq.center().x(), sq.center().y()
        r = min(sq.width(), sq.height()) * 0.13
        p.setPen(QPen(QColor(LINE_HI), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(QColor(MUTE), 1.2))
        p.drawLine(QPointF(cx - r * 0.7, cy), QPointF(cx + r * 0.7, cy))
        p.drawLine(QPointF(cx, cy - r * 0.7), QPointF(cx, cy + r * 0.7))
        p.setPen(QColor(MUTE))
        p.setFont(QFont(FONT_UI, 9))
        p.drawText(QRect(sq.left(), int(cy + r + 14), sq.width(), 24),
                   Qt.AlignHCenter | Qt.AlignTop, self._placeholder)

    def _paint_overlay(self, p: QPainter, sq: QRect) -> None:
        cx = sq.center().x() + 0.5
        cy = sq.center().y() + 0.5
        R = sq.width() / 2.0
        res = self.result

        p.setPen(QPen(QColor(120, 130, 150, 60), 1, Qt.DashLine))
        inner = R * 0.55
        p.drawEllipse(QPointF(cx, cy), inner, inner)

        if res is not None and res.zone_start_deg is not None and res.zone_len_deg is not None:
            a0 = math.radians(res.zone_start_deg)
            a1 = a0 + math.radians(res.zone_len_deg)
            r0, r1 = R * 0.80, R * 0.99
            steps = max(12, int(res.zone_len_deg * 2))
            pts = []
            for i in range(steps + 1):
                a = a0 + (a1 - a0) * i / steps
                pts.append(QPointF(cx + math.cos(a) * r1, cy + math.sin(a) * r1))
            for i in range(steps, -1, -1):
                a = a0 + (a1 - a0) * i / steps
                pts.append(QPointF(cx + math.cos(a) * r0, cy + math.sin(a) * r0))
            path = QPainterPath()
            path.moveTo(pts[0])
            for q in pts[1:]:
                path.lineTo(q)
            path.closeSubpath()
            c = QColor(ACCENT)
            c.setAlpha(60)
            p.fillPath(path, c)
            p.setPen(QPen(QColor(ACCENT), 1.2))
            p.drawPath(path)

        if res is not None and res.needle_deg is not None:
            a = math.radians(res.needle_deg)
            p.setPen(QPen(QColor(255, 255, 255, 230), 2.0, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx + math.cos(a) * R * 0.30, cy + math.sin(a) * R * 0.30),
                       QPointF(cx + math.cos(a) * R * 0.97, cy + math.sin(a) * R * 0.97))
            p.setBrush(QColor(255, 255, 255, 240))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx + math.cos(a) * R * 0.97,
                                  cy + math.sin(a) * R * 0.97), 2.8, 2.8)

        pred = self.prediction
        if pred is not None and res is not None and res.zone_center_deg is not None:
            a = math.radians(res.zone_center_deg)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(ACCENT), 1.3))
            p.drawEllipse(QPointF(cx + math.cos(a) * R * 0.90,
                                  cy + math.sin(a) * R * 0.90), 4.5, 4.5)


class LogView(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Log")
        self.setReadOnly(True)
        self.setMaximumBlockCount(400)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFont(QFont(FONT_MONO, 8))

    def add(self, text: str, level: str = "info") -> None:
        color = {"info": DIM, "ok": ACCENT, "warn": WARN, "error": "#f2707c"}.get(level, DIM)
        self.appendHtml(f'<span style="color:{color}">{_esc(text)}</span>')
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class PreviewWindow(QWidget):
    """无边框置顶的纯净预览窗，OBS 可直接窗口采集。"""

    def __init__(self, parent=None) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setStyleSheet(f"background:{SURFACE};")
        self.setWindowTitle("lonGon-AutoQTE-Tool 纯净预览")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = Preview(self)
        self.view.show_overlay = False
        lay.addWidget(self.view)
        self.resize(320, 320)
        self._drag = None

    def set_frame(self, frame: np.ndarray) -> None:
        self.view.set_frame(frame)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._drag = None
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.hide()
        super().keyPressEvent(e)
