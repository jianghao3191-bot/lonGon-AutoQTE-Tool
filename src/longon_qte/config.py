"""配置模型：纯本地 JSON，便携存放，不写系统盘。

设计要点
--------
* 所有配置放在 exe 同目录（或开发时的项目根目录），不碰 %APPDATA% / C 盘。
* 写盘采用 "临时文件 + 原子替换"，断电/崩溃不会留下半个 JSON。
* 没有时间戳校验、没有授权校验、没有联网校验。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Dict

CONFIG_FILENAME = "lonGon-AutoQTE-Tool.json"


def app_dir() -> Path:
    """返回程序所在目录。

    打包后是 exe 所在目录，开发时是项目根目录（src 的上一级）。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def config_path() -> Path:
    return app_dir() / CONFIG_FILENAME


@dataclass
class Settings:
    # ---- 截图 ----
    capture_mode: str = "dxgi"          # dxgi | obs | window
    monitor: int = 0
    crop_size: int = 224                # 224 / 256 / 320
    anchor: str = "center"              # center | custom
    offset_x: int = 0
    offset_y: int = 0
    max_fps: int = 0                    # 0 = 不限制（跟随显示器刷新）
    window_title: str = ""              # capture_mode=window 时的目标窗口
    obs_index: int = 0                  # capture_mode=obs 时的摄像头序号

    # ---- 识别 ----
    white_threshold: int = 205          # 0-255，纯白判定
    band_inner: float = 0.55            # 判定环内半径（相对半边长）
    band_outer: float = 1.00
    zone_frames: int = 5                # 时序 AND 帧数（白区=连续多帧都为白）
    zone_min_deg: float = 4.0           # 白区最小弧长
    needle_source: str = "auto"         # auto | white | motion
    motion_threshold: int = 14
    min_confidence: float = 0.45

    # ---- 触发 ----
    key: str = "space"
    hold_ms: int = 12
    cooldown_ms: int = 180
    lead_ms: float = 6.0                # 提前量（补偿注入->游戏响应延迟）
    horizon_ms: int = 240               # 最长预测时域
    sample_window: int = 9              # 角速度回归样本数
    late_tolerance_ms: float = 10.0     # 已经晚了但仍在容差内，补按

    # ---- 安全 ----
    only_foreground: bool = True        # 仅当目标窗口在前台时才按键
    target_title: str = ""              # 目标窗口标题关键字（可空=不限制）
    detect_only: bool = False           # 只识别不按键（压力测试用）

    # ---- 界面 ----
    always_on_top: bool = True
    show_overlay: bool = True
    log_to_file: bool = False
    start_hotkey: str = "F8"
    stop_hotkey: str = "F9"

    # ---- 模拟器（仅调试用）----
    sim_speed: float = 150.0
    sim_accel_after: int = 50

    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Settings":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (raw or {}).items() if k in known}
        obj = cls()
        for k, v in clean.items():
            cur = getattr(obj, k)
            try:
                if isinstance(cur, bool):
                    setattr(obj, k, bool(v))
                elif isinstance(cur, int) and not isinstance(cur, bool):
                    setattr(obj, k, int(v))
                elif isinstance(cur, float):
                    setattr(obj, k, float(v))
                elif isinstance(cur, str):
                    setattr(obj, k, str(v))
            except (TypeError, ValueError):
                continue
        return obj

    def copy(self) -> "Settings":
        return Settings.from_dict(self.to_dict())


def load_settings() -> Settings:
    p = config_path()
    try:
        if p.is_file():
            with open(p, "r", encoding="utf-8") as fh:
                return Settings.from_dict(json.load(fh))
    except (OSError, ValueError):
        pass
    return Settings()


def save_settings(s: Settings) -> None:
    p = config_path()
    tmp = p.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(s.to_dict(), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
