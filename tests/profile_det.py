import sys, time
sys.path.insert(0, r"D:\lonGon-AutoQTE-Tool\src")
import numpy as np
import synth
from longon_qte.detector import QteDetector, DetectorConfig

img = synth.render(224, needle=1.0, seed=3)
print(img.shape, img.dtype, img.flags["C_CONTIGUOUS"])

def bench(fn, n=2000):
    fn(); fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t0) / n * 1e6

print("min(axis=2)      : %.1f us" % bench(lambda: img[..., :3].min(axis=2)))
print("minimum chain    : %.1f us" % bench(lambda: np.minimum(np.minimum(img[..., 0], img[..., 1]), img[..., 2])))
u32 = img.view(np.uint32)
def bitwhite():
    v = u32
    return ((v & 0xFF) > 200) & (((v >> 8) & 0xFF) > 200) & (((v >> 16) & 0xFF) > 200)
print("uint32 bits      : %.1f us" % bench(bitwhite))
print("uint32 bits row  : %.1f us" % bench(lambda: ((u32 & 0xFF) > 200)))

white = img[..., :3].min(axis=2) > 200
det = QteDetector(224)
det.configure(DetectorConfig())
print("band n           :", det.band_n)
print("fancy index band : %.1f us" % bench(lambda: white.ravel()[det.band_idx]))

h = np.zeros((5, det.band_n), dtype=bool)
print("all(axis=0)      : %.1f us" % bench(lambda: h.all(axis=0)))
cnt = np.zeros(det.band_n, dtype=np.uint8)
print("counts>=5        : %.1f us" % bench(lambda: cnt >= 5))

# 全流程
for _ in range(100):
    det.update(img)
print("update           : %.1f us" % bench(lambda: det.update(img), 1000))

# 112 下采样
d112 = img[::2, ::2]
print("112 shape", d112.shape)
det2 = QteDetector(112)
det2.configure(DetectorConfig())
for _ in range(100):
    det2.update(np.ascontiguousarray(d112))
print("update@112       : %.1f us" % bench(lambda: det2.update(np.ascontiguousarray(d112)), 1000))
