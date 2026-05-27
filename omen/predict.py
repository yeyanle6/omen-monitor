"""风扇 PWM 决策:温度 → 基线 PWM(走用户曲线) + 多种加成项。

basal_pwm(temp, curve) 在 curve 上做线性插值给出基础 PWM,模式加成在 predict_pwm 里:
- 自动:不通过这里走风扇控制(调用方应当用 hp-wmi 自动模式)
- 手动:由 GUI 直接写 floor,这里不参与
- 温度曲线:基线 + 中等 CPU/GPU/slope 加成
- 预测控制:基线 + 重 CPU/GPU/proc/slope 加成
"""

from __future__ import annotations

from .curve import DEFAULT_CURVE, FanCurve, interpolate
from .sampler import Sample


def basal_pwm(temp: float, curve: FanCurve | None = None) -> int:
    return interpolate(curve if curve is not None else DEFAULT_CURVE, temp)


def current_temp(s: Sample) -> float:
    temps = [
        v
        for v in (
            s.cpu_pkg,
            s.gpu_temp,
            max((t for _, t in s.nvme_temps), default=None),
        )
        if v is not None
    ]
    return max(temps) if temps else 0.0


def predict_pwm(
    s: Sample,
    mode: str,
    last_temp: float | None,
    last_ts: float | None,
    floor: int,
    curve: FanCurve | None = None,
) -> tuple[int, str]:
    """计算推荐 PWM% 与诊断字符串。纯函数。"""
    temp = current_temp(s)
    now = s.ts
    slope = 0.0
    if last_temp is not None and last_ts is not None:
        dt = max(now - last_ts, 1.0)
        slope = (temp - last_temp) / dt

    cpu_util = s.cpu_util_total
    gpu_util = s.gpu_util or 0.0
    proc_cpu = sum(cpu for _, _, cpu, _ in s.top_processes[:3])
    proc_mem = sum(mem for _, _, _, mem in s.top_processes[:3])
    proc_peak = max((cpu for _, _, cpu, _ in s.top_processes[:3]), default=0.0)
    proc_count = sum(1 for _, _, cpu, _ in s.top_processes[:5] if cpu >= 8.0)

    pwm = basal_pwm(temp, curve)

    if mode == "predict":
        pwm += int(round(cpu_util / 10))
        pwm += int(round(gpu_util / 14))
        pwm += int(round(proc_cpu / 18))
        pwm += int(round(proc_peak / 3))
        pwm += 2 * max(proc_count - 1, 0)
        pwm += 6 if proc_mem > 25 else 0
        pwm += 8 if slope > 2.0 else 0
        pwm += 5 if slope > 1.0 else 0
        pwm += 4 if temp >= 80 else 0
        pwm += 3 if temp >= 85 else 0
    elif mode == "curve":
        pwm += int(round(cpu_util / 14))
        pwm += int(round(gpu_util / 18))
        pwm += 4 if slope > 1.2 else 0
        pwm += 5 if temp >= 82 else 0

    pwm = max(pwm, floor)
    pwm = max(0, min(100, pwm))

    parts = [
        f"T={temp:.1f}°C",
        f"dT={slope:+.2f}°C/s",
        f"CPU={cpu_util:.0f}%",
        f"GPU={gpu_util:.0f}%",
        f"PROC={proc_cpu:.0f}%/{proc_mem:.0f}%",
    ]
    return pwm, " · ".join(parts)
