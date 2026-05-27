"""运行时配置持久化:模式、底线 PWM、窗口几何。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


from . import i18n


SCHEMA_VERSION = 2
DEFAULT_MODE = "auto"
DEFAULT_FLOOR_PCT = 50
DEFAULT_LANG = i18n.DEFAULT_LANG

VALID_MODES = ("auto", "manual", "curve", "predict")

# 兼容 schema v1 (中文 mode key)
_LEGACY_MODE_MAP = {
    "自动": "auto",
    "手动": "manual",
    "温度曲线": "curve",
    "预测控制": "predict",
}


@dataclass
class Config:
    fan_mode: str = DEFAULT_MODE
    fan_floor_pct: int = DEFAULT_FLOOR_PCT
    window_geometry: tuple[int, int, int, int] | None = None  # (x, y, w, h)
    language: str = DEFAULT_LANG
    schema_version: int = SCHEMA_VERSION


def _config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "omen-monitor" / "config.json"


def _coerce_mode(value) -> str:
    if isinstance(value, str):
        if value in VALID_MODES:
            return value
        if value in _LEGACY_MODE_MAP:  # 旧 schema v1 中文 key
            return _LEGACY_MODE_MAP[value]
    return DEFAULT_MODE


def _coerce_lang(value) -> str:
    if isinstance(value, str) and value in i18n.available_langs():
        return value
    return DEFAULT_LANG


def _coerce_floor(value) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_FLOOR_PCT


def _coerce_geometry(value) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, w, h = (int(v) for v in value)
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return (x, y, w, h)


def load(path: Path | None = None) -> Config:
    p = path or _config_path()
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return Config()
    if not isinstance(data, dict):
        return Config()
    return Config(
        fan_mode=_coerce_mode(data.get("fan_mode")),
        fan_floor_pct=_coerce_floor(data.get("fan_floor_pct")),
        window_geometry=_coerce_geometry(data.get("window_geometry")),
        language=_coerce_lang(data.get("language")),
    )


def save(config: Config, path: Path | None = None) -> None:
    p = path or _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(config)
    if payload.get("window_geometry") is not None:
        payload["window_geometry"] = list(payload["window_geometry"])
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(p)
