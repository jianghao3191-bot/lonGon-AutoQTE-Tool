import math, sys, time
sys.path.insert(0, r"D:\lonGon-AutoQTE-Tool\src")
from longon_qte.detector import DetectorConfig, QteDetector
from longon_qte.predictor import Predictor
import synth
import numpy as np

DEG = math.pi / 180

cfg = DetectorConfig()
det = QteDetector(224)
det.configure(cfg)
pred = Predictor()

zone_start = -40 * DEG
zone_len = 24 * DEG
speed = 190 * DEG          # rad/s
fps = 144.0

# 先建白区：静止 6 帧
res = None
for i in range(6):
    res = det.update(synth.render(224, needle=0.0, zone_start=zone_start,
                                  zone_len=zone_len, seed=i))
print("warmup:", res)

theta = 0.0
t = 1.0
fired = None
errors = []
for i in range(4000):
    img = synth.render(224, needle=theta, zone_start=zone_start, zone_len=zone_len, seed=1000 + i)
    res = det.update(img)
    t += 1.0 / fps
    p = pred.update(t,
                    math.radians(res.needle_deg) if res.needle_deg is not None else None,
                    math.radians(res.zone_start_deg) if res.zone_start_deg is not None else None,
                    math.radians(res.zone_len_deg) if res.zone_len_deg is not None else None,
                    window=9, horizon=0.24, lead=0.006, late_tolerance=0.01)
    if p and not pred.fired_pass and p.confidence > 0.45:
        if p.fire_at - t <= 0.0035:
            if p.fire_at > t:
                while time.perf_counter() < 0:
                    pass
            fired = (t, p)
            pred.fired_pass = True
    if i == 20:
        print("sample res:", res)
        print("pred:", p)
    theta = (theta + speed / fps) % (2 * math.pi)
    if fired:
        break

if fired:
    t_hit, p = fired
    angle_at_press = None
    # 反推按键时刻的真实角度：fired 时 theta 就是下一帧角度，简单用 t_hit 对应
    print(f"fired at frame {i}, omega={math.degrees(p.omega):.1f} deg/s, conf={p.confidence:.2f}")
    print(f"predicted hit angle={math.degrees(p.zone_center):.2f} zone=[{math.degrees(zone_start):.1f},{math.degrees(zone_start+zone_len):.1f}]")
else:
    print("NO FIRE")

# 精度基准：直接测单帧耗时
imgs = [synth.render(224, needle=i * 0.01, seed=i) for i in range(64)]
for _ in range(50):
    det.update(imgs[0])
N = 600
t0 = time.perf_counter()
for i in range(N):
    det.update(imgs[i % 64])
el = (time.perf_counter() - t0) / N * 1000
print(f"detector.update: {el:.3f} ms/frame")
