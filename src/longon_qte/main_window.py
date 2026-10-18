"""主窗口：三栏布局（检测画面 / 参数 / 状态）+ 日志。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer, Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import APP_NAME, APP_VERSION, SIGNATURE, winutil
from .config import Settings, load_settings, save_settings
from .engine import Engine, Snapshot
from .injector import key_display, key_names
from .theme import (ACCENT, ERR, MUTE, SURFACE_2, WARN)
from .widgets import (Card, ComboBox, DoubleSpinBox, LogView, Meter, Preview,
                      PreviewWindow, SpinBox, Stat)

WM_ENTERSIZEMOVE = 0x0231
WM_EXITSIZEMOVE = 0x0232


class _MoveFilter(QAbstractNativeEventFilter):
    """窗口被拖动/缩放时，Windows 会进入一个模态循环；这段时间暂停预览刷新，
    避免和窗口重绘抢资源导致画面闪。"""

    def __init__(self, callback) -> None:
        super().__init__()
        self._cb = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        try:
            if event_type == b"windows_generic_MSG":
                msg = wt.MSG.from_address(int(message))
                if msg.message == WM_ENTERSIZEMOVE:
                    self._cb(True)
                elif msg.message == WM_EXITSIZEMOVE:
                    self._cb(False)
        except Exception:
            pass
        return False, 0


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings: Settings = load_settings()
        self.engine = Engine()
        self.preview_window: PreviewWindow | None = None
        self._last_preview_id = None
        self._key_state: dict[int, bool] = {}
        self._built = False
        self._dragging = False

        self.setWindowTitle(f"{APP_NAME}  ·  {SIGNATURE}")
        self.setMinimumSize(1180, 760)
        self.resize(1280, 812)

        self._build()
        self._load_into_ui()
        self._bind()

        self._move_filter = _MoveFilter(self._on_window_moving)
        QApplication.instance().installNativeEventFilter(self._move_filter)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(33)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(lambda: save_settings(self.settings))

        self._hotkey_timer = QTimer(self)
        self._hotkey_timer.setInterval(45)
        self._hotkey_timer.timeout.connect(self._poll_hotkeys)
        self._hotkey_timer.start()

        self.log(f"{APP_NAME} v{APP_VERSION} · {SIGNATURE}")
        self.log(f"配置文件：{config_hint()}")
        self.log("F8 启动 / 停止，F9 急停。第一次用建议先勾「只识别不按键」看一眼检测画面。")

    # ================================================================== #
    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)

        outer.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_left(), 112)
        body.addWidget(self._build_mid(), 126)
        body.addWidget(self._build_right(), 84)
        outer.addLayout(body, 1)

        outer.addWidget(self._build_log(), 0)

        self.status_chip = QLabel("就绪")
        self.status_chip.setObjectName("Hint")
        outer.addWidget(self.status_chip, 0, Qt.AlignLeft)
        self._built = True

    # ------------------------------------------------------------------ #
    def _build_header(self) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(9)

        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background:{ACCENT}; border-radius:4px;")
        h.addWidget(dot, 0, Qt.AlignVCenter)

        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        h.addWidget(title)

        meta = QLabel(f"v{APP_VERSION}   ·   {SIGNATURE}")
        meta.setObjectName("AppMeta")
        h.addWidget(meta, 0, Qt.AlignBottom)
        h.addStretch(1)

        self.read_fps = QLabel("— FPS")
        self.read_fps.setObjectName("Readout")
        self.read_ms = QLabel("— ms")
        self.read_ms.setObjectName("Readout")
        for w in (self.read_fps, self.read_ms):
            w.setToolTip("处理帧率 / 单帧处理耗时（截图 + 推理）")
            h.addWidget(w)
            h.addSpacing(6)

        self.btn_run = QPushButton("启动")
        self.btn_run.setObjectName("Primary")
        self.btn_run.setFixedSize(92, 34)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setToolTip("启动 / 停止（F8）")
        h.addWidget(self.btn_run)
        return h

    # ------------------------------------------------------------------ #
    def _build_left(self) -> Card:
        card = Card("检测画面")
        self.preview = Preview()
        self.preview.setToolTip("单击放大；双击打开纯净窗口")
        card.body.addWidget(self.preview, 1)

        line = QHBoxLayout()
        line.setSpacing(7)
        self._state_dot = QLabel()
        self._state_dot.setFixedSize(6, 6)
        self._state_dot.setStyleSheet(f"background:{MUTE}; border-radius:3px;")
        line.addWidget(self._state_dot, 0, Qt.AlignVCenter)
        self.lbl_status = QLabel("等待启动")
        self.lbl_status.setObjectName("Value")
        self.lbl_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        line.addWidget(self.lbl_status, 1)
        self.lbl_angle = QLabel("")
        self.lbl_angle.setObjectName("ValueMono")
        line.addWidget(self.lbl_angle, 0)
        card.body.addLayout(line)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_zoom = QPushButton("放大")
        self.btn_pure = QPushButton("纯净窗口")
        for b in (self.btn_zoom, self.btn_pure):
            b.setObjectName("Ghost")
            b.setCursor(Qt.PointingHandCursor)
        self.btn_zoom.setToolTip("把检测画面放大到独立窗口")
        self.btn_pure.setToolTip("无叠加层的预览窗口，适合 OBS 直接窗口采集")
        row.addWidget(self.btn_zoom)
        row.addWidget(self.btn_pure)
        row.addStretch(1)

        self.btn_overlay = QPushButton("叠加")
        self.btn_mask = QPushButton("掩码")
        for b in (self.btn_overlay, self.btn_mask):
            b.setObjectName("Ghost")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
        self.btn_overlay.setToolTip("显示白区 / 指针 / 预测落点")
        self.btn_mask.setToolTip("把识别用到的像素涂色：金色=白，绿色=判定到的白区")
        row.addWidget(self.btn_overlay)
        row.addWidget(self.btn_mask)
        card.body.addLayout(row)
        return card

    # ------------------------------------------------------------------ #
    def _build_mid(self) -> Card:
        card = Card("参数设置")
        reset = QPushButton("恢复默认")
        reset.setObjectName("Link")
        reset.setCursor(Qt.PointingHandCursor)
        reset.setToolTip("把所有参数恢复成初始值")
        reset.clicked.connect(self._reset_defaults)
        card.head_extra.addWidget(reset)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        g = QGridLayout(inner)
        g.setContentsMargins(0, 0, 8, 0)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(4)
        g.setColumnStretch(1, 1)
        scroll.setWidget(inner)
        card.body.addWidget(scroll, 1)

        # ---- 控件 ----
        self.w_capture = ComboBox()
        self.w_capture.addItem("DXGI 桌面复制", "dxgi")
        self.w_capture.addItem("GDI 兼容模式", "mss")
        self.w_capture.addItem("窗口 / OBS 投影", "window")
        self.w_capture.setToolTip("DXGI 最快；独占全屏抓不到时换 GDI")

        self.w_monitor = ComboBox()
        self.w_monitor.setSizeAdjustPolicy(ComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.w_monitor.setMinimumContentsLength(8)
        self.w_size = ComboBox()
        self.w_size.setSizeAdjustPolicy(ComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.w_size.setMinimumContentsLength(4)
        for s in (224, 256, 320):
            self.w_size.addItem(f"{s}", s)
        self.w_size.setToolTip("截图区域边长（像素）。游戏里的 QTE 比它大就换 320")

        self.w_window = QLineEdit()
        self.w_window.setPlaceholderText("窗口标题关键字")
        self.w_window.setToolTip("截图方式=窗口 时生效，比如填 OBS")
        self.btn_fg = QPushButton("取前台")
        self.btn_fg.setObjectName("Ghost")
        self.btn_fg.setFixedWidth(60)
        self.btn_fg.setCursor(Qt.PointingHandCursor)
        self.btn_fg.setToolTip("把当前前台窗口的标题填进来")

        self.w_offx = SpinBox()
        self.w_offx.setRange(-1200, 1200)
        self.w_offy = SpinBox()
        self.w_offy.setRange(-1200, 1200)
        for w in (self.w_offx, self.w_offy):
            w.setToolTip("截图中心相对屏幕中心的偏移")

        self.w_white = SpinBox()
        self.w_white.setRange(120, 255)
        self.w_white.setToolTip("多白才算白。识别不到白区就调低，误认就调高")

        self.w_band_in = DoubleSpinBox()
        self.w_band_in.setRange(0.10, 0.95)
        self.w_band_in.setSingleStep(0.05)
        self.w_band_in.setPrefix("内 ")
        self.w_band_in.setToolTip("判定环内径（相对半边长）。把中间的键帽排除掉")
        self.w_band_out = DoubleSpinBox()
        self.w_band_out.setRange(0.30, 1.00)
        self.w_band_out.setSingleStep(0.05)
        self.w_band_out.setPrefix("外 ")
        self.w_band_out.setToolTip("判定环外径")

        self.w_zone_frames = SpinBox()
        self.w_zone_frames.setRange(2, 12)
        self.w_zone_frames.setPrefix("确认 ")
        self.w_zone_frames.setSuffix(" 帧")
        self.w_zone_frames.setToolTip("连续多少帧都不动才算白区。误认静态白物就调大")

        self.w_needle = ComboBox()
        self.w_needle.addItem("自动", "auto")
        self.w_needle.addItem("只用白色", "white")
        self.w_needle.addItem("只用运动", "motion")
        self.w_needle.setToolTip("指针是彩色的就选「只用运动」")

        self.w_key = ComboBox()
        for name in key_names():
            self.w_key.addItem(key_display(name), name)
        self.w_hold = SpinBox()
        self.w_hold.setRange(1, 200)
        self.w_hold.setPrefix("按住 ")
        self.w_hold.setSuffix(" ms")

        self.w_lead = DoubleSpinBox()
        self.w_lead.setRange(0.0, 40.0)
        self.w_lead.setSingleStep(0.5)
        self.w_lead.setDecimals(1)
        self.w_lead.setPrefix("提前 ")
        self.w_lead.setSuffix(" ms")
        self.w_lead.setToolTip("打早了就加，打晚了就减，0.5ms 一步")

        self.w_cooldown = SpinBox()
        self.w_cooldown.setRange(30, 3000)
        self.w_cooldown.setPrefix("冷却 ")
        self.w_cooldown.setSuffix(" ms")

        self.w_horizon = SpinBox()
        self.w_horizon.setRange(60, 800)
        self.w_horizon.setSuffix(" ms")
        self.w_horizon.setToolTip("最多提前多久开始预测。指针很快时调小更稳")

        self.w_fg_only = QCheckBox("只在前台窗口按键")
        self.w_fg_only.setToolTip("配合下面的目标标题，避免误按到别的窗口")
        self.w_target = QLineEdit()
        self.w_target.setPlaceholderText("目标窗口标题关键字，留空不限制")
        self.w_detect_only = QCheckBox("只识别不按键")
        self.w_detect_only.setToolTip("调试 / 压力测试用：只统计，不发送任何按键")
        self.w_ontop = QCheckBox("窗口置顶")
        self.w_logfile = QCheckBox("写日志文件")

        rows = [
            ("section", "截图"),
            ("row", "方式", self.w_capture),
            ("row", "监视器", self._h(self.w_monitor, self.w_size, 2, 1)),
            ("row", "目标窗口", self._h(self.w_window, self.btn_fg, 1, 0)),
            ("row", "偏移", self._h(self.w_offx, self.w_offy, 1, 1)),
            ("section", "识别"),
            ("row", "白阈值", self._h(self.w_white, self.w_zone_frames, 1, 1)),
            ("row", "判定环", self._h(self.w_band_in, self.w_band_out, 1, 1)),
            ("row", "指针", self.w_needle),
            ("section", "触发"),
            ("row", "按键", self._h(self.w_key, self.w_hold, 2, 1)),
            ("row", "时机", self._h(self.w_lead, self.w_cooldown, 1, 1)),
            ("row", "预测窗口", self.w_horizon),
            ("section", "安全"),
            ("check", "", self.w_fg_only),
            ("row", "目标标题", self.w_target),
            ("check3", "", self.w_detect_only, self.w_ontop, self.w_logfile),
        ]
        r = 0
        for item in rows:
            kind = item[0]
            if kind == "section":
                r = self._section(g, r, item[1])
            elif kind == "row":
                r = self._row(g, r, item[1], item[2])
            elif kind == "check":
                r = self._check(g, r, item[2])
            elif kind == "check3":
                r = self._check3(g, r, item[2], item[3], item[4])
        g.setRowStretch(r, 1)
        return card

    # ------------------------------------------------------------------ #
    def _build_right(self) -> Card:
        card = Card("状态")

        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.stat_ms = Stat("单帧处理耗时", "ms")
        self.stat_fps = Stat("识别帧率", "fps")
        stats.addWidget(self.stat_ms)
        stats.addWidget(self.stat_fps)
        card.body.addLayout(stats)

        self.m_zone = Meter("白区弧长", ACCENT)
        self.m_needle = Meter("指针置信", "#6aa8ff")
        self.m_pred = Meter("预测置信", WARN)
        for m in (self.m_zone, self.m_needle, self.m_pred):
            card.body.addWidget(m)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:#1b2029;")
        card.body.addWidget(sep)

        cap = QLabel("本次运行")
        cap.setObjectName("CardTitle")
        card.body.addWidget(cap)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        self.v_frames = self._kv(grid, 0, "帧数")
        self.v_presses = self._kv(grid, 1, "按键")
        self.v_worst = self._kv(grid, 2, "最差耗时")
        self.v_capfps = self._kv(grid, 3, "截图 FPS")
        self.v_cat = self._kv(grid, 4, "类别")
        card.body.addLayout(grid)
        card.body.addStretch(1)

        self.lbl_engine = QLabel("未启动")
        self.lbl_engine.setObjectName("Hint")
        self.lbl_engine.setWordWrap(True)
        card.body.addWidget(self.lbl_engine)
        return card

    # ------------------------------------------------------------------ #
    def _build_log(self) -> Card:
        card = Card("运行日志")
        clear = QPushButton("清空")
        clear.setObjectName("Link")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(lambda: self.log_view.clear())
        card.head_extra.addWidget(clear)

        self.log_view = LogView()
        self.log_view.setFixedHeight(78)
        card.body.addWidget(self.log_view)
        return card

    # ------------------------------------------------------------------ #
    @staticmethod
    def _h(a: QWidget, b: QWidget, sa: int = 1, sb: int = 1) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(a, sa)
        lay.addWidget(b, sb)
        return w

    def _row(self, g: QGridLayout, r: int, label: str, w: QWidget) -> int:
        if label:
            lb = QLabel(label)
            lb.setObjectName("Key")
            lb.setFixedWidth(52)
            g.addWidget(lb, r, 0, Qt.AlignVCenter)
            g.addWidget(w, r, 1)
        else:
            g.addWidget(w, r, 0, 1, 2)
        return r + 1

    def _section(self, g: QGridLayout, r: int, text: str) -> int:
        lb = QLabel(text)
        lb.setStyleSheet(f"color:{MUTE}; font-size:8pt; font-weight:600;")
        lb.setContentsMargins(0, 4, 0, 0)
        g.addWidget(lb, r, 0, 1, 2)
        return r + 1

    def _check(self, g: QGridLayout, r: int, w: QWidget) -> int:
        g.addWidget(w, r, 0, 1, 2)
        return r + 1

    def _check2(self, g: QGridLayout, r: int, a: QWidget, b: QWidget) -> int:
        g.addWidget(a, r, 0)
        g.addWidget(b, r, 1)
        return r + 1

    def _check3(self, g: QGridLayout, r: int, a: QWidget, b: QWidget, c: QWidget) -> int:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(a)
        lay.addWidget(b)
        lay.addWidget(c)
        lay.addStretch(1)
        g.addWidget(w, r, 0, 1, 2)
        return r + 1

    def _kv(self, g: QGridLayout, r: int, key: str) -> QLabel:
        k = QLabel(key)
        k.setObjectName("Key")
        v = QLabel("—")
        v.setObjectName("ValueMono")
        v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        g.addWidget(k, r, 0)
        g.addWidget(v, r, 1)
        return v

    # ================================================================== #
    def _load_into_ui(self) -> None:
        s = self.settings
        self._fill_monitors()
        _set_combo(self.w_capture, s.capture_mode)
        _set_combo(self.w_size, s.crop_size)
        self.w_monitor.setCurrentIndex(max(0, min(s.monitor, self.w_monitor.count() - 1)))
        self.w_window.setText(s.window_title)
        self.w_offx.setValue(s.offset_x)
        self.w_offy.setValue(s.offset_y)
        self.w_white.setValue(s.white_threshold)
        self.w_band_in.setValue(s.band_inner)
        self.w_band_out.setValue(s.band_outer)
        self.w_zone_frames.setValue(s.zone_frames)
        _set_combo(self.w_needle, s.needle_source)
        _set_combo(self.w_key, s.key)
        self.w_lead.setValue(s.lead_ms)
        self.w_cooldown.setValue(s.cooldown_ms)
        self.w_hold.setValue(s.hold_ms)
        self.w_horizon.setValue(s.horizon_ms)
        self.w_fg_only.setChecked(s.only_foreground)
        self.w_target.setText(s.target_title)
        self.w_detect_only.setChecked(s.detect_only)
        self.w_ontop.setChecked(s.always_on_top)
        self.w_logfile.setChecked(s.log_to_file)
        self.btn_overlay.setChecked(s.show_overlay)
        self.btn_mask.setChecked(False)
        self.preview.set_overlay(s.show_overlay)
        self._sync_enabled()
        self._apply_ontop()

    def _collect(self) -> Settings:
        s = self.settings
        s.capture_mode = self.w_capture.currentData()
        s.monitor = self.w_monitor.currentIndex()
        s.crop_size = int(self.w_size.currentData())
        s.window_title = self.w_window.text().strip()
        s.offset_x = self.w_offx.value()
        s.offset_y = self.w_offy.value()
        s.white_threshold = self.w_white.value()
        s.band_inner = round(self.w_band_in.value(), 2)
        s.band_outer = round(self.w_band_out.value(), 2)
        s.zone_frames = self.w_zone_frames.value()
        s.needle_source = self.w_needle.currentData()
        s.key = self.w_key.currentData()
        s.lead_ms = self.w_lead.value()
        s.cooldown_ms = self.w_cooldown.value()
        s.hold_ms = self.w_hold.value()
        s.horizon_ms = self.w_horizon.value()
        s.only_foreground = self.w_fg_only.isChecked()
        s.target_title = self.w_target.text().strip()
        s.detect_only = self.w_detect_only.isChecked()
        s.always_on_top = self.w_ontop.isChecked()
        s.log_to_file = self.w_logfile.isChecked()
        s.show_overlay = self.btn_overlay.isChecked()
        return s

    def _fill_monitors(self) -> None:
        self.w_monitor.clear()
        try:
            mons = winutil.list_monitors()
        except Exception:
            mons = []
        if not mons:
            self.w_monitor.addItem("0", 0)
        for m in mons:
            tag = "主屏" if m.primary else f"副屏{m.index}"
            self.w_monitor.addItem(f"{m.width}×{m.height} {tag}", m.index)

    # ------------------------------------------------------------------ #
    def _bind(self) -> None:
        for w in (self.w_capture, self.w_monitor, self.w_size, self.w_needle, self.w_key):
            w.currentIndexChanged.connect(self._on_change)
        for w in (self.w_fg_only, self.w_detect_only, self.w_ontop, self.w_logfile):
            w.toggled.connect(self._on_change)
        for w in (self.w_offx, self.w_offy, self.w_white, self.w_zone_frames,
                  self.w_cooldown, self.w_hold, self.w_horizon):
            w.valueChanged.connect(self._on_change)
        for w in (self.w_lead, self.w_band_in, self.w_band_out):
            w.valueChanged.connect(self._on_change)
        for w in (self.w_window, self.w_target):
            w.editingFinished.connect(self._on_change)

        self.btn_overlay.toggled.connect(self._on_overlay)
        self.btn_mask.toggled.connect(self.preview.set_show_mask)
        self.btn_run.clicked.connect(self.toggle)
        self.btn_zoom.clicked.connect(self.show_preview_window)
        self.btn_pure.clicked.connect(self.show_pure_window)
        self.btn_fg.clicked.connect(self._grab_foreground_title)
        self.preview.clicked.connect(self.show_preview_window)

    def _on_change(self) -> None:
        if not self._built:
            return
        self._collect()
        self._sync_enabled()
        if self.engine.running:
            self.engine.apply(self.settings)
        self._save_timer.start()

    def _on_overlay(self, on: bool) -> None:
        self.preview.set_overlay(on)
        self._on_change()

    def _sync_enabled(self) -> None:
        is_win = self.w_capture.currentData() == "window"
        self.w_window.setEnabled(is_win)
        self.btn_fg.setEnabled(is_win)
        self.w_monitor.setEnabled(not is_win)

    def _apply_ontop(self) -> None:
        want = self.settings.always_on_top
        have = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
        if want == have:
            return
        flags = self.windowFlags()
        flags = (flags | Qt.WindowStaysOnTopHint) if want else (flags & ~Qt.WindowStaysOnTopHint)
        self.setWindowFlags(flags)
        self.show()

    def _reset_defaults(self) -> None:
        self.settings = Settings()
        self._load_into_ui()
        save_settings(self.settings)
        if self.engine.running:
            self.engine.apply(self.settings)
        self.log("已恢复默认参数", "warn")

    # ================================================================== #
    def toggle(self) -> None:
        if self.engine.running:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        self._collect()
        save_settings(self.settings)
        self._set_run_button(True)
        self.preview.set_placeholder("正在连接截图源…")
        self.engine.start(self.settings)
        self.log("已启动。出现指针后会自动识别白区并在到点时按键。", "ok")

    def stop(self) -> None:
        self.engine.stop()
        self._set_run_button(False)
        self.preview.set_placeholder("已停止")
        self.log("已停止。", "warn")

    def _set_run_button(self, running: bool) -> None:
        if getattr(self, "_run_state", None) == running:
            return
        self._run_state = running
        self.btn_run.setText("停止" if running else "启动")
        self.btn_run.setObjectName("Danger" if running else "Primary")
        self.btn_run.style().unpolish(self.btn_run)
        self.btn_run.style().polish(self.btn_run)

    # ================================================================== #
    def _on_window_moving(self, moving: bool) -> None:
        if moving == self._dragging:
            return
        self._dragging = moving
        self.preview.set_fast(moving)
        if not moving:
            # 拖完立刻补一帧，别等下一个 tick
            self._last_preview_id = None
            QTimer.singleShot(0, self._tick)

    def _tick(self) -> None:
        snap = self.engine.snapshot()
        running = snap.running
        self._set_run_button(running)

        total = snap.capture_ms + snap.detect_ms
        if running:
            self.read_fps.setText(f"{snap.detect_fps:5.1f} FPS")
            self.read_ms.setText(f"{total:5.2f} ms")
            good = 0 < total <= 4.0
            name = "ReadoutGood" if good else "Readout"
            if self.read_ms.objectName() != name:
                self.read_ms.setObjectName(name)
                self.read_ms.style().unpolish(self.read_ms)
                self.read_ms.style().polish(self.read_ms)
            self.stat_ms.set_value(f"{total:.2f}", "#3ddc97" if good else "#f5c451")
            self.stat_fps.set_value(f"{snap.detect_fps:.0f}")
        else:
            self.read_fps.setText("— FPS")
            self.read_ms.setText("— ms")
            if self.read_ms.objectName() != "Readout":
                self.read_ms.setObjectName("Readout")
                self.read_ms.style().unpolish(self.read_ms)
                self.read_ms.style().polish(self.read_ms)
            self.stat_ms.set_value("—")
            self.stat_fps.set_value("—")

        if (not self._dragging and snap.preview is not None
                and id(snap.preview) != self._last_preview_id):
            self._last_preview_id = id(snap.preview)
            self.preview.set_frame(snap.preview)
            self.preview.set_masks(snap.preview_white, snap.preview_zone)
            if self.preview_window is not None and self.preview_window.isVisible():
                self.preview_window.set_frame(snap.preview)

        self.preview.set_result(snap.result, snap.prediction)
        self._update_readouts(snap)
        self._drain_logs()

        if snap.error:
            self.status_chip.setText(f"错误：{snap.error}")
            self.status_chip.setStyleSheet(f"color:{ERR};")
        elif running:
            self.status_chip.setText(f"运行中 · {snap.capture_desc} · 区域 {snap.rect}")
            self.status_chip.setStyleSheet(f"color:{MUTE};")
        else:
            self.status_chip.setText("就绪")
            self.status_chip.setStyleSheet(f"color:{MUTE};")

    def _update_readouts(self, s: Snapshot) -> None:
        res = s.result
        pred = s.prediction
        zone_ok = res.zone_start_deg is not None
        needle_ok = res.needle_deg is not None

        if not s.running:
            self.lbl_status.setText("等待启动")
            self.lbl_angle.setText("")
            self._set_dot(MUTE)
            self.v_cat.setText("—")
            self.v_frames.setText("0")
            self.v_presses.setText("0")
            self.v_worst.setText("—")
            self.v_capfps.setText("—")
            for m in (self.m_zone, self.m_needle, self.m_pred):
                m.set_value(0.0, "—")
            self.lbl_engine.setText("未启动")
            return

        if zone_ok and needle_ok:
            if pred is not None:
                self.lbl_status.setText("已锁定 · 即将触发")
            else:
                self.lbl_status.setText("已锁定")
            self._set_dot(ACCENT)
        elif zone_ok:
            self.lbl_status.setText("寻找指针")
            self._set_dot("#6aa8ff")
        elif needle_ok and res.white_ratio > 0.0005:
            self.lbl_status.setText("寻找白区")
            self._set_dot(WARN)
        else:
            self.lbl_status.setText("未检测到画面")
            self._set_dot(MUTE)

        if needle_ok:
            self.lbl_angle.setText(f"{res.needle_deg:+.0f}°  {s.omega_deg:+.0f}°/s")
        else:
            self.lbl_angle.setText("")

        self.v_cat.setText("完美区" if zone_ok else "—")
        self.v_frames.setText(f"{s.frames}")
        self.v_presses.setText(f"{s.presses}")
        self.v_worst.setText(f"{s.worst_ms:.2f} ms" if s.worst_ms else "—")
        self.v_capfps.setText(f"{s.capture_fps:.0f}")

        arc = res.zone_len_deg or 0.0
        self.m_zone.set_value(min(1.0, arc / 40.0), f"{arc:.0f}°")
        self.m_needle.set_value(res.confidence, f"{res.confidence * 100:.0f}%")
        pc = pred.confidence if pred is not None else 0.0
        self.m_pred.set_value(pc, f"{pc * 100:.0f}%")
        self.lbl_engine.setText(f"{s.status}" + (f" · {s.capture_desc}" if s.capture_desc else ""))

    def _set_dot(self, color: str) -> None:
        if self._state_dot.property("c") == color:
            return
        self._state_dot.setProperty("c", color)
        self._state_dot.setStyleSheet(f"background:{color}; border-radius:3px;")

    def _drain_logs(self) -> None:
        for ts, level, text in self.engine.drain_logs():
            stamp = time.strftime("%H:%M:%S", time.localtime(ts))
            ms = int((ts % 1) * 1000)
            self.log_view.add(f"[{stamp}.{ms:03d}] {text}", level)

    def log(self, text: str, level: str = "info") -> None:
        self.engine.log(text, level)
        self._drain_logs()

    # ================================================================== #
    def _grab_foreground_title(self) -> None:
        t = winutil.foreground_title()
        if t:
            self.w_window.setText(t)
            self.w_target.setText(t)
            self._on_change()
            self.log(f"已取前台窗口：{t}")

    def show_preview_window(self) -> None:
        if self.preview_window is None:
            self.preview_window = PreviewWindow(self)
        self.preview_window.show()
        self.preview_window.raise_()

    def show_pure_window(self) -> None:
        self.show_preview_window()
        self.preview_window.view.show_overlay = False
        self.preview_window.raise_()

    def _poll_hotkeys(self) -> None:
        for vk, action in ((0x77, "toggle"), (0x78, "stop")):
            down = bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
            was = self._key_state.get(vk, False)
            self._key_state[vk] = down
            if down and not was:
                if action == "toggle":
                    self.toggle()
                elif self.engine.running:
                    self.stop()

    # ================================================================== #
    def closeEvent(self, e) -> None:  # noqa: N802
        self._tick_timer.stop()
        self._hotkey_timer.stop()
        try:
            QApplication.instance().removeNativeEventFilter(self._move_filter)
        except Exception:
            pass
        try:
            self.engine.stop()
        except Exception:
            pass
        save_settings(self.settings)
        if self.preview_window is not None:
            self.preview_window.close()
        super().closeEvent(e)


def _set_combo(box: ComboBox, value) -> None:
    for i in range(box.count()):
        if box.itemData(i) == value:
            box.setCurrentIndex(i)
            return


def config_hint() -> str:
    from .config import config_path
    return str(config_path())
