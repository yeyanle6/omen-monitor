"""风扇曲线交互编辑器(QDialog + matplotlib)。

操作:
- 左键拖动节点 — 调整 (温度, PWM%)
- 双击空白处 — 添加节点
- 右键节点 — 删除(至少保留 2 个)
- 重置默认 / 取消 / 应用
"""

from __future__ import annotations

from PyQt5 import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from .curve import DEFAULT_CURVE, FanCurve, interpolate, normalize
from .i18n import t


TEMP_MIN = 30.0
TEMP_MAX = 110.0
PICK_RADIUS_PX = 12  # 像素半径,判定是否点中节点


class FanCurveDialog(QtWidgets.QDialog):
    curve_applied = QtCore.pyqtSignal(list)  # FanCurve

    def __init__(self, current_curve: FanCurve, current_temp_hint: float | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("curve.title"))
        self.resize(720, 520)
        self.setStyleSheet("QDialog { background: #121216; } QLabel { color: #f1f3f4; }")

        self._curve: FanCurve = normalize(list(current_curve)) if current_curve else list(DEFAULT_CURVE)
        self._current_temp_hint = current_temp_hint
        self._drag_index: int | None = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.hint_label = QtWidgets.QLabel(t("curve.hint"))
        self.hint_label.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        root.addWidget(self.hint_label)

        self.figure = Figure(figsize=(7, 4), facecolor="#121216")
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(1, 1, 1)
        self._style_axes()
        root.addWidget(self.canvas, stretch=1)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color: #c7c9cc; font-size: 11px;")
        root.addWidget(self.status)

        button_row = QtWidgets.QHBoxLayout()
        self.reset_btn = QtWidgets.QPushButton(t("curve.reset"))
        self.cancel_btn = QtWidgets.QPushButton(t("curve.cancel"))
        self.apply_btn = QtWidgets.QPushButton(t("curve.apply"))
        for b in (self.reset_btn, self.cancel_btn, self.apply_btn):
            button_row.addWidget(b)
        root.addLayout(button_row)

        self.reset_btn.clicked.connect(self._on_reset)
        self.cancel_btn.clicked.connect(self.reject)
        self.apply_btn.clicked.connect(self._on_apply)

        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)

        self._redraw()

    def _style_axes(self) -> None:
        ax = self.ax
        ax.set_facecolor("#1e1e24")
        ax.tick_params(colors="#9aa0a6")
        for spine in ax.spines.values():
            spine.set_color("#3c4043")
        ax.grid(True, color="#2a2a30", linewidth=0.5)
        ax.set_xlim(TEMP_MIN, TEMP_MAX)
        ax.set_ylim(0, 105)
        ax.set_xlabel(t("curve.xlabel"), color="#9aa0a6")
        ax.set_ylabel(t("curve.ylabel"), color="#9aa0a6")

    def _redraw(self) -> None:
        self.ax.clear()
        self._style_axes()
        xs = [t for t, _ in self._curve]
        ys = [p for _, p in self._curve]
        self.ax.plot(xs, ys, color="#40c4ff", linewidth=1.8, zorder=2)
        self.ax.scatter(xs, ys, color="#ff9100", s=60, zorder=3, picker=True)
        if self._current_temp_hint is not None and TEMP_MIN <= self._current_temp_hint <= TEMP_MAX:
            self.ax.axvline(self._current_temp_hint, color="#ff5252", linewidth=0.8, linestyle="--", alpha=0.7)
            pwm_now = interpolate(self._curve, self._current_temp_hint)
            self.ax.text(
                self._current_temp_hint + 1, 95,
                t("curve.current", temp=self._current_temp_hint, pwm=pwm_now),
                color="#ff5252", fontsize=9,
            )
        self.figure.tight_layout()
        self.canvas.draw_idle()
        nodes_str = ", ".join(f"({temp:.0f},{p})" for temp, p in self._curve)
        self.status.setText(t("curve.summary", n=len(self._curve), nodes=nodes_str))

    # ---------------- 鼠标事件 ----------------

    def _pick_node(self, event) -> int | None:
        """返回距离 event 像素最近且在 PICK_RADIUS_PX 内的节点索引,无则 None。"""
        if event.x is None or event.y is None:
            return None
        best: tuple[int, float] | None = None
        for i, (t, p) in enumerate(self._curve):
            dx = self.ax.transData.transform((t, p)) - (event.x, event.y)
            dist = (dx[0] ** 2 + dx[1] ** 2) ** 0.5
            if best is None or dist < best[1]:
                best = (i, dist)
        if best and best[1] <= PICK_RADIUS_PX:
            return best[0]
        return None

    def _on_press(self, event) -> None:
        if event.inaxes is not self.ax:
            return
        idx = self._pick_node(event)
        if event.button == 1:  # 左键
            if idx is not None:
                if event.dblclick:
                    return  # 双击在节点上忽略,避免重复加点
                self._drag_index = idx
            elif event.dblclick and event.xdata is not None and event.ydata is not None:
                new_pt = (float(event.xdata), int(round(max(0, min(100, event.ydata)))))
                self._curve = normalize(self._curve + [new_pt])
                self._redraw()
        elif event.button == 3:  # 右键
            if idx is not None and len(self._curve) > 2:
                self._curve = self._curve[:idx] + self._curve[idx + 1:]
                self._redraw()

    def _on_motion(self, event) -> None:
        if self._drag_index is None or event.inaxes is not self.ax:
            return
        if event.xdata is None or event.ydata is None:
            return
        new_t = float(event.xdata)
        new_p = int(round(max(0, min(100, event.ydata))))
        # 不允许越过相邻节点 — 保持温度严格升序
        idx = self._drag_index
        left = self._curve[idx - 1][0] + 0.5 if idx > 0 else TEMP_MIN
        right = self._curve[idx + 1][0] - 0.5 if idx < len(self._curve) - 1 else TEMP_MAX
        new_t = max(left, min(right, new_t))
        self._curve = self._curve[:idx] + [(new_t, new_p)] + self._curve[idx + 1:]
        self._redraw()

    def _on_release(self, event) -> None:
        if self._drag_index is not None:
            self._curve = normalize(self._curve)
            self._drag_index = None
            self._redraw()

    # ---------------- 按钮 ----------------

    def _on_reset(self) -> None:
        self._curve = list(DEFAULT_CURVE)
        self._redraw()

    def _on_apply(self) -> None:
        self.curve_applied.emit(list(self._curve))
        self.accept()

    def current_curve(self) -> FanCurve:
        return list(self._curve)
