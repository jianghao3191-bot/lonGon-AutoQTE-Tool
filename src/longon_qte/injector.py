"""按键注入：SendInput + 扫描码，尽量兼容 DirectInput / RawInput 游戏。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from typing import Dict, Optional, Tuple

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


# 名称 -> (显示名, 虚拟键码, 扫描码, 是否扩展键)
_KEYS: Dict[str, Tuple[str, int, int, bool]] = {
    "space": ("空格 Space", 0x20, 0x39, False),
    "enter": ("回车 Enter", 0x0D, 0x1C, False),
    "esc": ("Esc", 0x1B, 0x01, False),
    "tab": ("Tab", 0x09, 0x0F, False),
    "shift": ("Shift", 0x10, 0x2A, False),
    "ctrl": ("Ctrl", 0x11, 0x1D, False),
    "alt": ("Alt", 0x12, 0x38, False),
    "e": ("E", 0x45, 0x12, False),
    "f": ("F", 0x46, 0x21, False),
    "q": ("Q", 0x51, 0x10, False),
    "r": ("R", 0x52, 0x13, False),
    "c": ("C", 0x43, 0x2E, False),
    "v": ("V", 0x56, 0x2F, False),
    "g": ("G", 0x47, 0x22, False),
    "z": ("Z", 0x5A, 0x2C, False),
    "x": ("X", 0x58, 0x2D, False),
    "1": ("1", 0x31, 0x02, False),
    "2": ("2", 0x32, 0x03, False),
    "mouse_left": ("鼠标左键", 0, 0, False),
    "mouse_right": ("鼠标右键", 0, 0, False),
    "mouse_middle": ("鼠标中键", 0, 0, False),
}

MOUSE_FLAGS = {
    "mouse_left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "mouse_right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "mouse_middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def key_display(name: str) -> str:
    return _KEYS.get(name, (name, 0, 0, False))[0]


def key_names() -> list:
    return list(_KEYS.keys())


class KeyInjector:
    """发送按键。按下/抬起分离，方便把"按住时长"交给主循环调度。"""

    def __init__(self) -> None:
        self._down: set = set()
        self.count = 0

    # ------------------------------------------------------------------ #
    def _send_keyboard(self, vk: int, scan: int, extended: bool, up: bool) -> None:
        flags = KEYEVENTF_SCANCODE
        if extended:
            flags |= KEYEVENTF_EXTENDEDKEY
        if up:
            flags |= KEYEVENTF_KEYUP
        inp = _INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki.wVk = 0
        inp.ki.wScan = scan
        inp.ki.dwFlags = flags
        inp.ki.time = 0
        inp.ki.dwExtraInfo = ctypes.cast(0, ctypes.POINTER(wt.ULONG))
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def _send_mouse(self, name: str, up: bool) -> None:
        fl = MOUSE_FLAGS[name][1 if up else 0]
        inp = _INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dx = 0
        inp.mi.dy = 0
        inp.mi.mouseData = 0
        inp.mi.dwFlags = fl
        inp.mi.time = 0
        inp.mi.dwExtraInfo = ctypes.cast(0, ctypes.POINTER(wt.ULONG))
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    # ------------------------------------------------------------------ #
    def down(self, name: str) -> bool:
        if name in MOUSE_FLAGS:
            self._send_mouse(name, up=False)
        else:
            spec = _KEYS.get(name)
            if spec is None:
                return False
            _, vk, scan, ext = spec
            self._send_keyboard(vk, scan, ext, up=False)
        self._down.add(name)
        return True

    def up(self, name: str) -> None:
        if name in MOUSE_FLAGS:
            self._send_mouse(name, up=True)
        else:
            spec = _KEYS.get(name)
            if spec is None:
                return
            _, vk, scan, ext = spec
            self._send_keyboard(vk, scan, ext, up=True)
        self._down.discard(name)
        self.count += 1

    def tap(self, name: str, hold: float = 0.012) -> None:
        if self.down(name):
            import time
            time.sleep(hold)
            self.up(name)

    def release_all(self) -> None:
        for name in list(self._down):
            try:
                self.up(name)
            except Exception:
                pass
        self._down.clear()
