"""截图源：DXGI 桌面复制（首选）/ GDI(mss) 兼容 / 窗口捕获。

设计目标
--------
* 只抓屏幕中心那一小块（224/320），不抓整屏，GPU 拷贝量极小。
* 拿不到新帧时立刻返回 None（约 0.05ms），由上层决定睡多久，
  避免像"每帧都抓整屏"那样白白吃掉 CPU/GPU。
* 不落盘、不缓存历史帧。
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

import numpy as np

from . import winutil

Rect = Tuple[int, int, int, int]


class CaptureError(RuntimeError):
    pass


def mode_label(mode: str) -> str:
    return {
        "dxgi": "DXGI 桌面复制（推荐）",
        "mss": "GDI 兼容模式",
        "window": "窗口 / OBS 投影",
    }.get(mode, mode)


def _rect_for(settings) -> Rect:
    monitors = winutil.list_monitors()
    if not monitors:
        raise CaptureError("没有检测到显示器")
    idx = min(max(0, int(settings.monitor)), len(monitors) - 1)
    m = monitors[idx]
    size = int(settings.crop_size)
    cx = m.left + m.width // 2 + int(settings.offset_x)
    cy = m.top + m.height // 2 + int(settings.offset_y)
    return (cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2)


def _window_rect(settings) -> Rect:
    hwnd = winutil.find_window(settings.window_title)
    if not hwnd or winutil.is_minimized(hwnd):
        raise CaptureError(f"找不到窗口：{settings.window_title or '(未填写)'}")
    r = winutil.window_client_rect(hwnd)
    if not r:
        raise CaptureError("无法读取窗口客户区")
    left, top, w, h = r
    size = min(int(settings.crop_size), w, h)
    cx = left + w // 2 + int(settings.offset_x)
    cy = top + h // 2 + int(settings.offset_y)
    return (cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2)


class Capture:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.mode = settings.capture_mode
        self.size = int(settings.crop_size)
        self._cam = None
        self._sct = None
        self._rect: Rect = (0, 0, 0, 0)
        self._dynamic = False
        self.describe = ""

    # ------------------------------------------------------------------ #
    def open(self) -> None:
        self.close()
        if self.mode == "window":
            self._rect = _window_rect(self.settings)
            self._dynamic = True
        else:
            self._rect = _rect_for(self.settings)
            self._dynamic = False

        if self.mode == "mss":
            self._open_mss()
        else:
            try:
                self._open_dxgi()
            except Exception as exc:  # noqa: BLE001
                # DXGI 在某些独占全屏/虚拟显示器上会失败，退回 GDI
                self._cam = None
                self.mode = "mss"
                self._open_mss()
                self.describe += f"  (DXGI 不可用: {exc})"

    def _open_dxgi(self) -> None:
        import bettercam  # 延迟导入，缩短冷启动

        region = None if self._dynamic else self._rect
        cam = bettercam.create(
            device_idx=0,
            output_idx=max(0, int(self.settings.monitor)),
            region=region,
            output_color="BGRA",
        )
        # 预热：第一帧要建 staging texture，约 3~6ms，别让玩家吃到
        for _ in range(3):
            if self._dynamic:
                probe = cam.grab(region=self._rect)
            else:
                probe = cam.grab()
            time.sleep(0.004)
        if probe is None:
            # 桌面完全静止时可能拿不到帧，再试一次
            for _ in range(20):
                probe = cam.grab(region=self._rect) if self._dynamic else cam.grab()
                if probe is not None:
                    break
                time.sleep(0.005)
        if probe is not None and probe.shape[0] != self.size:
            raise CaptureError(f"抓取尺寸不符：{probe.shape}")
        self._cam = cam
        self.describe = "DXGI Desktop Duplication"
        if self._dynamic:
            self.describe += " / 窗口"

    def _open_mss(self) -> None:
        import mss

        self._sct = mss.mss()
        self.describe = "GDI (mss)"
        # 预热
        for _ in range(2):
            try:
                self._grab_mss()
            except Exception:
                pass
            time.sleep(0.004)

    # ------------------------------------------------------------------ #
    def grab(self) -> Tuple[Optional[np.ndarray], float]:
        """返回 (BGRA 帧 或 None, 时间戳)。None = 还没有新帧。"""
        ts = 0.0
        if self.mode == "mss":
            try:
                frame = self._grab_mss()
                ts = time.perf_counter()
                return frame, ts
            except Exception as exc:  # noqa: BLE001
                raise CaptureError(f"GDI 截图失败: {exc}") from exc

        if self._cam is None:
            raise CaptureError("截图源未初始化")
        rect = None
        if self._dynamic:
            rect = _window_rect(self.settings)
            self._rect = rect
        frame = self._cam.grab(region=rect) if self._dynamic else self._cam.grab()
        ts = time.perf_counter()
        return frame, ts

    def _grab_mss(self) -> np.ndarray:
        left, top, right, bottom = self._rect
        w, h = right - left, bottom - top
        shot = self._sct.grab({"left": left, "top": top, "width": w, "height": h})
        return np.frombuffer(shot.bgra, dtype=np.uint8).reshape(h, w, 4).copy()

    # ------------------------------------------------------------------ #
    def close(self) -> None:
        cam, self._cam = self._cam, None
        if cam is not None:
            try:
                cam.release()
            except Exception:
                pass
        sct, self._sct = self._sct, None
        if sct is not None:
            try:
                sct.close()
            except Exception:
                pass

    @property
    def rect(self) -> Rect:
        return self._rect
