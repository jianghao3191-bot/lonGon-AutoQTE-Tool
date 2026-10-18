"""识别引擎：独立线程里 "抓帧 -> 识别 -> 预测 -> 按下去"。

线程策略
--------
* 识别线程提到 TIME_CRITICAL，进程 HIGH_PRIORITY，系统定时器 0.5ms。
* 没有新帧时只睡 0.4ms 轮询（一次 grab 约 0.05ms），不吃满 CPU。
* 触发前最后 3.5ms 用自旋等待，落点误差通常在 ±0.15ms。
* 运行期间关闭 GC（循环里全是无环的 numpy 临时对象，靠引用计数回收）。
"""

from __future__ import annotations

import gc
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

import numpy as np

from . import winutil
from .capture import Capture, CaptureError
from .detector import DetectorConfig, FrameResult, QteDetector
from .injector import KeyInjector
from .predictor import Prediction, Predictor

SPIN_WINDOW = 0.0035      # 距触发 3.5ms 内改自旋
IDLE_SLEEP = 0.00040      # 没新帧时的轮询间隔
PREVIEW_INTERVAL = 1 / 45


@dataclass
class Snapshot:
    running: bool = False
    status: str = "未启动"
    error: str = ""
    capture_fps: float = 0.0
    detect_fps: float = 0.0
    capture_ms: float = 0.0
    detect_ms: float = 0.0
    worst_ms: float = 0.0
    frames: int = 0
    presses: int = 0
    result: FrameResult = field(default_factory=FrameResult)
    prediction: Optional[Prediction] = None
    omega_deg: float = 0.0
    preview: Optional[np.ndarray] = None
    preview_white: Optional[np.ndarray] = None
    preview_zone: Optional[np.ndarray] = None
    capture_desc: str = ""
    rect: Tuple[int, int, int, int] = (0, 0, 0, 0)
    version: int = 0


class _PressState:
    __slots__ = ("pending_fire", "pending_up", "last_press", "pred")

    def __init__(self) -> None:
        self.pending_fire: Optional[float] = None
        self.pending_up: Optional[float] = None
        self.last_press: float = 0.0
        self.pred = None


