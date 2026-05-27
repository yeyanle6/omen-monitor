#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export QT_OPENGL=software
export LIBGL_ALWAYS_SOFTWARE=1
export MPLCONFIGDIR="${XDG_CACHE_HOME:-$HOME/.cache}/omen-monitor/matplotlib"

mkdir -p "$MPLCONFIGDIR"
cd "$SCRIPT_DIR"
exec python3 omen_monitor.py
