import ctypes, time, sys
sys.path.insert(0, r"D:\lonGon-AutoQTE-Tool\src")
from longon_qte import winutil
import numpy as np

winutil.enable_dpi_awareness()
u = ctypes.windll.user32
print("GetSystemMetrics:", u.GetSystemMetrics(0), u.GetSystemMetrics(1))
for m in winutil.list_monitors():
    print("monitor:", m)

import bettercam
cam = bettercam.create(device_idx=0, output_idx=None, output_color="BGRA")
print("cam size:", cam.width, cam.height, "region:", cam.region)

# full grab
t0 = time.perf_counter()
f = cam.grab()
print("full grab:", f.shape, "t=%.3f ms" % ((time.perf_counter()-t0)*1000))

h, w = f.shape[:2]
l = (w-224)//2; t = (h-224)//2
crop = f[t:t+224, l:l+224]
print("center crop mean:", crop.mean(axis=(0,1)))

# latency + none rate
N = 300
times = []
nones = 0
for _ in range(N):
    a = time.perf_counter()
    g = cam.grab(region=(l, t, l+224, t+224))
    b = time.perf_counter()
    times.append((b-a)*1000)
    if g is None:
        nones += 1
times = np.array(times)
print("grab region N=%d none=%d  mean=%.3f p50=%.3f p95=%.3f max=%.3f ms" % (
    N, nones, times.mean(), np.percentile(times,50), np.percentile(times,95), times.max()))

# continuous
for _ in range(20):
    cam.grab(region=(l,t,l+224,t+224))
t0=time.perf_counter(); c=0
while time.perf_counter()-t0 < 1.0:
    if cam.grab(region=(l,t,l+224,t+224)) is not None: c+=1
print("effective fps:", c)

# save crop png
from PIL import Image  # may not exist
