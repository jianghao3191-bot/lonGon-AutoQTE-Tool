"""角度跟踪与预测：什么时候按下才刚好落在白区中心。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple
from collections import deque

TAU = math.pi * 2.0


@dataclass
class Prediction:
    fire_at: float       # perf_counter 目标按下时刻
    hit_at: float        # 预计进入白区中心的时刻
    omega: float         # rad/s
    angle_now: float
    zone_center: float
    confidence: float
    late: bool = False


class Predictor:
    def __init__(self) -> None:
        self.samples: Deque[Tuple[float, float]] = deque(maxlen=32)
        self._cont = 0.0
        self._prev_raw: Optional[float] = None
        self.last_seen = 0.0
        self.omega = 0.0
        self.confidence = 0.0
        self.fired_pass = False
        self._fired_at = 0.0
        self.in_zone_since: Optional[float] = None

    def mark_fired(self, t: float) -> None:
        self.fired_pass = True
        self._fired_at = t

    def reset(self) -> None:
        self.samples.clear()
        self._cont = 0.0
        self._prev_raw = None
        self.omega = 0.0
        self.confidence = 0.0
        self.fired_pass = False
        self.in_zone_since = None

    # ------------------------------------------------------------------ #
    def update(
        self,
        t: float,
        needle_rad: Optional[float],
        zone_start: Optional[float],
        zone_len: Optional[float],
        *,
        window: int,
        horizon: float,
        lead: float,
        late_tolerance: float,
    ) -> Optional[Prediction]:
        if needle_rad is None:
            if t - self.last_seen > 0.30:
                self.reset()
            return None

        self.last_seen = t

        # ---- 角度解卷绕 ----
        raw = needle_rad
        if self._prev_raw is not None:
            jump = (raw - self._prev_raw + math.pi) % TAU - math.pi
            if abs(jump) > math.radians(60.0):
                # 指针瞬移 = 新的一轮 QTE，旧轨迹作废
                self.samples.clear()
                self.fired_pass = False
                self._prev_raw = raw
                self._cont = raw
                return None
        if self._prev_raw is None:
            self._cont = raw
        else:
            d = raw - self._prev_raw
            if d > math.pi:
                self._cont -= TAU
            elif d < -math.pi:
                self._cont += TAU
            self._cont += d
        self._prev_raw = raw
        # 指针压到白区上时，白色像素被"并"进白区、轮廓被截断，质心会往回偏。
        # 这时候停止采样，用入区前的轨迹纯外推，落点反而更准。
        zone_margin = 0.030
        inside = (zone_start is not None and zone_len is not None
                  and len(self.samples) >= 3
                  and in_zone(raw, zone_start - zone_margin, zone_len + 2 * zone_margin))
        if not inside:
            self.samples.append((t, self._cont))
        if self.fired_pass and (t - self._fired_at) > 0.18 and not inside:
            # 已经打出去、指针也离开白区了 -> 下一轮可以重新触发
            self.fired_pass = False

        if zone_start is None or zone_len is None or zone_len <= 0:
            return None

        n = len(self.samples)
        if n < 3:
            return None

        # ---- 加权最小二乘估角速度 ----
        items = list(self.samples)[-max(3, window):]
        t0 = items[-1][0]
        xs = [s[0] - t0 for s in items]
        angs = [s[1] for s in items]
        wts = [0.72 ** (len(items) - 1 - i) for i in range(len(items))]
        W = sum(wts)
        xm = sum(w * x for w, x in zip(wts, xs)) / W
        am = sum(w * a for w, a in zip(wts, angs)) / W
        den = sum(w * (x - xm) ** 2 for w, x in zip(wts, xs))
        span = xs[0]
        if den <= 1e-12 or abs(span) < 0.010:
            return None
        omega = sum(w * (x - xm) * (a - am) for w, x, a in zip(wts, xs, angs)) / den
        a0 = am - omega * xm
        resid = math.sqrt(sum(w * (a - (a0 + omega * x)) ** 2
                              for w, x, a in zip(wts, xs, angs)) / W)

        self.omega = omega
        if not (0.25 <= abs(omega) <= 45.0):
            self.confidence = 0.0
            return None

        # ---- 目标角度 ----
        zone_center = zone_start + zone_len / 2.0
        if omega > 0:
            delta = (zone_center - a0) % TAU
        else:
            delta = -((a0 - zone_center) % TAU)
        t_hit = delta / omega
        if t_hit < -0.05 or t_hit > horizon:
            self.confidence = 0.0
            return None

        fire_at = t0 + t_hit - lead
        late = fire_at < t0
        if late and (t0 - fire_at) > late_tolerance:
            self.confidence = 0.0
            return None

        fire_at = max(fire_at, t0)
        angle_at_fire = a0 + omega * (fire_at - t0)
        if not in_zone(angle_at_fire, zone_start, zone_len):
            self.confidence = 0.0
            return None

        conf = (
            min(1.0, len(items) / 6.0)
            * max(0.0, 1.0 - resid / 0.20)
            * max(0.0, 1.0 - t_hit / max(horizon, 1e-6) * 0.5)
        )
        self.confidence = conf
        return Prediction(
            fire_at=fire_at,
            hit_at=t0 + t_hit,
            omega=omega,
            angle_now=a0,
            zone_center=zone_center,
            confidence=conf,
            late=late,
        )


def in_zone(angle: float, start: float, length: float) -> bool:
    if length <= 0:
        return False
    return ((angle - start) % TAU) < length
