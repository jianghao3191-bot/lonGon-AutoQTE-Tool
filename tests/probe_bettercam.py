import time, sys
import bettercam

print("output_info:")
try:
    bettercam.output_info()
except Exception as e:
    print("  output_info failed:", e)
try:
    print("enum:", bettercam.enum_dxgi_adapters())
except Exception as e:
    print("  enum failed:", e)

for dev in (0, 1):
    for out in (None, 0, 1):
        try:
            cam = bettercam.create(device_idx=dev, output_idx=out, region=None, output_color="BGRA")
        except Exception as e:
            print(f"create dev={dev} out={out} -> {type(e).__name__}: {e}")
            continue
        try:
            print(f"create dev={dev} out={out} ok: w={cam.width} h={cam.height} region={getattr(cam,'region',None)}")
            f = cam.grab(region=(1200, 600, 1424, 824))
            print("   grab shape:", None if f is None else f.shape, None if f is None else f.dtype)
        except Exception as e:
            print(f"   grab failed: {type(e).__name__}: {e}")
        finally:
            try:
                cam.release()
            except Exception:
                pass
        if cam is not None:
            break
    break
