# OMEN Monitor

PyQt5 温控/占用监控 + 风扇控制面板,针对 HP OMEN 16-wf0(board ID **8BAB**)在 Ubuntu 22.04 + kernel 6.8 下定制。

## 功能

- **实时仪表**:CPU 封装/核温 · CPU 占用与频率 · GPU 温度/占用/功耗/显存 · 内存 · NVMe 最高温 · 风扇 RPM
- **历史曲线**:温度 / 占用,过去 120 秒
- **风扇控制四模式**:
  - **自动** — `pwm1_enable=2`,交还 EC
  - **手动** — 滑条直接写 PWM%
  - **温度曲线** — 按用户可编辑的 (温度, PWM%) 折线插值 + 中等加成项
  - **预测控制** — 同上 + 重 CPU/GPU/进程压力/温度斜率加成
- **可视化曲线编辑器** — 拖节点 / 双击加点 / 右键删点,JSON 持久化
- **配置持久化** — 模式 / 底线 / 窗口几何 / 语言,XDG 标准目录
- **多语言** — 默认中文 + English,加新语言只需在 `omen/locales/` 丢一个 JSON
- **系统托盘** — 风扇 symbolic 图标 + 状态摘要 + mini 控制(自动/手动/曲线/预测/快速 PWM)
- **单实例锁** — fcntl flock,第二次启动弹消息框退出
- **DKMS 持久驱动** — patched `hp-wmi.ko`,kernel 升级自动重建

## 系统要求

| 组件 | 版本 / 状态 |
|---|---|
| 机型 | HP OMEN 16-wf0xxx, board ID 8BAB, BIOS F.26+ |
| OS | **Ubuntu 22.04 LTS**(因 ROS Humble 锁定,不要升 24.04) |
| Kernel | 6.8.x HWE(`linux-hwe-6.8-headers-*` 必装) |
| Secure Boot | **关闭**(patched 模块未签名) |
| Python | 3.10+,`PyQt5` + `matplotlib` + `psutil` |
| NVIDIA | 595.x(可选,仅 GPU 仪表用) |

## 架构

```
┌──────────────────────────────────────────────────────────────────┐
│ omen_monitor.py            入口 (QApplication + 单实例锁)         │
│ omen/                                                            │
│  ├── sampler.py            hwmon + psutil + nvidia-smi 采样      │
│  ├── fan_backend.py        HpWmiFanBackend → /sys/class/hwmon    │
│  ├── predict.py            纯函数 PWM 决策(基于曲线 + 模式加成)   │
│  ├── curve.py              FanCurve 模型 + 插值 + JSON IO        │
│  ├── curve_widget.py       曲线编辑器 (QDialog + matplotlib)     │
│  ├── config.py             模式/底线/几何/语言 持久化             │
│  ├── i18n.py               JSON 翻译表 + 动态语言扫描             │
│  ├── tray.py               系统托盘(风扇图标 + mini 控制)         │
│  ├── gui.py                MainWindow + StatTile + FanPanel      │
│  ├── locales/{zh,en}.json  翻译数据                              │
│  └── assets/icon.svg       风扇 SVG 图标                         │
└──────────────────────────────────────────────────────────────────┘
                            ↓ sudo -n (NOPASSWD)
              /usr/local/sbin/omen-fanctl  (root helper)
                            ↓ write text
          /sys/class/hwmon/<hp>/pwm1, pwm1_enable
                            ↑ 暴露这些节点
                  patched hp-wmi.ko  (driver/, 走 DKMS)
```

## 快速开始

```bash
# 1. 装 patched 驱动 (DKMS,kernel 升级会自动重建)
sudo ./scripts/install_driver.sh

# 2. 装 root helper + sudo NOPASSWD + 桌面入口 + ELF launcher
sudo ./scripts/setup_helper.sh

# 3. 跑 GUI
./run_omen_monitor.sh                # 或者双击桌面 OMEN-Monitor / GNOME Activities 搜索

# 4. (可选) 开机自启
./scripts/install_autostart.sh
```

`setup_helper.sh --check` 复检现状,`--remove` 卸载。

## 配置 / 文档

| 文档 | 内容 |
|---|---|
| [docs/CONFIG.md](docs/CONFIG.md) | 用户态运行时配置(`~/.config/omen-monitor/*.json`),字段说明 + 加新语言 |
| [docs/SYSTEM.md](docs/SYSTEM.md) | 系统层配置(helper / sudoers / DKMS / systemd / Secure Boot / 改密码) |
| [driver/README.md](driver/README.md) | patched `hp-wmi.ko` 来源 + 构建 + 风险 |
| [driver/PATCH.md](driver/PATCH.md) | 3 处兼容补丁的源码 diff 说明 |

## 故障排查

| 现象 | 原因 / 修复 |
|---|---|
| 风扇控制面板灰色"未找到 hp-wmi 风扇节点" | patched `hp-wmi.ko` 没加载。`lsmod \| grep hp_wmi` 应来自 `/updates/`,不是 `platform/x86/hp/`。重跑 `install_driver.sh` 或 `modprobe -r hp_wmi && modprobe hp_wmi`。 |
| 写 PWM 报 "sudo: a password is required" | NOPASSWD 没生效。检查 `/etc/sudoers.d/omen-monitor` 存在且 mode 440。 |
| 写 PWM 报 "helper missing: /usr/local/sbin/omen-fanctl" | 没部署 helper。重做 `setup_helper.sh`。 |
| 顶栏托盘图标不见 | GNOME 上需要 `ubuntu-appindicators` 扩展(默认启用)。Wayland 会话若关了扩展看不到。 |
| GUI 起不来,报 `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` | 缺 X11/Wayland 桌面。`run_omen_monitor.sh` 已强制软件 OpenGL,但仍需要图形会话。 |
| `pwm1=` 写入与读回不一致 | 正常 — 内核驱动对 PWM 做了线性映射,读到的 RPM-反推值不等于刚写入的 raw PWM。以 `fan*_input` 为准。 |

## License

MIT。`driver/hp-wmi.c` 派生自 [omen-fan-control](https://github.com/dmidlb/omen-fan-control) (GPL-2.0),改动按其许可证条款。
