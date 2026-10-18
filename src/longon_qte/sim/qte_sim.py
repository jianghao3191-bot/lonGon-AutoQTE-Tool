"""QTE 模拟器：验证 lonGon-AutoQTE-Tool 端到端是否真的能打中完美区。

用法：
    python -m longon_qte.sim.qte_sim            # 默认 150°/s，50 次后提速
    python -m longon_qte.sim.qte_sim --speed 220 --zone 18 --accel-after 20

窗口居中显示，中心 224x224 就是工具截图区域；统计数字放在四角，
不会被 224 的截图框读到，所以不会干扰识别。
"""

from __future__ import annotations

import argparse
import math
import sys
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

BG = QColor(16, 18, 22)
WHITE = QColor(255, 255, 255)
GRAY = QColor(80, 80, 80)
ACCENT = QColor(61, 220, 132)
ERR = QColor(240, 97, 109)


class Sim(QWidget):
    def __init__(self, speed: float, zone_deg: float, accel_after: int) -> None:
        super().__init__()
        self.setWindowTitle("QTE 模拟器 · lonGon")
        # 必须无边框：否则标题栏会让客户区整体下移，和"屏幕中心 224"截图框错位
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(560, 560)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

        self.base_speed = speed
        self.speed = speed
        self.zone_deg = zone_deg
        self.accel_after = accel_after

        self.t0 = time.perf_counter()
        self.angle = 0.0
        self.zone_start = math.radians(-60.0)
        self.active = True
        self.next_at = 0.0
        self.last_report = 0.0

        self.hits = 0
        self.perfect = 0
        self.tries = 0
        self.last_err = None
        self.worst = 0.0
        self.log = []

        self.timer = QTimer(self)
        self.timer.setInterval(4)
        self.timer.timeout.connect(self._step)
        self.timer.start()

        self._new_round()
        scr = self.screen()
        if scr is not None:
            # 用整屏几何中心（不是 availableGeometry），保证和"屏幕中心 224"截图框完全对齐
            c = scr.geometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)

    # ------------------------------------------------------------------ #
    def _new_round(self) -> None:
        self.zone_start = math.radians(-55.0 + (time.time() * 137) % 200.0)
        self.angle = math.radians(-90.0)
        self.t0 = time.perf_counter()
        self.active = True
        self.last_err = None

    def _now_angle(self) -> float:
        return (self.angle + math.radians(self.speed) * (time.perf_counter() - self.t0)) % (2 * math.pi)

    def _step(self) -> None:
        now = time.perf_counter()
        if self.next_at and now >= self.next_at:
            self.next_at = 0.0
            self._new_round()
        if now - self.last_report >= 2.0:
            self.last_report = now
            last = f"{self.last_err:+.2f}" if self.last_err is not None else "--"
            print(f"[sim] hits={self.hits} tries={self.tries} "
                  f"perfect={self.perfect} worst={self.worst:.2f} last={last} "
                  f"speed={self.speed:.0f}", flush=True)
        self.update()

    # ------------------------------------------------------------------ #
    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() != Qt.Key_Space:
            return super().keyPressEvent(e)
        if e.isAutoRepeat() or not self.active:
            return
        self.active = False
        self.tries += 1
        a = self._now_angle()
        z0 = self.zone_start % (2 * math.pi)
        zl = math.radians(self.zone_deg)
        inside = ((a - z0) % (2 * math.pi)) < zl
        err = (a - (z0 + zl / 2) + math.pi) % (2 * math.pi) - math.pi
        self.last_err = math.degrees(err)
        print(f"[sim] press 角度={math.degrees(a) % 360:.1f}° 白区=[{math.degrees(z0):.1f}°,"
              f"{math.degrees(z0 + zl):.1f}°] 误差={self.last_err:+.2f}° {'OK' if inside else 'MISS'}",
              flush=True)
        if inside:
            self.hits += 1
            if abs(err) < math.radians(self.zone_deg) / 2:
                self.perfect += 1
            self.worst = max(self.worst, abs(self.last_err))
        if self.hits >= self.accel_after and self.speed == self.base_speed:
            self.speed = self.base_speed * 1.65
            print(f"[sim] 已打中 {self.hits} 次，指针提速到 {self.speed:.0f}°/s", flush=True)
        self.next_at = time.perf_counter() + 0.28
        self.update()

    # ------------------------------------------------------------------ #
    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), BG)

        # 关键：工具截的是 224 **物理**像素，这里要按 DPI 比例把 QTE 画成
        # 224 物理像素，否则 125% 缩放下会画成 280 物理像素、截不全。
        k = 1.0 / max(1.0, self.devicePixelRatioF())
        side = 224 * k
        cx = self.width() / 2
        cy = self.height() / 2
        R = side / 2
        sq = QRectF(cx - R, cy - R, side, side)

        p.setPen(QPen(QColor(255, 255, 255, 10), 1))
        p.drawRect(sq)

        # 外环
        p.setPen(QPen(GRAY, 3))
        p.drawEllipse(QPointF(cx, cy), R * 0.975, R * 0.975)

        # 完美区（纯白弧带）
        a0 = math.degrees(self.zone_start)
        path = QPainterPath()
        r0, r1 = R * 0.84, R * 0.98
        steps = 24
        pts = []
        for i in range(steps + 1):
            a = math.radians(a0 + self.zone_deg * i / steps)
            pts.append(QPointF(cx + math.cos(a) * r1, cy + math.sin(a) * r1))
        for i in range(steps, -1, -1):
            a = math.radians(a0 + self.zone_deg * i / steps)
            pts.append(QPointF(cx + math.cos(a) * r0, cy + math.sin(a) * r0))
        path.moveTo(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        path.closeSubpath()
        p.fillPath(path, WHITE)

        # 指针
        a = self._now_angle()
        p.setPen(QPen(WHITE, 4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx + math.cos(a) * R * 0.55, cy + math.sin(a) * R * 0.55),
                   QPointF(cx + math.cos(a) * R * 0.97, cy + math.sin(a) * R * 0.97))
        p.setBrush(WHITE)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx + math.cos(a) * R * 0.965,
                              cy + math.sin(a) * R * 0.965), 4.0, 4.0)

        # 中心 Space 键帽（干扰项）
        cap = QRectF(cx - 78 * k, cy - 26 * k, 156 * k, 52 * k)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(235, 235, 235), 2 * k))
        p.drawRoundedRect(cap, 10 * k, 10 * k)
        p.setPen(QColor(255, 255, 255))
        f = QFont("Consolas")
        f.setPixelSize(max(8, int(20 * k * self.devicePixelRatioF())))
        p.setFont(f)
        p.drawText(cap, Qt.AlignCenter, "Space")

        # HUD（在 224 截图框外）
        p.setFont(QFont("Consolas", 10))
        p.setPen(QColor(150, 160, 180))
        p.drawText(16, 26, f"速度 {self.speed:.0f}°/s   白区 {self.zone_deg:.0f}°")
        p.setPen(ACCENT if self.hits else QColor(150, 160, 180))
        p.drawText(16, 48, f"命中 {self.hits} / 尝试 {self.tries}")
        p.setPen(QColor(240, 200, 100))
        p.drawText(16, 70, f"完美 {self.perfect}   最大误差 {self.worst:.2f}°")
        if self.last_err is not None:
            p.setPen(ACCENT if abs(self.last_err) <= self.zone_deg / 2 else ERR)
            p.drawText(16, 92, f"上次误差 {self.last_err:+.2f}°")

        p.setPen(QColor(120, 130, 150))
        p.setFont(QFont("Microsoft YaHei UI", 8))
        p.drawText(16, self.height() - 16,
                   "按空格判定 · 窗口必须在最前 · 截图区域=窗口中心 224x224")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=150.0)
    ap.add_argument("--zone", type=float, default=24.0)
    ap.add_argument("--accel-after", type=int, default=50)
    args = ap.parse_args()
    app = QApplication(sys.argv)
    w = Sim(args.speed, args.zone, args.accel_after)
    w.show()
    w.raise_()
    w.activateWindow()
    w.setFocus()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
