"""生成图标与界面小图标。"""

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QPainter,
                           QPainterPath, QPen, QPolygonF)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    m = size * 0.06
    rect = QRectF(m, m, size - 2 * m, size - 2 * m)
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.22, size * 0.22)
    p.fillPath(path, QColor("#0e1118"))
    p.setPen(QPen(QColor("#243044"), max(1.0, size * 0.012)))
    p.drawPath(path)

    cx = cy = size / 2
    R = size * 0.30
    ring = QRectF(cx - R, cy - R, 2 * R, 2 * R)
    p.setPen(QPen(QColor("#2c3b52"), max(1.0, size * 0.045)))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(ring)

    p.setPen(QPen(QColor("#e9eef7"), max(1.0, size * 0.085), Qt.SolidLine, Qt.FlatCap))
    p.drawArc(ring, int(-55 * 16), int(58 * 16))

    a = math.radians(-128)
    p.setPen(QPen(QColor("#3ddc97"), max(1.0, size * 0.055), Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(cx + math.cos(a) * R * 0.15, cy + math.sin(a) * R * 0.15),
               QPointF(cx + math.cos(a) * R * 0.98, cy + math.sin(a) * R * 0.98))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#3ddc97"))
    p.drawEllipse(QPointF(cx + math.cos(a) * R * 0.98, cy + math.sin(a) * R * 0.98),
                  size * 0.035, size * 0.035)

    p.setBrush(QColor("#7c8aa0"))
    p.drawEllipse(QPointF(cx, cy), size * 0.028, size * 0.028)
    p.end()
    return img


def draw_chevron(size: int = 12) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#9aa4b5"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline(QPolygonF([QPointF(3, 4.6), QPointF(6, 7.6), QPointF(9, 4.6)]))
    p.end()
    return img


def draw_check(size: int = 12) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#04140d"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline(QPolygonF([QPointF(2.6, 6.3), QPointF(5.0, 8.7), QPointF(9.4, 3.4)]))
    p.end()
    return img


def write_ico_png(imgs, path: Path) -> None:
    """手写一个多尺寸 ICO（每帧都是 PNG 压缩的）。"""
    import struct

    from PySide6.QtCore import QBuffer, QByteArray

    blobs = []
    for img in imgs:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.WriteOnly)
        img.save(buf, "PNG")
        buf.close()
        blobs.append((img.width(), bytes(ba)))

    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    data = b""
    for w, blob in blobs:
        entries += struct.pack("<BBBBHHII", 0 if w >= 256 else w,
                               0 if w >= 256 else w, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        data += blob
    path.write_bytes(header + entries + data)


def main() -> None:
    app = QGuiApplication([])  # noqa: F841
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [draw(s) for s in sizes]
    big = imgs[-1]
    big.save(str(OUT / "icon.png"))
    ok = big.save(str(OUT / "icon.ico"), "ICO")
    print("ico ok:", ok, "png:", (OUT / "icon.png").stat().st_size)
    if not ok:
        write_ico_png(imgs, OUT / "icon.ico")
        print("ico(written by hand):", (OUT / "icon.ico").stat().st_size)

    draw_chevron(12).save(str(OUT / "chevron-down.png"))
    draw_check(12).save(str(OUT / "check.png"))
    print("assets:", [p.name for p in sorted(OUT.glob("*.png"))])


if __name__ == "__main__":
    main()
