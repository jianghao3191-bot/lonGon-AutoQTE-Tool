"""QTE 视觉识别核心。

思路（屏幕中心固定的圆环 + 纯白完美区 + 旋转指针）：

1. 只在一个"判定环"半径带里看像素，中间的文字/键帽提示（Space 之类）不参与判定。
2. 完美区 = 最近 K 帧的**时序 AND**：不动的白像素。这样不用训练模型，
   也不用事先知道白区角度，工具自己就把白区标定出来了（指针一动就被抹掉）。
3. 为了避免把"中间那块静态键帽提示"误当成白区，白区的弧只在外圈
   (band_outer 往里的 30%) 里统计——完美区永远画在圆环上，不会画在中心。
4. 指针 = 白色像素减去静态像素，用 cos/sin 加权质心取角度（O(N)，无轮廓查找）。
5. 指针不是白色时，用帧差找运动块兜底。

单帧 224x224 约 0.2ms（纯 numpy，无 GPU 依赖）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

TAU = math.pi * 2.0


@dataclass
class DetectorConfig:
    white_threshold: int = 205
    band_inner: float = 0.55
    band_outer: float = 1.00
    zone_frames: int = 5
    zone_min_deg: float = 4.0
    needle_source: str = "auto"      # auto | white | motion
    motion_threshold: int = 14
    zone_trim_deg: float = 0.0
    zone_band_ratio: float = 0.30    # 白区弧只在外圈这 30% 里找
    min_zone_deg: float = 4.0


@dataclass
class FrameResult:
    needle_deg: Optional[float] = None
    zone_start_deg: Optional[float] = None
    zone_len_deg: Optional[float] = None
    confidence: float = 0.0
    white_ratio: float = 0.0
    needle_px: int = 0
    zone_px: int = 0
    source: str = "-"

    @property
    def zone_center_deg(self) -> Optional[float]:
        if self.zone_start_deg is None or self.zone_len_deg is None:
            return None
        c = self.zone_start_deg + self.zone_len_deg / 2.0
        return (c + 180.0) % 360.0 - 180.0


class QteDetector:
    NBINS = 720

    def __init__(self, size: int = 224) -> None:
        self.size = int(size)
        self.band_inner = 0.55
        self.band_outer = 1.00
        self.white_threshold = 205
        self.zone_min_deg = 4.0
        self.needle_source = "auto"
        self.motion_threshold = 14
        self.zone_trim_deg = 0.0
        self.zone_band_ratio = 0.30
        self.zone_frames = 5
        self.zone_px = 0
        self.white_ratio = 0.0
        self.last_white = None
        self.last_zone = None          # 判定环内的静态(白区)掩码, 长度 band_n
        self.last_zone_full = None     # 整帧掩码, 给 UI 叠加用
        self._hist_i = 0
        self._hist_fill = 0
        self._build(size)

    # ------------------------------------------------------------------ #
    def _build(self, size: int) -> None:
        self.size = int(size)
        y, x = np.mgrid[0:size, 0:size]
        half = size / 2.0
        nx = (x.astype(np.float32) - (half - 0.5)) / half
        ny = (y.astype(np.float32) - (half - 0.5)) / half
        r = np.sqrt(nx * nx + ny * ny)
        theta = np.arctan2(ny, nx).astype(np.float32)

        band = (r >= self.band_inner) & (r <= self.band_outer)
        self.band_idx = np.flatnonzero(band.ravel())
        self.band_n = int(self.band_idx.size)
        th = theta.ravel()[self.band_idx]
        rr = r.ravel()[self.band_idx]
        self.theta_band = th
        self.cos_band = np.cos(th).astype(np.float32)
        self.sin_band = np.sin(th).astype(np.float32)
        self.bin_band = (((th + np.pi) * (self.NBINS / TAU)).astype(np.int32)
                         % self.NBINS)

        # 白区只看外圈
        self.zr0 = self.band_outer - self.zone_band_ratio * (self.band_outer - self.band_inner)
        self.zsel = np.flatnonzero(rr >= self.zr0)          # band 内的位置
        self.z_bin = self.bin_band[self.zsel]
        self.z_n = int(self.zsel.size)

        # 运动检测用的 1/2 下采样网格
        ds = max(2, size // 112)
        self.ds = int(ds)
        sy, sx = np.mgrid[0:size:ds, 0:size:ds]
        hx = (sx.astype(np.float32) - (half - 0.5)) / half
        hy = (sy.astype(np.float32) - (half - 0.5)) / half
        sr = np.sqrt(hx * hx + hy * hy)
        sth = np.arctan2(hy, hx).astype(np.float32)
        m = (sr >= self.band_inner) & (sr <= self.band_outer)
        self.ds_idx = np.flatnonzero(m.ravel())
        self.ds_theta = sth.ravel()[self.ds_idx]
        self.ds_cos = np.cos(self.ds_theta).astype(np.float32)
        self.ds_sin = np.sin(self.ds_theta).astype(np.float32)

        self._full_idx = None
        self.hist: Optional[np.ndarray] = None
        self.prev_gray: Optional[np.ndarray] = None
        self._alloc_hist()

    def _alloc_hist(self) -> None:
        self.hist = np.zeros((self.zone_frames, self.band_n), dtype=bool)
        self._hist_i = 0
        self._hist_fill = 0
        self.last_zone = np.zeros(self.band_n, dtype=bool)
        self.last_zone_full = np.zeros((self.size, self.size), dtype=bool)
        self.prev_gray = None

    def set_size(self, size: int) -> None:
        size = int(size)
        if size == self.size and self.hist is not None:
            return
        self._build(size)

    def configure(self, cfg: DetectorConfig) -> None:
        rebuild = (cfg.band_inner != self.band_inner
                   or cfg.band_outer != self.band_outer
                   or cfg.zone_band_ratio != self.zone_band_ratio)
        self.band_inner = float(cfg.band_inner)
        self.band_outer = float(cfg.band_outer)
        self.zone_band_ratio = float(cfg.zone_band_ratio)
        self.white_threshold = int(cfg.white_threshold)
        self.zone_min_deg = float(max(0.5, cfg.zone_min_deg))
        self.needle_source = cfg.needle_source
        self.motion_threshold = int(cfg.motion_threshold)
        self.zone_trim_deg = float(cfg.zone_trim_deg)
        frames_changed = self.zone_frames != int(cfg.zone_frames)
        self.zone_frames = int(max(2, cfg.zone_frames))
        if rebuild:
            self._build(self.size)
        elif frames_changed:
            self._alloc_hist()

    def reset(self) -> None:
        if self.hist is not None:
            self.hist[:] = False
        self._hist_fill = 0
        self.prev_gray = None
        if self.last_zone_full is not None:
            self.last_zone_full[:] = False

    def reset_zone(self) -> None:
        """新一轮 QTE 出现时清空白区历史，避免把上一轮的白区当成这一轮的。"""
        if self.hist is not None:
            self.hist[:] = False
        self._hist_fill = 0

    # ------------------------------------------------------------------ #
    def update(self, frame: np.ndarray) -> FrameResult:
        if frame.shape[0] != self.size or frame.shape[1] != self.size:
            self._build(frame.shape[0])

        # 纯白掩码。不要用 arr[..., :3].min(axis=2)：numpy 对跨步末轴求 min 慢 20 倍
        white = np.minimum(np.minimum(frame[..., 0], frame[..., 1]),
                           frame[..., 2]) > self.white_threshold
        self.last_white = white

        wb = white.ravel()[self.band_idx]
        self.white_ratio = float(wb.mean()) if wb.size else 0.0

        # ---- 时序 AND：不动的白色像素 = 静态(白区 + 中心提示) ----
        h = self.hist
        h[self._hist_i] = wb
        self._hist_i = (self._hist_i + 1) % self.zone_frames
        self._hist_fill = min(self._hist_fill + 1, self.zone_frames)
        if self._hist_fill >= self.zone_frames:
            static = h.all(axis=0)
        else:
            static = np.zeros(self.band_n, dtype=bool)
        self.last_zone = static

        # ---- 白区弧：只在外圈找 ----
        z_start = z_len = None
        zone_z = static[self.zsel]
        self.zone_px = int(zone_z.sum())
        if self.zone_px > 0:
            occ = np.bincount(self.z_bin[zone_z], minlength=self.NBINS) > 0
            run = _longest_circular_run(occ)
            if run is not None:
                b0, length = run
                start = -math.pi + b0 * (TAU / self.NBINS)
                ln = length * (TAU / self.NBINS)
                if self.zone_trim_deg > 0.0:
                    trim = math.radians(self.zone_trim_deg)
                    if ln - 2 * trim > math.radians(self.min_zone_deg):
                        start += trim
                        ln -= 2 * trim
                if math.degrees(ln) >= self.zone_min_deg:
                    z_start, z_len = start, ln

        # 整帧白区掩码（调试叠加用）
        if self.last_zone_full is not None:
            self.last_zone_full[:] = False
            self.last_zone_full.ravel()[self.band_idx[self.zsel][zone_z]] = True

        # ---- 指针 ----
        angle = None
        conf = 0.0
        npx = 0
        src = "-"
        if self.needle_source in ("auto", "white"):
            nz = wb & ~static
            npx = int(nz.sum())
            if npx >= 12:
                sc = float(self.cos_band[nz].sum())
                ss = float(self.sin_band[nz].sum())
                coh = math.hypot(sc, ss) / npx
                if coh >= 0.5 or self.needle_source == "white":
                    angle = math.atan2(ss, sc)
                    conf = min(1.0, coh) * min(1.0, npx / 120.0) ** 0.5
                    src = "white"

        if angle is None and self.needle_source in ("auto", "motion"):
            angle, conf, npx, src = self._motion_needle(frame)

        return FrameResult(
            needle_deg=(math.degrees(angle) if angle is not None else None),
            zone_start_deg=(math.degrees(z_start) if z_start is not None else None),
            zone_len_deg=(math.degrees(z_len) if z_len is not None else None),
            confidence=float(conf),
            white_ratio=self.white_ratio,
            needle_px=npx,
            zone_px=self.zone_px,
            source=src,
        )

    # ------------------------------------------------------------------ #
    def _motion_needle(self, frame: np.ndarray):
        gray = np.minimum(np.minimum(frame[..., 0], frame[..., 1]), frame[..., 2])
        g = gray[::self.ds, ::self.ds]
        if self.prev_gray is None or self.prev_gray.shape != g.shape:
            self.prev_gray = g
            return None, 0.0, 0, "motion"
        diff = np.abs(g.astype(np.int16) - self.prev_gray.astype(np.int16))
        self.prev_gray = g
        mb = (diff > self.motion_threshold).ravel()[self.ds_idx]
        n = int(mb.sum())
        if n < 6:
            return None, 0.0, 0, "motion"
        sc = float(self.ds_cos[mb].sum())
        ss = float(self.ds_sin[mb].sum())
        coh = math.hypot(sc, ss) / n
        if coh < 0.25:
            return None, 0.0, n, "motion"
        return math.atan2(ss, sc), min(1.0, coh) * 0.8, n, "motion"


def _longest_circular_run(mask: np.ndarray) -> Optional[Tuple[int, int]]:
    n = int(mask.size)
    if n == 0 or not mask.any():
        return None
    if mask.all():
        return 0, n
    false_idx = np.flatnonzero(~mask)
    start = int(false_idx[0])
    idx = np.concatenate((np.arange(start, n), np.arange(0, start)))
    m = mask[idx]
    padded = np.concatenate(([False], m, [False]))
    d = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    lengths = ends - starts
    k = int(np.argmax(lengths))
    return (start + int(starts[k])) % n, int(lengths[k])
