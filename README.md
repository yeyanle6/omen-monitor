# OMEN Monitor

> 一个为 **HP OMEN 16-wf0** 定制的温控监视器 + 风扇控制面板
> A custom thermal monitor + fan control panel for **HP OMEN 16-wf0**

**[中文](#中文)** &nbsp;·&nbsp; **[English](#english)**

---

## 中文

PyQt5 GUI,实时显示 CPU/GPU/NVMe 温度与占用,自定义风扇曲线,带系统托盘和中英双语切换。

### ✨ 功能

- 📊 **实时仪表** — CPU/GPU 温度与占用、内存、NVMe、风扇 RPM
- 📈 **历史曲线** — 过去 120 秒的温度与占用
- 🌀 **风扇四模式** — 自动 / 手动 / 温度曲线 / 预测控制
- 🎚 **可视化曲线编辑** — 拖节点、双击加点、右键删点
- 💾 **配置持久化** — 模式、底线、窗口几何、语言全部记住
- 🌐 **多语言** — 中文 + English,加新语言只需丢一个 JSON
- 🔔 **系统托盘** — 风扇 symbolic 图标 + 状态摘要 + mini 控制
- 🔒 **单实例锁** — 双击不会启动两份
- ⚙️ **DKMS 驱动** — patched `hp-wmi.ko`,kernel 升级自动重建

### 🖥 系统要求

| 组件 | 要求 |
|---|---|
| 机型 | HP OMEN 16-wf0xxx · **board ID 8BAB** · BIOS F.26+ |
| OS | Ubuntu 22.04 LTS |
| Kernel | 6.8.x HWE (`linux-hwe-6.8-headers-*`) |
| Secure Boot | **关闭**(patched 模块未签名) |
| Python | 3.10+ · `PyQt5` · `matplotlib` · `psutil` |
| NVIDIA | 595.x(可选,仅 GPU 仪表) |

### 🚀 快速开始

```bash
# 1. 装系统依赖
sudo apt install -y python3 python3-pyqt5 python3-matplotlib python3-psutil \
                    dkms linux-headers-$(uname -r) build-essential

# 2. clone
git clone https://github.com/yeyanle6/omen-monitor.git
cd omen-monitor

# 3. 装驱动 + helper + 桌面入口
sudo ./scripts/install_driver.sh
sudo ./scripts/setup_helper.sh

# 4. 跑
./run_omen_monitor.sh        # 或双击桌面 OMEN-Monitor / GNOME Activities 搜索

# 可选:开机自启
./scripts/install_autostart.sh
```

`setup_helper.sh --check` 复检,`--remove` 卸载。

### 📚 文档

| 文档 | 内容 |
|---|---|
| [docs/CONFIG.md](docs/CONFIG.md) | 运行时配置(`~/.config/omen-monitor/*.json`),字段说明 + 加新语言 |
| [docs/SYSTEM.md](docs/SYSTEM.md) | 系统层(helper / sudoers / DKMS / systemd / 改密码) |
| [driver/README.md](driver/README.md) | patched `hp-wmi.ko` 来源 + 构建 + 风险 |
| [driver/PATCH.md](driver/PATCH.md) | 3 处兼容补丁 diff 说明 |

### 🛠 故障排查

| 现象 | 修复 |
|---|---|
| 风扇控制面板灰色 | `hp-wmi.ko` 没加载 → 重跑 `install_driver.sh` |
| 写 PWM 报 "password required" | NOPASSWD 没生效 → 检查 `/etc/sudoers.d/omen-monitor` |
| 顶栏图标不见 | GNOME 需启用 `ubuntu-appindicators` 扩展 |
| PWM 写入与读回不一致 | 正常,以 `fan*_input` RPM 读数为准 |

---

## English

A PyQt5 GUI showing live CPU/GPU/NVMe temperatures and usage, with custom fan curves, system tray, and Chinese/English language toggle.

### ✨ Features

- 📊 **Live tiles** — CPU/GPU temp & util, memory, NVMe, fan RPM
- 📈 **History charts** — last 120 s of temperature and utilization
- 🌀 **Four fan modes** — Auto / Manual / Temp Curve / Predictive
- 🎚 **Visual curve editor** — drag nodes, double-click to add, right-click to delete
- 💾 **Persistent config** — mode, floor, window geometry, language all remembered
- 🌐 **i18n** — Chinese + English, add a new language by dropping a JSON file
- 🔔 **System tray** — symbolic fan icon + status summary + mini controls
- 🔒 **Single-instance lock** — double-clicking won't launch two copies
- ⚙️ **DKMS driver** — patched `hp-wmi.ko`, rebuilt automatically on kernel upgrade

### 🖥 Requirements

| Component | Required |
|---|---|
| Hardware | HP OMEN 16-wf0xxx · **board ID 8BAB** · BIOS F.26+ |
| OS | Ubuntu 22.04 LTS |
| Kernel | 6.8.x HWE (`linux-hwe-6.8-headers-*`) |
| Secure Boot | **disabled** (patched module is unsigned) |
| Python | 3.10+ · `PyQt5` · `matplotlib` · `psutil` |
| NVIDIA | 595.x (optional, only for GPU tiles) |

### 🚀 Quick Start

```bash
# 1. Install system dependencies
sudo apt install -y python3 python3-pyqt5 python3-matplotlib python3-psutil \
                    dkms linux-headers-$(uname -r) build-essential

# 2. Clone
git clone https://github.com/yeyanle6/omen-monitor.git
cd omen-monitor

# 3. Install driver + helper + desktop entry
sudo ./scripts/install_driver.sh
sudo ./scripts/setup_helper.sh

# 4. Run
./run_omen_monitor.sh        # or double-click desktop OMEN-Monitor / search in GNOME Activities

# Optional: autostart on login
./scripts/install_autostart.sh
```

Run `setup_helper.sh --check` to verify, `--remove` to uninstall.

### 📚 Documentation

| Doc | Topic |
|---|---|
| [docs/CONFIG.md](docs/CONFIG.md) | Runtime config (`~/.config/omen-monitor/*.json`), fields, adding a language |
| [docs/SYSTEM.md](docs/SYSTEM.md) | System layer (helper / sudoers / DKMS / systemd / changing password) |
| [driver/README.md](driver/README.md) | Source of patched `hp-wmi.ko`, build, risks |
| [driver/PATCH.md](driver/PATCH.md) | The three compatibility patches explained |

### 🛠 Troubleshooting

| Symptom | Fix |
|---|---|
| Fan control panel greyed out | `hp-wmi.ko` not loaded → re-run `install_driver.sh` |
| "password required" when writing PWM | NOPASSWD didn't take effect → check `/etc/sudoers.d/omen-monitor` |
| Tray icon missing | GNOME requires `ubuntu-appindicators` extension |
| PWM write/read mismatch | Normal — kernel does a linear remap; trust `fan*_input` RPM |
