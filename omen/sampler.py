"""hwmon / psutil / nvidia-smi 采样层。

无 Qt / matplotlib 依赖,可独立测试。
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import psutil


HISTORY_SECONDS = 120
SAMPLE_INTERVAL_MS = 1000
HWMON_ROOT = Path("/sys/class/hwmon")
FAN_PWM_MAX = 255
FAN_PWM_MIN = 0


def _hwmon_by_name() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for entry in HWMON_ROOT.iterdir():
        try:
            name = (entry / "name").read_text().strip()
        except OSError:
            continue
        out.setdefault(name, entry)
    return out


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _read_temps_from(node: Path) -> list[tuple[str, float]]:
    temps: list[tuple[str, float]] = []
    for f in sorted(node.glob("temp*_input")):
        v = _read_int(f)
        if v is None:
            continue
        label_file = f.with_name(f.name.replace("_input", "_label"))
        label = label_file.read_text().strip() if label_file.exists() else f.stem
        temps.append((label, v / 1000.0))
    return temps


def pct_to_pwm(percent: int) -> int:
    return max(FAN_PWM_MIN, min(FAN_PWM_MAX, int(round(percent / 100.0 * FAN_PWM_MAX))))


def pwm_to_pct(pwm: int) -> int:
    return max(0, min(100, int(round(pwm / FAN_PWM_MAX * 100.0))))


@dataclass
class Sample:
    ts: float
    cpu_pkg: float | None = None
    cpu_cores: list[float] = field(default_factory=list)
    cpu_util_total: float = 0.0
    cpu_util_per: list[float] = field(default_factory=list)
    cpu_freq_mhz: float | None = None
    mem_used_gb: float = 0.0
    mem_total_gb: float = 0.0
    gpu_temp: float | None = None
    gpu_util: float | None = None
    gpu_mem_used: float | None = None
    gpu_mem_total: float | None = None
    gpu_power: float | None = None
    nvme_temps: list[tuple[str, float]] = field(default_factory=list)
    fan_rpm: list[int] = field(default_factory=list)
    fan_pwm: int | None = None
    fan_enable: int | None = None
    fan_hwmon: str | None = None
    top_processes: list[tuple[int, str, float, float]] = field(default_factory=list)
    wifi_temp: float | None = None


class Sampler:
    """缓存 hwmon 路径,定期采样所有指标。"""

    def __init__(self) -> None:
        self._hwmon = _hwmon_by_name()
        self._nvme_nodes = []
        for entry in HWMON_ROOT.iterdir():
            try:
                if (entry / "name").read_text().strip() == "nvme":
                    self._nvme_nodes.append(entry)
            except OSError:
                pass
        psutil.cpu_percent(percpu=True)
        self._has_nvidia_smi = shutil.which("nvidia-smi") is not None

    def sample(self) -> Sample:
        s = Sample(ts=time.time())

        core_node = self._hwmon.get("coretemp")
        if core_node:
            temps = _read_temps_from(core_node)
            for label, v in temps:
                if label.startswith("Package"):
                    s.cpu_pkg = v
                else:
                    s.cpu_cores.append(v)

        s.cpu_util_per = psutil.cpu_percent(percpu=True)
        s.cpu_util_total = sum(s.cpu_util_per) / max(len(s.cpu_util_per), 1)
        try:
            freq = psutil.cpu_freq()
            if freq and freq.current:
                cur = freq.current
                s.cpu_freq_mhz = cur * 1000 if cur < 100 else cur
        except Exception:
            pass

        mem = psutil.virtual_memory()
        s.mem_used_gb = mem.used / (1024 ** 3)
        s.mem_total_gb = mem.total / (1024 ** 3)

        if self._has_nvidia_smi:
            try:
                out = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True, text=True, timeout=2,
                )
                if out.returncode == 0 and out.stdout.strip():
                    parts = [p.strip() for p in out.stdout.strip().splitlines()[0].split(",")]
                    def _f(x: str) -> float | None:
                        try:
                            return float(x)
                        except ValueError:
                            return None
                    s.gpu_temp = _f(parts[0])
                    s.gpu_util = _f(parts[1])
                    s.gpu_mem_used = _f(parts[2])
                    s.gpu_mem_total = _f(parts[3])
                    s.gpu_power = _f(parts[4])
            except (subprocess.SubprocessError, OSError):
                pass

        for node in self._nvme_nodes:
            for label, v in _read_temps_from(node):
                dev = node.resolve().parent.name
                s.nvme_temps.append((f"{dev}/{label}", v))

        hp_node = self._hwmon.get("hp")
        if hp_node:
            for f in sorted(hp_node.glob("fan*_input")):
                v = _read_int(f)
                if v is not None:
                    s.fan_rpm.append(v)

        wifi_node = self._hwmon.get("iwlwifi_1")
        if wifi_node:
            temps = _read_temps_from(wifi_node)
            if temps:
                s.wifi_temp = temps[0][1]

        fan_node = self._hwmon.get("hp")
        if fan_node:
            s.fan_hwmon = str(fan_node)
            s.fan_enable = _read_int(fan_node / "pwm1_enable")
            s.fan_pwm = _read_int(fan_node / "pwm1")

        procs: list[tuple[int, str, float, float]] = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = proc.info
                pid = int(info.get("pid") or 0)
                name = str(info.get("name") or f"pid-{pid}")
                cpu = float(info.get("cpu_percent") or 0.0)
                mem = float(info.get("memory_percent") or 0.0)
                procs.append((pid, name, cpu, mem))
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue
        procs.sort(key=lambda x: (x[2], x[3]), reverse=True)
        s.top_processes = procs[:5]

        return s
