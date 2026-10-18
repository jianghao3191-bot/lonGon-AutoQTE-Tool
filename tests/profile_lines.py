import sys, time
sys.path.insert(0, r"D:\lonGon-AutoQTE-Tool\src")
import numpy as np
import synth
from longon_qte.detector import QteDetector, DetectorConfig

img = synth.render(224, needle=1.0, seed=3)
det = QteDetector(224)
det.configure(DetectorConfig())
white_t = np.minimum(np.minimum(img[..., 0], img[..., 1]), img[..., 2]) > 200

T = {}
def mark(k, t):
    T.setdefault(k, []).append(t)

N = 500
for _ in range(N):
    t0 = time.perf_counter()
    w = np.minimum(np.minimum(img[..., 0], img[..., 1]), img[..., 2]) > 200
    t1 = time.perf_counter()
    wb = w.ravel()[det.band_idx]
    t2 = time.perf_counter()
    h = det.hist
    h[det._hist_i] = wb
    t3 = time.perf_counter()
    zone = h.all(axis=0)
    t4 = time.perf_counter()
    occ = np.bincount(det.bin_band[zone], minlength=720) > 0
    t5 = time.perf_counter()
    nz = wb & ~zone
    t6 = time.perf_counter()
    sc = det.cos_band[nz].sum()
    ss = det.sin_band[nz].sum()
    t7 = time.perf_counter()
    mark("white", t1-t0); mark("band", t2-t1); mark("hist", t3-t2)
    mark("and", t4-t3); mark("bincount", t5-t4); mark("nz", t6-t5); mark("sums", t7-t6)

for k, v in T.items():
    v = np.array(v) * 1e6
    print(f"{k:10s} mean={v.mean():7.1f}us p95={np.percentile(v,95):7.1f}us")
print("total", sum(np.array(v).mean() for v in T.values()))
