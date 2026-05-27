"""系统托盘:风扇 symbolic 图标 + mini 风扇控制 + 状态摘要。

GNOME AppIndicator 通常不显示 QSystemTrayIcon 的 tooltip,所以实时
温度/占用走菜单顶部的只读 status_action,而不是 tooltip。
"""

from __future__ import annotations

from pathlib import Path

from PyQt5 import QtCore, QtGui, QtSvg, QtWidgets

from .i18n import MODE_KEYS, mode_label, t


ICON_SIZE = 24

COLOR_HOT_CRIT = "#ff5252"
COLOR_HOT = "#ff9100"
COLOR_WARM = "#ffd740"
COLOR_COOL = "#69f0ae"
COLOR_DIM = "#9aa0a6"

_FAN_SVG = Path(__file__).parent / "assets" / "icon.svg"
_fan_renderer: QtSvg.QSvgRenderer | None = None


def _get_fan_renderer() -> QtSvg.QSvgRenderer | None:
    """懒加载 SVG 渲染器,避免 QApplication 还没起就解析。"""
    global _fan_renderer
    if _fan_renderer is None and _FAN_SVG.exists():
        _fan_renderer = QtSvg.QSvgRenderer(str(_FAN_SVG))
    return _fan_renderer


def _temp_color(t_val: float | None) -> str:
    if t_val is None:
        return COLOR_DIM
    if t_val >= 90:
        return COLOR_HOT_CRIT
    if t_val >= 80:
        return COLOR_HOT
    if t_val >= 70:
        return COLOR_WARM
    return COLOR_COOL


