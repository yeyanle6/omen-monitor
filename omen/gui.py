"""PyQt5 GUI:仪表卡片、温度/占用曲线、风扇控制面板、主窗口。"""

from __future__ import annotations

import os
import time
from collections import deque
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

_cache_base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
matplotlib_cache = Path(_cache_base) / "omen-monitor" / "matplotlib"
matplotlib_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))

APP_ICON_PATH = Path(__file__).parent / "assets" / "icon.svg"

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from . import config as user_config
from .curve import load_curve, save_curve
from .curve_widget import FanCurveDialog
from .fan_backend import HpWmiFanBackend
from .i18n import MODE_KEYS, available_langs, lang_display, mode_label, set_lang, t
from .predict import current_temp, predict_pwm
from .sampler import (
    HISTORY_SECONDS,
    SAMPLE_INTERVAL_MS,
    Sample,
    Sampler,
    pwm_to_pct,
)
from .tray import TrayIcon


class StatTile(QtWidgets.QFrame):
    """大字仪表卡片。"""

    def __init__(self, title_key: str, parent=None) -> None:
        super().__init__(parent)
        self.title_key = title_key
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #1e1e24; border-radius: 8px; }"
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(2)

        self.title = QtWidgets.QLabel(t(title_key))
        self.title.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        self.value = QtWidgets.QLabel("--")
        self.value.setStyleSheet("color: #f1f3f4; font-size: 26px; font-weight: 600;")
        self.sub = QtWidgets.QLabel("")
        self.sub.setStyleSheet("color: #80868b; font-size: 10px;")

        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.sub)

    def set_value(self, value: str, sub: str = "", color: str | None = None) -> None:
        self.value.setText(value)
        self.sub.setText(sub)
        if color:
            self.value.setStyleSheet(
                f"color: {color}; font-size: 26px; font-weight: 600;"
            )

    def retranslate(self) -> None:
        self.title.setText(t(self.title_key))


def temp_color(t: float | None) -> str:
    if t is None:
        return "#80868b"
    if t >= 90:
        return "#ff5252"
    if t >= 80:
        return "#ff9100"
    if t >= 70:
        return "#ffd740"
    return "#69f0ae"


FAN_PANEL_QSS = """
QFrame#FanPanel { background: #1e1e24; border-radius: 10px; }
QFrame#FanPanel QLabel { color: #f1f3f4; }
QFrame#FanPanel QPushButton[role="seg"] {
    background: #2a2a30;
    color: #c7c9cc;
    border: 1px solid #3c4043;
    padding: 6px 14px;
    font-size: 12px;
}
QFrame#FanPanel QPushButton[role="seg"]:hover { background: #32323a; }
QFrame#FanPanel QPushButton[role="seg"]:checked {
    background: #40c4ff;
    color: #121216;
    border-color: #40c4ff;
}
QFrame#FanPanel QPushButton[role="seg"][seg_pos="left"]   { border-top-left-radius: 8px;  border-bottom-left-radius: 8px;  border-right: none; }
QFrame#FanPanel QPushButton[role="seg"][seg_pos="middle"] { border-right: none; }
QFrame#FanPanel QPushButton[role="seg"][seg_pos="right"]  { border-top-right-radius: 8px; border-bottom-right-radius: 8px; }
QFrame#FanPanel QPushButton[role="ghost"] {
    background: transparent;
    color: #9aa0a6;
    border: 1px solid #3c4043;
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 12px;
}
QFrame#FanPanel QPushButton[role="ghost"]:hover { color: #f1f3f4; border-color: #40c4ff; }
QFrame#FanPanel QPushButton[role="ghost"]:disabled { color: #5f6368; border-color: #3c4043; }
QFrame#FanPanel QSlider::groove:horizontal {
    border: none; height: 6px; background: #2a2a30; border-radius: 3px;
}
QFrame#FanPanel QSlider::handle:horizontal {
    background: #40c4ff; border: none;
    width: 14px; height: 14px; margin: -4px 0; border-radius: 7px;
}
QFrame#FanPanel QSlider::sub-page:horizontal {
    background: #40c4ff; border-radius: 3px;
}
"""


