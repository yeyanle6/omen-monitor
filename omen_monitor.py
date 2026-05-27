#!/usr/bin/env python3
"""OMEN 16-wf0 温控/占用监控 + 风扇控制 GUI 入口。"""

from __future__ import annotations

import fcntl
import os
import sys
from pathlib import Path

from PyQt5 import QtWidgets

from omen import config as user_config
from omen.gui import MainWindow
from omen.i18n import set_lang, t


def _lock_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    d = Path(base) / "omen-monitor"
    d.mkdir(parents=True, exist_ok=True)
    return d / "omen-monitor.lock"


def _acquire_lock():
    """抢独占锁;返回打开的 file handle(保持引用即持锁)。失败返回 None。"""
    path = _lock_path()
    fh = open(path, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 让 lock-busy 弹窗使用用户上次保存的语言
    set_lang(user_config.load().language)

    lock = _acquire_lock()
    if lock is None:
        QtWidgets.QMessageBox.warning(None, t("lock.title"), t("lock.body"))
        return 1

    w = MainWindow()
    w.show()
    rc = app.exec_()
    lock.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