class TrayIcon(QtCore.QObject):
    show_requested = QtCore.pyqtSignal()
    hide_requested = QtCore.pyqtSignal()
    toggle_requested = QtCore.pyqtSignal()
    mode_changed = QtCore.pyqtSignal(str)            # emits mode key
    manual_pwm_requested = QtCore.pyqtSignal(int)
    quit_requested = QtCore.pyqtSignal()

    QUICK_PWM_VALUES = (30, 50, 70, 100)

    def __init__(self, parent: QtWidgets.QMainWindow) -> None:
        super().__init__(parent)
        self._parent = parent
        self.tray: QtWidgets.QSystemTrayIcon | None = None
        self._mode_actions: dict[str, QtWidgets.QAction] = {}
        self._quick_actions: list[tuple[int, QtWidgets.QAction]] = []
        self._quick_menu: QtWidgets.QMenu | None = None

        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray = QtWidgets.QSystemTrayIcon(self._make_fan_icon(), parent)
        self.tray.setToolTip(t("tray.title"))

        menu = QtWidgets.QMenu(parent)
        menu.setStyleSheet(
            "QMenu { background: #1e1e24; color: #f1f3f4; padding: 4px; }"
            "QMenu::item { padding: 4px 14px; }"
            "QMenu::item:selected { background: #2a2a30; }"
            "QMenu::item:disabled { color: #9aa0a6; }"
            "QMenu::separator { height: 1px; background: #3c4043; margin: 4px 8px; }"
        )

        # 只读状态行
        self.status_action = menu.addAction(t("tray.title"))
        self.status_action.setEnabled(False)
        self.fan_state_action = menu.addAction(t("tray.fan_line",
                                                 desc="--", rpm=t("tray.rpm_none"), pwm=t("tray.pwm_none")))
        self.fan_state_action.setEnabled(False)
        menu.addSeparator()

        # 模式(单选)
        self.mode_group = QtWidgets.QActionGroup(parent)
        self.mode_group.setExclusive(True)
        for key in MODE_KEYS:
            act = menu.addAction(mode_label(key))
            act.setCheckable(True)
            self.mode_group.addAction(act)
            act.triggered.connect(lambda _checked, k=key: self.mode_changed.emit(k))
            self._mode_actions[key] = act
        menu.addSeparator()

        # 快速手动 PWM
        self._quick_menu = menu.addMenu(t("tray.quick_pwm"))
        for pct in self.QUICK_PWM_VALUES:
            a = self._quick_menu.addAction(t("tray.quick_pct", pct=pct))
            a.triggered.connect(lambda _checked, p=pct: self.manual_pwm_requested.emit(p))
            self._quick_actions.append((pct, a))
        menu.addSeparator()

        # 窗口控制
        self.show_action = menu.addAction(t("tray.show"))
        self.show_action.triggered.connect(self.show_requested.emit)
        self.hide_action = menu.addAction(t("tray.hide"))
        self.hide_action.triggered.connect(self.hide_requested.emit)
        menu.addSeparator()
        self.quit_action = menu.addAction(t("tray.quit"))
        self.quit_action.triggered.connect(self.quit_requested.emit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    # ---------------- public API ----------------

    @property
    def available(self) -> bool:
        return self.tray is not None

    def _on_activated(self, reason) -> None:
        if reason in (
            QtWidgets.QSystemTrayIcon.Trigger,
            QtWidgets.QSystemTrayIcon.DoubleClick,
        ):
            self.toggle_requested.emit()

    def update_visibility(self, window_visible: bool) -> None:
        if not self.tray:
            return
        self.show_action.setEnabled(not window_visible)
        self.hide_action.setEnabled(window_visible)

    def update_mode(self, mode_key: str) -> None:
        act = self._mode_actions.get(mode_key)
        if act is not None and not act.isChecked():
            blocker = QtCore.QSignalBlocker(act)
            act.setChecked(True)
            del blocker

    def update_status(
        self,
        cpu_temp: float | None,
        cpu_util: float | None,
        gpu_temp: float | None,
        gpu_util: float | None,
        fan_rpm_max: int | None,
        fan_enable: int | None,
        fan_pwm_raw: int | None,
    ) -> None:
        if not self.tray:
            return

        # 图标固定为风扇 symbolic 形状(同 wifi 风格,不随温度变化),
        # 温度数值在菜单 status_action / tooltip 里显示。

        cpu_part = t("tray.status.cpu_full", temp=cpu_temp, util=cpu_util) \
            if cpu_temp is not None and cpu_util is not None else t("tray.status.cpu_none")
        if gpu_temp is not None and gpu_util is not None:
            gpu_part = t("tray.status.gpu_full", temp=gpu_temp, util=gpu_util)
        elif gpu_temp is not None:
            gpu_part = t("tray.status.gpu_temp", temp=gpu_temp)
        else:
            gpu_part = t("tray.status.gpu_none")
        self.status_action.setText(f"{cpu_part}    {gpu_part}")

        fan_desc = {0: "max", 1: "manual", 2: "auto"}.get(fan_enable, "--") if fan_enable is not None else "--"
        rpm_desc = t("tray.rpm_val", n=fan_rpm_max) if fan_rpm_max else t("tray.rpm_none")
        pwm_desc = t("tray.pwm_val", n=fan_pwm_raw) if fan_pwm_raw is not None else t("tray.pwm_none")
        self.fan_state_action.setText(t("tray.fan_line", desc=fan_desc, rpm=rpm_desc, pwm=pwm_desc))

        self.tray.setToolTip(
            t("tray.tooltip", cpu=cpu_part, gpu=gpu_part, fan_desc=fan_desc, rpm=rpm_desc)
        )

    def retranslate(self) -> None:
        """切换语言后调用,重写所有静态菜单文本(动态状态行由下次 update_status 刷新)。"""
        if not self.tray:
            return
        self.tray.setToolTip(t("tray.title"))
        for key, act in self._mode_actions.items():
            act.setText(mode_label(key))
        if self._quick_menu is not None:
            self._quick_menu.setTitle(t("tray.quick_pwm"))
            for pct, a in self._quick_actions:
                a.setText(t("tray.quick_pct", pct=pct))
        self.show_action.setText(t("tray.show"))
        self.hide_action.setText(t("tray.hide"))
        self.quit_action.setText(t("tray.quit"))

    # ---------------- 图标绘制 ----------------

    _cached_icon: QtGui.QIcon | None = None

    @classmethod
    def _make_fan_icon(cls) -> QtGui.QIcon:
        """单色风扇图标(symbolic 风格),给 QSystemTrayIcon 和 windowIcon 共用。"""
        if cls._cached_icon is not None:
            return cls._cached_icon
        pix = QtGui.QPixmap(ICON_SIZE, ICON_SIZE)
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        renderer = _get_fan_renderer()
        if renderer is not None and renderer.isValid():
            renderer.render(p, QtCore.QRectF(0, 0, ICON_SIZE, ICON_SIZE))
        else:
            p.setBrush(QtGui.QColor("#ffffff"))
            p.setPen(QtCore.Qt.NoPen)
            p.drawEllipse(2, 2, ICON_SIZE - 4, ICON_SIZE - 4)
        p.end()
        cls._cached_icon = QtGui.QIcon(pix)
        return cls._cached_icon