class FanControlPanel(QtWidgets.QFrame):
    """风扇控制面板:分段按钮(模式)+ 滑条(底线/手动 PWM)+ 曲线编辑。"""

    mode_changed = QtCore.pyqtSignal(str)
    slider_applied = QtCore.pyqtSignal(int)
    curve_edit_requested = QtCore.pyqtSignal()

    def __init__(self, backend: HpWmiFanBackend, parent=None) -> None:
        super().__init__(parent)
        self.backend = backend
        self.setObjectName("FanPanel")
        self.setStyleSheet(FAN_PANEL_QSS)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(10)

        self.title_label = QtWidgets.QLabel(t("fan.title"))
        self.title_label.setStyleSheet("color: #9aa0a6; font-size: 11px; letter-spacing: 1px;")
        root.addWidget(self.title_label)

        # 分段控件:4 个互斥模式按钮
        seg_row = QtWidgets.QHBoxLayout()
        seg_row.setSpacing(0)
        seg_row.setContentsMargins(0, 0, 0, 0)
        self.mode_btns: dict[str, QtWidgets.QPushButton] = {}
        self.mode_group = QtWidgets.QButtonGroup(self)
        self.mode_group.setExclusive(True)
        for i, key in enumerate(MODE_KEYS):
            btn = QtWidgets.QPushButton(mode_label(key))
            btn.setCheckable(True)
            btn.setProperty("role", "seg")
            pos = "left" if i == 0 else ("right" if i == len(MODE_KEYS) - 1 else "middle")
            btn.setProperty("seg_pos", pos)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            seg_row.addWidget(btn, 1)
            self.mode_group.addButton(btn)
            self.mode_btns[key] = btn
            btn.clicked.connect(lambda _c, k=key: self._emit_mode(k))
        root.addLayout(seg_row)

        # 滑条 + 数值 + 曲线编辑
        slider_row = QtWidgets.QHBoxLayout()
        slider_row.setSpacing(10)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        self.value_label = QtWidgets.QLabel("50 %")
        self.value_label.setStyleSheet("color: #f1f3f4; font-size: 13px; min-width: 48px;")
        self.value_label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight)
        self.curve_btn = QtWidgets.QPushButton(t("fan.curve_btn"))
        self.curve_btn.setProperty("role", "ghost")
        self.curve_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.curve_btn.setEnabled(False)
        slider_row.addWidget(self.slider, 1)
        slider_row.addWidget(self.value_label)
        slider_row.addWidget(self.curve_btn)
        root.addLayout(slider_row)

        # 状态(单行)
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        root.addWidget(self.status_label)

        self.slider.valueChanged.connect(
            lambda v: self.value_label.setText(f"{v} %")
        )
        self.slider.sliderReleased.connect(
            lambda: self.slider_applied.emit(self.slider.value())
        )
        self.curve_btn.clicked.connect(self.curve_edit_requested.emit)

        if not self.backend.available:
            self.setEnabled(False)
            self.status_label.setText(t("fan.disabled.summary") + " — " + t("fan.disabled.detail"))

    def _emit_mode(self, key: str) -> None:
        self.curve_btn.setEnabled(key in ("curve", "predict"))
        self.mode_changed.emit(key)

    def set_status(self, summary: str, detail: str = "") -> None:
        if detail:
            self.status_label.setText(f"{summary}  ·  {detail}")
        else:
            self.status_label.setText(summary)

    def set_mode_silent(self, key: str) -> None:
        btn = self.mode_btns.get(key)
        if btn is not None and not btn.isChecked():
            blocker = QtCore.QSignalBlocker(btn)
            btn.setChecked(True)
            del blocker
        self.curve_btn.setEnabled(key in ("curve", "predict"))

    def set_slider_silent(self, value: int) -> None:
        if value != self.slider.value():
            blocker = QtCore.QSignalBlocker(self.slider)
            self.slider.setValue(value)
            del blocker
            self.value_label.setText(f"{value} %")

    def mode(self) -> str:
        for key, btn in self.mode_btns.items():
            if btn.isChecked():
                return key
        return "auto"

    def retranslate(self) -> None:
        self.title_label.setText(t("fan.title"))
        for key, btn in self.mode_btns.items():
            btn.setText(mode_label(key))
        self.curve_btn.setText(t("fan.curve_btn"))
        if not self.backend.available:
            self.status_label.setText(t("fan.disabled.summary") + " — " + t("fan.disabled.detail"))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = user_config.load()
        set_lang(self.config.language)

        self.setWindowTitle(t("window.title"))
        self.resize(1180, 760)
        self.setStyleSheet("QMainWindow { background: #121216; } QLabel { color: #f1f3f4; }")
        if APP_ICON_PATH.exists():
            app_icon = QtGui.QIcon(str(APP_ICON_PATH))
            self.setWindowIcon(app_icon)
            QtWidgets.QApplication.setWindowIcon(app_icon)

        self.sampler = Sampler()
        self.fan_backend = HpWmiFanBackend()
        self.fan_mode = self.config.fan_mode
        self.fan_curve = load_curve()
        self._last_recommended_pwm = 0
        self._last_control_temp: float | None = None
        self._last_control_ts: float | None = None
        self._last_write_ts: float = 0.0
        self._applied_pwm_pct = self.config.fan_floor_pct

        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._save_config_now)

        self._quitting = False

        if self.config.window_geometry is not None:
            x, y, w, h = self.config.window_geometry
            self.setGeometry(x, y, w, h)

        n = HISTORY_SECONDS
        self.t_hist: deque[float] = deque(maxlen=n)
        self.cpu_temp_hist: deque[float] = deque(maxlen=n)
        self.gpu_temp_hist: deque[float] = deque(maxlen=n)
        self.cpu_util_hist: deque[float] = deque(maxlen=n)
        self.gpu_util_hist: deque[float] = deque(maxlen=n)
        self.nvme_temp_hist: deque[float] = deque(maxlen=n)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        tile_row = QtWidgets.QHBoxLayout()
        tile_row.setSpacing(6)
        self.tile_cpu_temp = StatTile("tile.cpu_temp")
        self.tile_cpu_util = StatTile("tile.cpu_util")
        self.tile_gpu_temp = StatTile("tile.gpu_temp")
        self.tile_gpu_util = StatTile("tile.gpu_util")
        self.tile_mem = StatTile("tile.mem")
        self.tile_nvme = StatTile("tile.nvme")
        self.tile_fan = StatTile("tile.fan")
        self._tiles = (
            self.tile_cpu_temp, self.tile_cpu_util,
            self.tile_gpu_temp, self.tile_gpu_util,
            self.tile_mem, self.tile_nvme, self.tile_fan,
        )
        for tile in self._tiles:
            tile_row.addWidget(tile)
        root.addLayout(tile_row)

        self.figure = Figure(figsize=(10, 5), facecolor="#1e1e24")
        self.canvas = FigureCanvas(self.figure)
        self.ax_temp = self.figure.add_subplot(2, 1, 1)
        self.ax_util = self.figure.add_subplot(2, 1, 2, sharex=self.ax_temp)
        for ax in (self.ax_temp, self.ax_util):
            ax.set_facecolor("#1e1e24")
            ax.tick_params(colors="#9aa0a6")
            for spine in ax.spines.values():
                spine.set_color("#3c4043")
            ax.grid(True, color="#2a2a30", linewidth=0.5)
        self.ax_temp.set_ylabel(t("plot.temp"), color="#9aa0a6")
        self.ax_util.set_ylabel(t("plot.util"), color="#9aa0a6")
        self.ax_util.set_xlabel(t("plot.time"), color="#9aa0a6")
        self.ax_temp.set_ylim(20, 105)
        self.ax_util.set_ylim(0, 100)
        self.figure.tight_layout()

        (self.line_cpu_t,) = self.ax_temp.plot([], [], label=t("plot.cpu_pkg"), color="#ff5252")
        (self.line_gpu_t,) = self.ax_temp.plot([], [], label=t("plot.gpu"), color="#40c4ff")
        (self.line_nvme_t,) = self.ax_temp.plot([], [], label=t("plot.nvme"), color="#b388ff")
        self._temp_legend = self.ax_temp.legend(loc="upper left", facecolor="#1e1e24", labelcolor="#f1f3f4", framealpha=0.8)

        (self.line_cpu_u,) = self.ax_util.plot([], [], label=t("plot.cpu"), color="#ff5252")
        (self.line_gpu_u,) = self.ax_util.plot([], [], label=t("plot.gpu"), color="#40c4ff")
        self._util_legend = self.ax_util.legend(loc="upper left", facecolor="#1e1e24", labelcolor="#f1f3f4", framealpha=0.8)

        # 把 canvas 包进卡片化的容器,与 FanPanel 视觉一致
        plot_card = QtWidgets.QFrame()
        plot_card.setStyleSheet("QFrame { background: #1e1e24; border-radius: 10px; }")
        plot_layout = QtWidgets.QVBoxLayout(plot_card)
        plot_layout.setContentsMargins(8, 8, 8, 8)
        plot_layout.addWidget(self.canvas)
        root.addWidget(plot_card, stretch=1)

        self.fan_panel = FanControlPanel(backend=self.fan_backend)
        root.addWidget(self.fan_panel)
        self.fan_panel.mode_changed.connect(self._on_fan_mode_changed)
        self.fan_panel.slider_applied.connect(self._on_fan_slider_applied)
        self.fan_panel.curve_edit_requested.connect(self._open_curve_editor)
        self.fan_panel.set_mode_silent(self.fan_mode)
        self._sync_fan_state()

        sb = self.statusBar()
        sb.setStyleSheet("color: #80868b;")
        sb.showMessage(t("app.starting"))
        self._start_ts = time.time()

        self._build_menubar()

        self.tray = TrayIcon(self)
        if self.tray.available:
            self.tray.show_requested.connect(self._show_window)
            self.tray.hide_requested.connect(self.hide)
            self.tray.toggle_requested.connect(self._toggle_window)
            self.tray.mode_changed.connect(self._set_mode_from_tray)
            self.tray.manual_pwm_requested.connect(self._set_manual_pwm_from_tray)
            self.tray.quit_requested.connect(self._quit_app)
            self.tray.update_visibility(self.isVisible())
            self.tray.update_mode(self.fan_mode)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(SAMPLE_INTERVAL_MS)
        self.on_tick()

    def _sync_fan_state(self) -> None:
        """把 UI 设为 config 中保存的模式 / 底线;并记录当前硬件 PWM 用于去抖比较。"""
        self.fan_panel.set_slider_silent(self.config.fan_floor_pct)
        self.fan_panel.set_mode_silent(self.fan_mode)
        if self.fan_backend.available:
            _, pwm = self.fan_backend.read_state()
            if pwm is not None:
                self._applied_pwm_pct = pwm_to_pct(pwm)

    def _top_process_summary(self, s: Sample) -> str:
        if not s.top_processes:
            return t("proc.none")
        top = s.top_processes[:3]
        parts = [f"{pid}:{name} {cpu:.0f}%/{mem:.0f}%" for pid, name, cpu, mem in top]
        return t("proc.prefix") + " · ".join(parts)

    def _apply_pwm_percent(self, percent: int) -> None:
        if not self.fan_backend.available:
            return
        rc, msg = self.fan_backend.set_percent(percent)
        if rc == 0:
            self._applied_pwm_pct = percent
            self._last_write_ts = time.time()
            self.fan_panel.set_status(t("fan.status.manual_applied", pct=percent), "")
        else:
            self.fan_panel.set_status(t("fan.status.write_fail", rc=rc), msg[:120])

    def _set_auto_mode(self) -> None:
        if not self.fan_backend.available:
            return
        rc, msg = self.fan_backend.set_auto()
        if rc == 0:
            self.fan_mode = "auto"
            self.fan_panel.set_mode_silent("auto")
            self.fan_panel.set_status(t("fan.status.auto"), t("fan.status.auto_sub"))
        else:
            self.fan_panel.set_status(t("fan.status.auto_fail", rc=rc), msg[:120])

    def _on_fan_mode_changed(self, key: str) -> None:
        self.fan_mode = key
        if key == "auto":
            self._set_auto_mode()
        elif key == "manual":
            self._apply_pwm_percent(self.fan_panel.slider.value())
        self._schedule_save()

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def _save_config_now(self) -> None:
        geom = self.geometry()
        self.config.fan_mode = self.fan_mode
        self.config.fan_floor_pct = self.fan_panel.slider.value()
        self.config.window_geometry = (geom.x(), geom.y(), geom.width(), geom.height())
        try:
            user_config.save(self.config)
        except OSError as e:
            self.statusBar().showMessage(t("save.config_fail", err=str(e)))

    def closeEvent(self, event) -> None:
        self._save_timer.stop()
        self._save_config_now()
        if self.tray.available and not self._quitting:
            event.ignore()
            self.hide()
            self.tray.update_visibility(False)
            return
        super().closeEvent(event)

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if self.tray.available:
            self.tray.update_visibility(True)

    def _toggle_window(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
            if self.tray.available:
                self.tray.update_visibility(False)
        else:
            self._show_window()

    def _quit_app(self) -> None:
        self._quitting = True
        QtWidgets.QApplication.quit()

    def _set_mode_from_tray(self, key: str) -> None:
        self.fan_panel.set_mode_silent(key)
        self.fan_mode = key
        if key == "auto":
            self._set_auto_mode()
        elif key == "manual":
            self._apply_pwm_percent(self.fan_panel.slider.value())
        self._schedule_save()

    def _set_manual_pwm_from_tray(self, pct: int) -> None:
        self.fan_panel.set_mode_silent("manual")
        self.fan_panel.set_slider_silent(pct)
        self.fan_mode = "manual"
        self._apply_pwm_percent(pct)
        self._schedule_save()

    # ---------------- menubar + i18n ----------------

    def _build_menubar(self) -> None:
        mb = self.menuBar()
        mb.setStyleSheet(
            "QMenuBar { background: #1a1a20; color: #c7c9cc; padding: 2px; }"
            "QMenuBar::item:selected { background: #2a2a30; }"
            "QMenu { background: #1e1e24; color: #f1f3f4; }"
            "QMenu::item:selected { background: #2a2a30; }"
        )
        self.lang_menu = mb.addMenu(t("menu.language"))
        self.lang_actions: dict[str, QtWidgets.QAction] = {}
        group = QtWidgets.QActionGroup(self)
        group.setExclusive(True)
        for code in available_langs():
            act = self.lang_menu.addAction(lang_display(code))
            act.setCheckable(True)
            act.setChecked(code == self.config.language)
            group.addAction(act)
            act.triggered.connect(lambda _checked, c=code: self._set_language(c))
            self.lang_actions[code] = act

    def _set_language(self, code: str) -> None:
        if code == self.config.language:
            return
        set_lang(code)
        self.config.language = code
        self._schedule_save()
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(t("window.title"))
        # menubar
        if hasattr(self, "lang_menu"):
            self.lang_menu.setTitle(t("menu.language"))
            for code, act in self.lang_actions.items():
                act.setText(lang_display(code))
        # tiles
        for tile in self._tiles:
            tile.retranslate()
        # plot axes + legends
        self.ax_temp.set_ylabel(t("plot.temp"), color="#9aa0a6")
        self.ax_util.set_ylabel(t("plot.util"), color="#9aa0a6")
        self.ax_util.set_xlabel(t("plot.time"), color="#9aa0a6")
        self.line_cpu_t.set_label(t("plot.cpu_pkg"))
        self.line_gpu_t.set_label(t("plot.gpu"))
        self.line_nvme_t.set_label(t("plot.nvme"))
        self.line_cpu_u.set_label(t("plot.cpu"))
        self.line_gpu_u.set_label(t("plot.gpu"))
        self.ax_temp.legend(loc="upper left", facecolor="#1e1e24", labelcolor="#f1f3f4", framealpha=0.8)
        self.ax_util.legend(loc="upper left", facecolor="#1e1e24", labelcolor="#f1f3f4", framealpha=0.8)
        self.canvas.draw_idle()
        # fan panel
        self.fan_panel.retranslate()
        # tray
        if self.tray.available:
            self.tray.retranslate()
        # 立即跑一次 on_tick 让动态字符串(状态栏/进程/tooltip 等)也用新语言
        self.on_tick()

    def _open_curve_editor(self) -> None:
        hint = self._last_control_temp
        dlg = FanCurveDialog(self.fan_curve, current_temp_hint=hint, parent=self)
        dlg.curve_applied.connect(self._on_curve_applied)
        dlg.exec_()

    def _on_curve_applied(self, new_curve: list) -> None:
        self.fan_curve = new_curve
        try:
            save_curve(new_curve)
        except OSError as e:
            self.statusBar().showMessage(t("save.curve_fail", err=str(e)))

    def _on_fan_slider_applied(self, value: int) -> None:
        if self.fan_mode == "auto":
            return
        if self.fan_mode == "manual":
            self._apply_pwm_percent(value)
        else:
            self._last_recommended_pwm = max(self._last_recommended_pwm, value)
        self._schedule_save()

    def on_tick(self) -> None:
        s = self.sampler.sample()

        self.t_hist.append(s.ts)
        self.cpu_temp_hist.append(s.cpu_pkg if s.cpu_pkg is not None else float("nan"))
        self.gpu_temp_hist.append(s.gpu_temp if s.gpu_temp is not None else float("nan"))
        max_nvme = max((v for _, v in s.nvme_temps), default=float("nan"))
        self.nvme_temp_hist.append(max_nvme)
        self.cpu_util_hist.append(s.cpu_util_total)
        self.gpu_util_hist.append(s.gpu_util if s.gpu_util is not None else float("nan"))

        if s.cpu_pkg is not None:
            sub = (
                t("tile.cpu_cores", lo=min(s.cpu_cores), hi=max(s.cpu_cores))
                if s.cpu_cores else ""
            )
            self.tile_cpu_temp.set_value(f"{s.cpu_pkg:.0f} °C", sub, temp_color(s.cpu_pkg))
        freq_txt = f"{s.cpu_freq_mhz / 1000:.2f} GHz" if s.cpu_freq_mhz else ""
        self.tile_cpu_util.set_value(f"{s.cpu_util_total:.0f} %", freq_txt)

        self.tile_gpu_temp.set_value(
            f"{s.gpu_temp:.0f} °C" if s.gpu_temp is not None else "n/a",
            "RTX 4060 Laptop",
            temp_color(s.gpu_temp),
        )
        if s.gpu_util is not None:
            self.tile_gpu_util.set_value(
                f"{s.gpu_util:.0f} %",
                f"{s.gpu_power:.0f} W · {s.gpu_mem_used:.0f}/{s.gpu_mem_total:.0f} MiB"
                if s.gpu_power is not None and s.gpu_mem_used is not None
                else "",
            )

        self.tile_mem.set_value(
            f"{s.mem_used_gb:.1f} / {s.mem_total_gb:.0f} GiB",
            f"{100 * s.mem_used_gb / s.mem_total_gb:.0f} %" if s.mem_total_gb else "",
        )

        if s.nvme_temps:
            top = max(s.nvme_temps, key=lambda x: x[1])
            self.tile_nvme.set_value(f"{top[1]:.0f} °C", top[0], temp_color(top[1]))

        if s.fan_rpm:
            joined = " · ".join(f"{r}" for r in s.fan_rpm)
            self.tile_fan.set_value(joined, t("tile.fan.unit"))
        else:
            self.tile_fan.set_value("--", t("tile.fan.norpm"))

        current_mode = self.fan_mode
        floor = self.fan_panel.slider.value()
        recommended_pwm, reason = predict_pwm(
            s,
            current_mode,
            self._last_control_temp,
            self._last_control_ts,
            floor,
            curve=self.fan_curve,
        )
        self._last_control_temp = current_temp(s)
        self._last_control_ts = s.ts
        if current_mode in ("curve", "predict"):
            if abs(recommended_pwm - self._applied_pwm_pct) >= 2 or (time.time() - self._last_write_ts) > 4:
                self._apply_pwm_percent(recommended_pwm)
        elif current_mode == "manual":
            self.fan_panel.set_status(
                t("fan.status.manual", pct=self.fan_panel.slider.value()),
                self._top_process_summary(s),
            )

        if current_mode in ("curve", "predict"):
            self.fan_panel.set_status(
                t("fan.status.curve_pred", mode=mode_label(current_mode), pwm=recommended_pwm, floor=floor),
                f"{reason} · {self._top_process_summary(s)}",
            )
        elif current_mode == "auto":
            self.fan_panel.set_status(t("fan.status.auto"), self._top_process_summary(s))

        if s.fan_enable is not None:
            enable_desc = {0: "max", 1: "manual", 2: "auto"}.get(s.fan_enable, str(s.fan_enable))
            actual_pwm = s.fan_pwm if s.fan_pwm is not None else 0
            self.statusBar().showMessage(t(
                "sb.sample_fan",
                n=len(self.t_hist),
                fan_desc=enable_desc,
                pwm=actual_pwm,
                reason=reason,
                procs=self._top_process_summary(s),
            ))
        else:
            self.statusBar().showMessage(t(
                "sb.sample_plain",
                n=len(self.t_hist),
                ms=SAMPLE_INTERVAL_MS,
                procs=self._top_process_summary(s),
            ))

        if len(self.t_hist) > 1:
            ts_axis = [ti - self.t_hist[-1] for ti in self.t_hist]
            self.line_cpu_t.set_data(ts_axis, list(self.cpu_temp_hist))
            self.line_gpu_t.set_data(ts_axis, list(self.gpu_temp_hist))
            self.line_nvme_t.set_data(ts_axis, list(self.nvme_temp_hist))
            self.line_cpu_u.set_data(ts_axis, list(self.cpu_util_hist))
            self.line_gpu_u.set_data(ts_axis, list(self.gpu_util_hist))
            self.ax_temp.set_xlim(ts_axis[0], 0)
            self.ax_util.set_xlim(ts_axis[0], 0)
            self.canvas.draw_idle()

        if self.tray.available:
            self.tray.update_status(
                cpu_temp=s.cpu_pkg,
                cpu_util=s.cpu_util_total,
                gpu_temp=s.gpu_temp,
                gpu_util=s.gpu_util,
                fan_rpm_max=max(s.fan_rpm) if s.fan_rpm else None,
                fan_enable=s.fan_enable,
                fan_pwm_raw=s.fan_pwm,
            )
            self.tray.update_mode(self.fan_mode)
            self.tray.update_visibility(self.isVisible())
