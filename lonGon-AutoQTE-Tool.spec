# -*- mode: python ; coding: utf-8 -*-
"""lonGon-AutoQTE-Tool 打包配置。

onedir + noconsole：
  * 不释放/不解压到 C 盘临时目录（onefile 每次启动都会往 %TEMP% 解压一遍）
  * 启动快，运行时只读自己目录下的文件
"""

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis

block_cipher = None

EXCLUDES = [
    "tkinter", "unittest", "pydoc", "doctest", "test", "asyncio",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSerialPort",
    "PySide6.QtSensors", "PySide6.QtSvgWidgets", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtHelp", "PySide6.QtDesigner",
    "PySide6.QtUiTools", "PySide6.QtOpenGLFunctions", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
    "PySide6.QtSpatialAudio", "PySide6.QtGraphs", "PySide6.QtGraphsWidgets",
    "PySide6.QtHttpServer", "PySide6.QtJson", "PySide6.QtNetwork",
]

a = Analysis(
    ["packaging/entry.py"],
    pathex=["src"],
    binaries=[],
    datas=[("assets", "assets")],
    hiddenimports=["bettercam", "mss", "comtypes", "numpy"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 只用 QtWidgets 画界面，下面这些 DLL 一个都用不到，删掉能省 ~35MB
_DROP = (
    "opengl32sw.dll", "qt6quick", "qt6qml", "qt6pdf", "qt6opengl",
    "qt6network", "qt6virtualkeyboard", "qt6designer", "qt6svg",
    "qt6datavisualization", "qt6charts", "qt6multimedia", "qt6websockets",
    "d3dcompiler_47.dll", "qt6sql", "qt6test", "qt6concurrent",
)
a.binaries = [b for b in a.binaries
              if not any(p in b[0].lower() for p in _DROP)]
a.datas = [d for d in a.datas
           if not any(p in d[0].lower() for p in _DROP)]

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="lonGon-AutoQTE-Tool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="lonGon-AutoQTE-Tool",
)
