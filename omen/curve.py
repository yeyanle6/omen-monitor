"""用户可编辑的风扇曲线 (温度 → PWM%) 折线 + 线性插值 + JSON IO。"""

from __future__ import annotations

import json
import os
from pathlib import Path


FanCurve = list[tuple[float, int]]

SCHEMA_VERSION = 1

DEFAULT_CURVE: FanCurve = [
    (40.0, 18),
    (58.0, 26),
    (64.0, 34),
    (68.0, 44),
    (72.0, 54),
    (76.0, 64),
    (80.0, 74),
    (84.0, 84),
    (88.0, 94),
    (92.0, 100),
]


def _config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "omen-monitor" / "curve.json"


def normalize(curve: FanCurve) -> FanCurve:
    """按温度升序排序、去重、clamp 到合法范围。"""
    seen: dict[float, int] = {}
    for t, p in curve:
        t = float(t)
        p = max(0, min(100, int(round(p))))
        seen[t] = p
    return sorted(seen.items(), key=lambda kv: kv[0])


def interpolate(curve: FanCurve, temp: float) -> int:
    """线性插值;曲线为空时返回 0;两端按端点 clamp。"""
    if not curve:
        return 0
    curve = normalize(curve)
    if temp <= curve[0][0]:
        return curve[0][1]
    if temp >= curve[-1][0]:
        return curve[-1][1]
    for (t0, p0), (t1, p1) in zip(curve, curve[1:]):
        if t0 <= temp <= t1:
            if t1 == t0:
                return p1
            ratio = (temp - t0) / (t1 - t0)
            return max(0, min(100, int(round(p0 + ratio * (p1 - p0)))))
    return curve[-1][1]


def load_curve(path: Path | None = None) -> FanCurve:
    """从 JSON 读曲线;失败/不存在/格式错时回退到 DEFAULT_CURVE。"""
    p = path or _config_path()
    try:
        data = json.loads(p.read_text())
        points = data.get("curve") if isinstance(data, dict) else None
        if not isinstance(points, list):
            return list(DEFAULT_CURVE)
        out: FanCurve = []
        for entry in points:
            if isinstance(entry, list) and len(entry) == 2:
                out.append((float(entry[0]), int(entry[1])))
        if not out:
            return list(DEFAULT_CURVE)
        return normalize(out)
    except (OSError, ValueError, TypeError):
        return list(DEFAULT_CURVE)


def save_curve(curve: FanCurve, path: Path | None = None) -> None:
    p = path or _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SCHEMA_VERSION,
        "curve": [[float(t), int(pwm)] for t, pwm in normalize(curve)],
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(p)
