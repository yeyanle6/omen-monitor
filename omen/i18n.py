"""Plug-and-play i18n:启动时扫描 omen/locales/*.json,新增语言无需改代码。

每个 JSON 文件结构:
  {
    "_lang_code": "zh",          // 必填,语言代码(等于文件名 stem)
    "_lang_display": "中文",      // 必填,菜单中显示的语言名(用该语言本身的写法)
    "window.title": "...",
    "tile.cpu_temp": "...",
    ...
  }

下划线开头的 key 是元数据,不参与 t() 检索。
"""

from __future__ import annotations

import json
from pathlib import Path


_LOCALES_DIR = Path(__file__).parent / "locales"
DEFAULT_LANG = "zh"
FALLBACK_LANG = "en"

_all_translations: dict[str, dict[str, str]] = {}
_lang_display: dict[str, str] = {}
_current_lang = DEFAULT_LANG


def _load_all() -> None:
    """扫描 locales/ 目录,加载全部语言。出错的文件跳过 + 警告。"""
    _all_translations.clear()
    _lang_display.clear()
    if not _LOCALES_DIR.is_dir():
        return
    for f in sorted(_LOCALES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            import sys
            print(f"[i18n] skip {f.name}: {e}", file=sys.stderr)
            continue
        if not isinstance(data, dict):
            continue
        code = data.get("_lang_code") or f.stem
        display = data.get("_lang_display") or code
        # 剔除元数据 key (以 _ 开头)
        body = {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, str)}
        _all_translations[code] = body
        _lang_display[code] = display


_load_all()


# ---------- public API ----------

def available_langs() -> list[str]:
    """按语言代码排序的所有可用语言。"""
    return sorted(_all_translations.keys())


def lang_display(code: str) -> str:
    """该语言用它自己写法的显示名(菜单用)。"""
    return _lang_display.get(code, code)


def get_lang() -> str:
    return _current_lang


def set_lang(lang: str) -> None:
    global _current_lang
    if lang in _all_translations:
        _current_lang = lang


def t(key: str, **fmt) -> str:
    """查 key。缺译落回 fallback,再缺落回 key 自身(显著标识便于排查)。"""
    text = _all_translations.get(_current_lang, {}).get(key)
    if text is None:
        text = _all_translations.get(FALLBACK_LANG, {}).get(key, key)
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return text
    return text


# ---------- fan mode helper ----------

MODE_KEYS: tuple[str, ...] = ("auto", "manual", "curve", "predict")


def mode_label(key: str) -> str:
    return t(f"mode.{key}") if key in MODE_KEYS else key
