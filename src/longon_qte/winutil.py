"""Windows 平台小工具：定时器精度、线程优先级、显示器枚举、前台窗口。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass
from typing import List, Optional

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll", use_last_error=True)


# --------------------------------------------------------------------------- #
# 显示器
# --------------------------------------------------------------------------- #
class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", wt.DWORD)]


@dataclass(frozen=True)
class Monitor:
    index: int
    left: int
    top: int
    right: int
    bottom: int
    primary: bool

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def label(self) -> str:
        tag = "主屏" if self.primary else f"副屏{self.index}"
        return f"{self.index}: {self.width}x{self.height}  {tag}"


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_int, wt.HMONITOR, wt.HDC, ctypes.POINTER(_RECT), wt.LPARAM
)


def list_monitors() -> List[Monitor]:
    found: List[Monitor] = []

    def _cb(hmon, _hdc, _rect, _data):  # noqa: ANN001
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            found.append(Monitor(len(found), r.left, r.top, r.right, r.bottom,
                                 bool(info.dwFlags & 1)))
        return 1

    user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(_cb), 0)
    found.sort(key=lambda m: (m.left, m.top))
    return [Monitor(i, m.left, m.top, m.right, m.bottom, m.primary)
            for i, m in enumerate(found)]


# --------------------------------------------------------------------------- #
# DPI
# --------------------------------------------------------------------------- #
def enable_dpi_awareness() -> None:
    """每显示器 DPI 感知，避免 125%/150% 缩放下坐标错位。"""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# 定时器 / 优先级
# --------------------------------------------------------------------------- #
def begin_high_res_timer() -> None:
    """把系统定时器精度压到 0.5ms，降低 sleep 抖动。"""
    try:
        cur = wt.ULONG(0)
        ntdll.NtSetTimerResolution(5000, True, ctypes.byref(cur))
    except Exception:
        pass
    try:
        ctypes.WinDLL("winmm").timeBeginPeriod(1)
    except Exception:
        pass


def end_high_res_timer() -> None:
    try:
        cur = wt.ULONG(0)
        ntdll.NtSetTimerResolution(5000, False, ctypes.byref(cur))
    except Exception:
        pass
    try:
        ctypes.WinDLL("winmm").timeEndPeriod(1)
    except Exception:
        pass


def set_thread_time_critical() -> None:
    """当前线程提到 TIME_CRITICAL，防止被后台任务抢占。"""
    try:
        handle = kernel32.GetCurrentThread()
        kernel32.SetThreadPriority(handle, 15)  # THREAD_PRIORITY_TIME_CRITICAL
    except Exception:
        pass


def set_process_high_priority() -> None:
    try:
        handle = kernel32.GetCurrentProcess()
        kernel32.SetPriorityClass(handle, 0x00000080)  # HIGH_PRIORITY_CLASS
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 窗口
# --------------------------------------------------------------------------- #
def foreground_title() -> str:
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(hwnd, buf, n + 2)
        return buf.value
    except Exception:
        return ""


def find_window(keyword: str) -> Optional[int]:
    """按标题关键字找第一个可见顶层窗口。"""
    if not keyword:
        return None
    result: List[int] = []
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def _cb(hwnd, _lparam):  # noqa: ANN001
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(hwnd, buf, n + 2)
        if keyword.lower() in buf.value.lower():
            result.append(hwnd)
            return False
        return True

    try:
        user32.EnumWindows(proc_type(_cb), 0)
    except Exception:
        return None
    return result[0] if result else None


def window_client_rect(hwnd: int) -> Optional[tuple]:
    """返回窗口客户区在屏幕上的坐标 (left, top, width, height)。"""
    try:
        r = _RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(r)):
            return None
        w, h = r.right - r.left, r.bottom - r.top
        if w <= 0 or h <= 0:
            return None
        pt = wt.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return None
        return pt.x, pt.y, w, h
    except Exception:
        return None


def is_minimized(hwnd: int) -> bool:
    try:
        return bool(user32.IsIconic(hwnd))
    except Exception:
        return False
