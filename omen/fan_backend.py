"""通过 patched hp-wmi 的 hwmon 节点控制风扇。

写路径走 /usr/local/sbin/omen-fanctl (sudo NOPASSWD),
节点位置由 /sys/class/hwmon/hwmon*/name == "hp" 自动定位。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .sampler import (
    FAN_PWM_MAX,
    FAN_PWM_MIN,
    HWMON_ROOT,
    _read_int,
    pct_to_pwm,
)


FAN_HELPER = Path("/usr/local/sbin/omen-fanctl")


class HpWmiFanBackend:
    """通过 hp-wmi 的 hwmon 节点控制风扇。"""

    def __init__(self, hwmon_root: Path = HWMON_ROOT) -> None:
        self.hwmon_root = hwmon_root
        self.node = self._find_node()
        self._sudo = shutil.which("sudo")

    def _find_node(self) -> Path | None:
        for entry in self.hwmon_root.iterdir():
            try:
                if (entry / "name").read_text().strip() == "hp" and (entry / "pwm1").exists():
                    return entry
            except OSError:
                continue
        return None

    @property
    def available(self) -> bool:
        return self.node is not None

    def read(self, filename: str) -> int | None:
        if not self.node:
            return None
        return _read_int(self.node / filename)

    def read_state(self) -> tuple[int | None, int | None]:
        if not self.node:
            return None, None
        return self.read("pwm1_enable"), self.read("pwm1")

    def _write_text(self, path: Path, value: str) -> tuple[int, str]:
        if os.geteuid() == 0:
            try:
                path.write_text(value)
                return 0, "ok"
            except OSError as e:
                return -1, str(e)

        if not self._sudo:
            return -1, "sudo not found"
        if not FAN_HELPER.exists():
            return -1, f"helper missing: {FAN_HELPER}"

        cmd = [
            self._sudo,
            "-n",
            str(FAN_HELPER),
            path.name,
            value,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            msg = (r.stdout + r.stderr).strip()
            return r.returncode, msg
        except (subprocess.SubprocessError, OSError) as e:
            return -1, str(e)

    def set_auto(self) -> tuple[int, str]:
        if not self.node:
            return -1, "fan hwmon not found"
        return self._write_text(self.node / "pwm1_enable", "2")

    def set_manual(self, pwm: int) -> tuple[int, str]:
        if not self.node:
            return -1, "fan hwmon not found"
        rc, msg = self._write_text(self.node / "pwm1_enable", "1")
        if rc != 0:
            return rc, msg
        return self._write_text(self.node / "pwm1", str(max(FAN_PWM_MIN, min(FAN_PWM_MAX, int(pwm)))))

    def set_percent(self, percent: int) -> tuple[int, str]:
        return self.set_manual(pct_to_pwm(percent))