class Engine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snap = Snapshot()
        self._settings = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._logs: Deque[Tuple[float, str, str]] = deque(maxlen=600)
        self._cfg_ver = 0
        self._seen_ver = 0

    # ------------------------------------------------------------------ #
    # 对外接口
    # ------------------------------------------------------------------ #
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def log(self, text: str, level: str = "info") -> None:
        with self._lock:
            self._logs.append((time.time(), level, text))
        if self._settings is not None and getattr(self._settings, "log_to_file", False):
            _append_log_file(text, level)

    def start(self, settings) -> None:
        if self.running:
            return
        self._settings = settings.copy()
        self._cfg_ver += 1
        self._seen_ver = -1
        self._stop.clear()
        with self._lock:
            self._snap = Snapshot(running=True, status="启动中…")
        self._thread = threading.Thread(
            target=self._run, name="qte-engine", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.5) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout)
            if t.is_alive():
                self.log("引擎线程未在超时内退出，仍在等待…", "warn")
                return
        self._thread = None
        with self._lock:
            self._snap.running = False
            self._snap.status = "已停止"

    def apply(self, settings) -> None:
        """运行中热更新参数；截图参数变了会自动重开截图源。"""
        self._settings = settings.copy()
        self._cfg_ver += 1

    def snapshot(self) -> Snapshot:
        with self._lock:
            s = self._snap
            # 浅拷贝，避免 UI 读的过程中被改写
            return Snapshot(**{k: getattr(s, k) for k in s.__dataclass_fields__})

    def drain_logs(self) -> List[Tuple[float, str, str]]:
        with self._lock:
            out = list(self._logs)
            self._logs.clear()
        return out

    # ------------------------------------------------------------------ #
    # 线程主体
    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        winutil.set_thread_time_critical()
        winutil.set_process_high_priority()
        winutil.begin_high_res_timer()
        gc.collect()
        gc.freeze()
        gc.set_threshold(20000, 50, 50)

        cap: Optional[Capture] = None
        detector = QteDetector(224)
        predictor = Predictor()
        injector = KeyInjector()
        frames = presses = 0
        cap_ms = det_ms = worst = 0.0
        fps_cap = fps_det = 0.0
        frame_times: Deque[float] = deque(maxlen=60)
        ps = _PressState()
        last_preview = 0.0
        cfg_seen = -1
        cap_key = None
        cap_desc = ""
        rect = (0, 0, 0, 0)
        dcfg = DetectorConfig()
        status = "识别中"
        last_status_push = 0.0
        last_needle: Optional[float] = None
        last_zone_reset = 0.0

        try:
            while not self._stop.is_set():
                st = self._settings
                if st is None:
                    break

                # ---------- 参数热更新 ----------
                if self._cfg_ver != cfg_seen:
                    cfg_seen = self._cfg_ver
                    dcfg = DetectorConfig(
                        white_threshold=st.white_threshold,
                        band_inner=st.band_inner,
                        band_outer=st.band_outer,
                        zone_frames=st.zone_frames,
                        zone_min_deg=st.zone_min_deg,
                        needle_source=st.needle_source,
                        motion_threshold=st.motion_threshold,
                        zone_trim_deg=0.0,
                    )
                    key = (st.capture_mode, st.monitor, st.crop_size,
                           st.anchor, st.offset_x, st.offset_y, st.window_title)
                    if cap is not None and key != cap_key:
                        cap.close()
                        cap = None
                        self.log("截图参数变化，正在重开截图源…")
                    cap_key = key
                    detector.set_size(int(st.crop_size))
                    detector.configure(dcfg)
                    predictor.reset()

                # ---------- 打开截图源 ----------
                if cap is None:
                    try:
                        cap = Capture(st)
                        cap.open()
                        cap_desc = cap.describe
                        rect = cap.rect
                        detector.set_size(int(st.crop_size))
                        detector.configure(dcfg)
                        self.log(f"截图源已启动：{cap_desc}  区域={rect}")
                        status = "识别中"
                    except Exception as exc:  # noqa: BLE001
                        cap = None
                        self.log(f"截图源启动失败：{exc}", "error")
                        self._push(status="错误", error=str(exc))
                        time.sleep(0.6)
                        continue

                # ---------- 抓帧 ----------
                t_g0 = time.perf_counter()
                try:
                    frame, ts = cap.grab()
                except Exception as exc:  # noqa: BLE001
                    # 切全屏/改分辨率/锁屏 都会让 DXGI 丢连接，这里自动重连，
                    # 不要让整个工具因为一次显示器事件就退出。
                    grab_fail += 1
                    self.log(f"截图中断（{exc}），正在重连…（第 {grab_fail} 次）", "warn")
                    try:
                        cap.close()
                    except Exception:
                        pass
                    cap = None
                    if grab_fail > 30:
                        raise CaptureError(f"连续重连失败：{exc}") from exc
                    time.sleep(0.25)
                    continue
                grab_fail = 0
                t_g1 = time.perf_counter()
                now = t_g1
                msg = self._service(st, injector, predictor, ps, now)
                if msg:
                    self.log(msg)
                    if msg.startswith("按 "):
                        presses += 1
                if frame is None:
                    time.sleep(IDLE_SLEEP)
                    continue

                # ---------- 识别 ----------
                res = detector.update(frame)
                t_d1 = time.perf_counter()
                frames += 1
                frame_times.append(ts)

                # 指针角度瞬移 = 新的一轮 QTE，清掉上一轮的白区历史
                if res.needle_deg is not None:
                    if last_needle is not None:
                        jump = abs((res.needle_deg - last_needle + 180.0) % 360.0 - 180.0)
                        if jump > 60.0 and (ts - last_zone_reset) > 0.15:
                            detector.reset_zone()
                            last_zone_reset = ts
                    last_needle = res.needle_deg
                else:
                    last_needle = None

                grab_cost = (t_g1 - t_g0) * 1000.0
                det_cost = (t_d1 - t_g1) * 1000.0
                cap_ms = grab_cost if cap_ms == 0 else cap_ms * 0.9 + grab_cost * 0.1
                det_ms = det_cost if det_ms == 0 else det_ms * 0.9 + det_cost * 0.1
                total = grab_cost + det_cost
                if frames > 20 and total > worst:
                    worst = total
                if len(frame_times) >= 2:
                    span = frame_times[-1] - frame_times[0]
                    if span > 1e-6:
                        fps_cap = (len(frame_times) - 1) / span
                        fps_det = fps_cap

                # ---------- 预测 ----------
                pred = predictor.update(
                    ts,
                    math.radians(res.needle_deg) if res.needle_deg is not None else None,
                    math.radians(res.zone_start_deg) if res.zone_start_deg is not None else None,
                    math.radians(res.zone_len_deg) if res.zone_len_deg is not None else None,
                    window=int(st.sample_window),
                    horizon=st.horizon_ms / 1000.0,
                    lead=st.lead_ms / 1000.0,
                    late_tolerance=st.late_tolerance_ms / 1000.0,
                )

                now = time.perf_counter()
                if (pred is not None and not predictor.fired_pass
                        and pred.confidence >= st.min_confidence
                        and (now - ps.last_press) * 1000.0 >= st.cooldown_ms):
                    ps.pending_fire = pred.fire_at
                    ps.pred = pred
                    msg = self._service(st, injector, predictor, ps, now)
                    if msg:
                        self.log(msg)
                        if msg.startswith("按 "):
                            presses += 1

                # ---------- 发布快照 ----------
                now = time.perf_counter()
                if now - last_preview >= PREVIEW_INTERVAL:
                    last_preview = now
                    self._push(
                        running=True, status=status, error="",
                        capture_fps=fps_cap, detect_fps=fps_det,
                        capture_ms=cap_ms, detect_ms=det_ms, worst_ms=worst,
                        frames=frames, presses=presses, result=res,
                        prediction=pred, omega_deg=math.degrees(predictor.omega),
                        preview=frame.copy(),
                        preview_white=detector.last_white.copy()
                        if detector.last_white is not None else None,
                        preview_zone=detector.last_zone_full.copy()
                        if detector.last_zone_full is not None else None,
                        capture_desc=cap_desc, rect=rect,
                    )
                elif now - last_status_push > 0.2:
                    last_status_push = now
                    self._push(capture_fps=fps_cap, detect_fps=fps_det,
                               capture_ms=cap_ms, detect_ms=det_ms,
                               frames=frames, presses=presses,
                               worst_ms=worst, result=res, prediction=pred,
                               omega_deg=math.degrees(predictor.omega))

        except CaptureError as exc:
            self.log(f"截图错误：{exc}", "error")
            self._push(status="错误", error=str(exc), running=False)
        except Exception as exc:  # noqa: BLE001
            import traceback
            self.log(f"引擎异常：{exc}\n{traceback.format_exc()}", "error")
            self._push(status="错误", error=str(exc), running=False)
        finally:
            try:
                injector.release_all()
            except Exception:
                pass
            if cap is not None:
                try:
                    cap.close()
                except Exception:
                    pass
            winutil.end_high_res_timer()
            gc.enable()
            with self._lock:
                self._snap.running = False
                self._snap.preview = None
                self._snap.preview_white = None
                self._snap.preview_zone = None

    # ------------------------------------------------------------------ #
    def _service(self, st, injector: KeyInjector, predictor: Predictor,
                 ps: "_PressState", now: float) -> Optional[str]:
        """处理"到点按下"与"按住到时间抬起"。没有新帧时也要调用。"""
        if ps.pending_up is not None and now >= ps.pending_up:
            injector.up(st.key)
            ps.pending_up = None

        t = ps.pending_fire
        if t is None:
            return None
        if now > t + st.late_tolerance_ms / 1000.0:
            ps.pending_fire = None
            self.log(f"错过预测窗口（晚了 {1000 * (now - t):.1f} ms），放弃本次", "warn")
            return None
        if predictor.fired_pass or st.detect_only:
            ps.pending_fire = None
            return None
        if now < t - SPIN_WINDOW:
            return None

        ok, why = _can_press(st)
        ps.pending_fire = None
        if not ok:
            predictor.mark_fired(now)
            return f"跳过按键：{why}"
        if t > now:
            _spin_until(t)
        press_t = time.perf_counter()
        injector.down(st.key)
        ps.pending_up = press_t + max(1, st.hold_ms) / 1000.0
        predictor.mark_fired(press_t)
        ps.last_press = press_t
        pred = ps.pred
        if pred is not None:
            return (f"按 {st.key}  (调度误差 {(press_t - t) * 1000:+.2f} ms, "
                    f"角速度 {math.degrees(pred.omega):+.0f}°/s, "
                    f"置信度 {pred.confidence:.0%})")
        return f"按 {st.key}"

    # ------------------------------------------------------------------ #
    def _push(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self._snap, k, v)
            self._snap.version += 1


def _spin_until(t: float) -> None:
    while True:
        now = time.perf_counter()
        if now >= t:
            return
        if t - now > 0.00035:
            time.sleep((t - now) - 0.0002)


def _can_press(settings) -> Tuple[bool, str]:
    if settings.only_foreground and settings.target_title:
        title = winutil.foreground_title()
        if settings.target_title.lower() not in title.lower():
            return False, f"前台窗口不是目标（{title or '无'}）"
    return True, ""


def _append_log_file(text: str, level: str) -> None:
    """可选：把日志写到 exe 旁边，单文件上限 512KB，超了就清空重来。"""
    try:
        from .config import app_dir
        import datetime
        p = app_dir() / "running.log"
        if p.exists() and p.stat().st_size > 512 * 1024:
            p.unlink()
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.datetime.now():%H:%M:%S}] {level.upper()}: {text}\n")
    except Exception:
        pass
