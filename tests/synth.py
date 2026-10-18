"""合成 QTE 画面：用于离线验证识别/预测精度，不依赖游戏。"""

from __future__ import annotations

import math
import numpy as np

TAU = math.pi * 2


def render(
    size: int = 224,
    needle: float = 0.0,
    zone_start: float = 1.2,
    zone_len: float = 0.33,
    *,
    bg: int = 22,
    ring: int = 78,
    noise: int = 3,
    seed: int = 0,
) -> np.ndarray:
    """needle/zone 均为弧度（0=正右，顺时针为正，因为 y 轴向下）。"""
    n = size
    yy, xx = np.mgrid[0:n, 0:n]
    c = (n - 1) / 2.0
    dx = (xx - c) / (n / 2.0)
    dy = (yy - c) / (n / 2.0)
    r = np.sqrt(dx * dx + dy * dy)
    ang = np.arctan2(dy, dx)

    img = np.full((n, n, 4), bg, dtype=np.uint8)
    img[..., 3] = 255

    # 外环
    band = (r > 0.955) & (r < 1.0)
    img[band] = (ring, ring, ring, 255)

    # 完美区（纯白弧带）
    delta = (ang - zone_start) % TAU
    zone = (delta < zone_len) & (r > 0.84) & (r < 0.98)
    img[zone] = (255, 255, 255, 255)

    # 指针（白色细线 + 端头方块）
    dth = np.abs((ang - needle + math.pi) % TAU - math.pi)
    needle_mask = (dth < 0.035) & (r > 0.56) & (r < 0.97)
    img[needle_mask] = (255, 255, 255, 255)
    head = (dth < 0.10) & (r > 0.90) & (r < 0.97)
    img[head] = (255, 255, 255, 255)

    # 中心键盘提示（静态白框，用来验证它不会干扰）
    box = ((np.abs(dx) < 0.42) & (np.abs(dy) < 0.13))
    edge = box & ~((np.abs(dx) < 0.39) & (np.abs(dy) < 0.10))
    img[edge] = (235, 235, 235, 255)
    # 一条静态横线模拟 "Space" 文字
    txt = (np.abs(dy) < 0.012) & (np.abs(dx) < 0.22)
    img[txt] = (255, 255, 255, 255)

    if noise:
        rng = np.random.default_rng(seed)
        nz = rng.integers(-noise, noise + 1, size=(n, n, 3), dtype=np.int16)
        base = img[..., :3].astype(np.int16) + nz
        img[..., :3] = np.clip(base, 0, 255).astype(np.uint8)
    return img
