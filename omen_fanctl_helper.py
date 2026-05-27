#!/usr/bin/env python3
"""Minimal root helper for HP OMEN fan control.

Invoked via:
  omen-fanctl pwm1_enable 1
  omen-fanctl pwm1 128
"""

from __future__ import annotations

import sys
from pathlib import Path


HWMON_ROOT = Path("/sys/class/hwmon")
ALLOWED = {"pwm1_enable", "pwm1"}


def find_hp_node() -> Path | None:
    for entry in HWMON_ROOT.iterdir():
        try:
            if (entry / "name").read_text().strip() == "hp" and (entry / "pwm1").exists():
                return entry
        except OSError:
            continue
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: omen-fanctl pwm1_enable|pwm1 VALUE", file=sys.stderr)
        return 2

    filename = argv[1]
    value = argv[2]
    if filename not in ALLOWED:
        print(f"unsupported file: {filename}", file=sys.stderr)
        return 2

    if filename == "pwm1_enable" and value not in {"1", "2"}:
        print("pwm1_enable must be 1 or 2", file=sys.stderr)
        return 2

    if filename == "pwm1":
        try:
            pwm = int(value)
        except ValueError:
            print("pwm1 must be an integer", file=sys.stderr)
            return 2
        if not 0 <= pwm <= 255:
            print("pwm1 must be within 0..255", file=sys.stderr)
            return 2

    node = find_hp_node()
    if node is None:
        print("hp-wmi hwmon node not found", file=sys.stderr)
        return 1

    target = node / filename
    try:
        target.write_text(value)
    except OSError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
