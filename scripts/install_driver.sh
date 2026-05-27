#!/usr/bin/env bash
# Install patched hp-wmi as a DKMS module so it survives kernel upgrades.
#
# Usage:  sudo ./scripts/install_driver.sh
#
# Idempotent: re-running the script rebuilds against the current kernel.

set -euo pipefail

PKG_NAME="hp-wmi-omen"
PKG_VERSION="1.0"
SRC_DIR="/usr/src/${PKG_NAME}-${PKG_VERSION}"
KVER="$(uname -r)"
STOCK_KO="/lib/modules/${KVER}/kernel/drivers/platform/x86/hp/hp-wmi.ko"
BACKUP_DIR="/var/backups"
BACKUP_KO="${BACKUP_DIR}/hp-wmi.ko.stock.${KVER}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRIVER_DIR="${REPO_ROOT}/driver"

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m!! %s\033[0m\n" "$*"; }
die()  { printf "\033[1;31mxx %s\033[0m\n" "$*" >&2; exit 1; }

[ "$EUID" -eq 0 ] || die "需要 root 权限。请用 sudo 运行。"

step "0/7 前置检查"
command -v dkms >/dev/null || die "未找到 dkms。先 apt install dkms。"
[ -d "/lib/modules/${KVER}/build" ] || die "未找到 kernel headers: /lib/modules/${KVER}/build。先 apt install linux-headers-${KVER} (或对应 HWE 包)。"
[ -f "${DRIVER_DIR}/hp-wmi.c" ] || die "未找到 ${DRIVER_DIR}/hp-wmi.c。脚本须在 repo 根的 scripts/ 里运行。"
[ -f "${DRIVER_DIR}/dkms.conf" ] || die "未找到 ${DRIVER_DIR}/dkms.conf。"

step "1/7 备份原版 hp-wmi.ko (仅当备份不存在)"
mkdir -p "${BACKUP_DIR}"
if [ -e "${BACKUP_KO}" ]; then
    warn "已存在备份: ${BACKUP_KO} — 不覆盖"
elif [ -e "${STOCK_KO}" ] || [ -e "${STOCK_KO}.zst" ] || [ -e "${STOCK_KO}.xz" ]; then
    SRC_FOUND=""
    for ext in "" ".zst" ".xz"; do
        if [ -e "${STOCK_KO}${ext}" ]; then
            SRC_FOUND="${STOCK_KO}${ext}"
            break
        fi
    done
    cp -a "${SRC_FOUND}" "${BACKUP_KO}$(basename "${SRC_FOUND}" "${STOCK_KO}")"
    echo "已备份: ${SRC_FOUND} → ${BACKUP_KO}$(basename "${SRC_FOUND}" "${STOCK_KO}")"
else
    warn "找不到 stock hp-wmi.ko (kernel 可能没编译它)。继续。"
fi

step "2/7 同步源码到 ${SRC_DIR}"
rm -rf "${SRC_DIR}"
mkdir -p "${SRC_DIR}"
cp "${DRIVER_DIR}/hp-wmi.c" "${DRIVER_DIR}/hp-wmi.c.orig" "${DRIVER_DIR}/Makefile" "${DRIVER_DIR}/dkms.conf" "${SRC_DIR}/"
ls -la "${SRC_DIR}/"

step "3/7 dkms remove 旧版本 (如果存在)"
if dkms status "${PKG_NAME}/${PKG_VERSION}" 2>/dev/null | grep -q .; then
    dkms remove -m "${PKG_NAME}" -v "${PKG_VERSION}" --all || warn "dkms remove 报错但继续"
fi

step "4/7 dkms add"
dkms add -m "${PKG_NAME}" -v "${PKG_VERSION}"

step "5/7 dkms build (kernel ${KVER})"
dkms build -m "${PKG_NAME}" -v "${PKG_VERSION}" -k "${KVER}"

step "6/7 dkms install"
dkms install -m "${PKG_NAME}" -v "${PKG_VERSION}" -k "${KVER}" --force
depmod -a "${KVER}"

step "7/7 重新加载 hp_wmi 并验证"
if lsmod | grep -q '^hp_wmi'; then
    rmmod hp_wmi || warn "rmmod hp_wmi 失败 (可能被持有)"
fi
modprobe hp_wmi
# hwmon 节点在 udev 事件链上注册,modprobe 返回 ≠ 节点已可见。
# 轮询最多 ~5s,期间 udev settle 一次以加速。
udevadm settle --timeout=3 || true
for i in 1 2 3 4 5; do
    if ls /sys/class/hwmon/hwmon*/pwm1 >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
if ls /sys/class/hwmon/hwmon*/pwm1 >/dev/null 2>&1; then
    HWMON=$(grep -l '^hp$' /sys/class/hwmon/hwmon*/name 2>/dev/null | head -1 | xargs dirname)
    echo "✓ pwm1 节点已就绪: ${HWMON}/pwm1"
    echo "  enable=$(cat ${HWMON}/pwm1_enable)  pwm=$(cat ${HWMON}/pwm1)"
else
    die "安装成功但 ~5s 内未发现 pwm1 节点。手动试: sudo rmmod hp_wmi && sudo modprobe hp_wmi; 仍无则看 dmesg | tail -30。"
fi

echo
echo "完成。重启后 hp-wmi.ko 由 DKMS 自动 rebuild for 新 kernel。"
echo "回滚: sudo $(dirname "${BASH_SOURCE[0]}")/uninstall_driver.sh"
