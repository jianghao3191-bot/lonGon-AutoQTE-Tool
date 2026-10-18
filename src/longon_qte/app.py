"""程序入口。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _resource(name: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    for p in (base / "assets" / name, Path(__file__).resolve().parents[1] / "assets" / name):
        if p.is_file():
            return str(p)
    return ""


def _assets_dir():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    for p in (base / "assets", Path(__file__).resolve().parents[1] / "assets"):
        if p.is_dir():
            return p
    return None


def main() -> int:
    # Qt 6 自己会把进程设成 Per-Monitor-V2 DPI 感知，这里不要再设一遍，
    # 否则 SetProcessDpiAwarenessContext 会返回"拒绝访问"并打印警告。
    from . import winutil  # noqa: F401  (留给无 Qt 的调试脚本调用)

    smoke = None
    if "--smoke" in sys.argv:
        i = sys.argv.index("--smoke")
        smoke = (sys.argv[i + 1] if i + 1 < len(sys.argv)
                 and not sys.argv[i + 1].startswith("--") else "smoke.png")

    selftest = None
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        selftest = (sys.argv[i + 1] if i + 1 < len(sys.argv)
                    and not sys.argv[i + 1].startswith("--") else "selftest.json")

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("lonGon-AutoQTE-Tool")
    app.setApplicationDisplayName("lonGon-AutoQTE-Tool")
    app.setOrganizationName("lonGon")

    from .theme import build_qss
    app.setStyleSheet(build_qss(_assets_dir()))

    ico = _resource("icon.ico")
    if ico:
        app.setWindowIcon(QIcon(ico))

    from .main_window import MainWindow

    win = MainWindow()
    win.show()
    win.raise_()
    win.activateWindow()

    # 任何槽函数里的未捕获异常都写进日志，不要让窗口无声消失
    import traceback

    def _excepthook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            win.log(f"界面异常：{exc}", "error")
            win.log(text, "error")
        except Exception:
            pass

    sys.excepthook = _excepthook

    if selftest:
        import json

        from PySide6.QtCore import QTimer

        from .config import Settings
        from .engine import Engine

        st = Settings()
        st.detect_only = True
        eng = Engine()
        eng.start(st)

        def _finish() -> None:
            snap = eng.snapshot()
            data = {
                "ok": bool(snap.frames > 0 and not snap.error),
                "frames": snap.frames,
                "capture_ms": round(snap.capture_ms, 3),
                "detect_ms": round(snap.detect_ms, 3),
                "desc": snap.capture_desc,
                "error": snap.error,
                "status": snap.status,
            }
            try:
                with open(selftest, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
            except OSError:
                pass
            eng.stop()
            app.quit()

        QTimer.singleShot(3000, _finish)

    if smoke:
        from PySide6.QtCore import QTimer

        def _shot() -> None:
            try:
                win.grab().save(smoke)
            finally:
                app.quit()

        QTimer.singleShot(1500, _shot)

    rc = app.exec()

    # bettercam/comtypes 的 COM 指针如果在解释器关闭阶段才释放，会打出
    # "access violation" 的 unraisable 异常；这里在退出前主动回收掉。
    try:
        win.deleteLater()
        del win
        import gc
        gc.collect()
    except Exception:
        pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
