#!/usr/bin/env bash
# Roll back the patched hp-wmi DKMS module and restore the stock one.
#
# Usage:  sudo ./scripts/uninstall_driver.sh

set -euo pipefail

PKG_NAME="hp-wmi-omen"
PKG_VERSION="1.0"
SRC_DIR="/usr/src/${PKG_NAME}-${PKG_VERSION}"
KVER="$(uname -r)"
STOCK_KO_DIR="/lib/modules/${KVER}/kernel/drivers/platform/x86/hp"
BACKUP_DIR="/var/backups"

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m!! %s\033[0m\n" "$*"; }
die()  { printf "\033[1;31mxx %s\033[0m\n" "$*" >&2; exit 1; }

[ "$EUID" -eq 0 ] || die "需要 root 权限。请用 sudo 运行。"

step "1/4 dkms remove (所有 kernel)"
if dkms status "${PKG_NAME}/${PKG_VERSION}" 2>/dev/null | grep -q .; then
    dkms remove -m "${PKG_NAME}" -v "${PKG_VERSION}" --all || warn "dkms remove 报错但继续"
else
    warn "${PKG_NAME}/${PKG_VERSION} 未在 DKMS 树中"
fi

step "2/4 清 /usr/src/${PKG_NAME}-${PKG_VERSION}"
rm -rf "${SRC_DIR}"

step "3/4 恢复 stock hp-wmi.ko (若有备份)"
restored=""
for ext in "" ".zst" ".xz"; do
    BACKUP_KO="${BACKUP_DIR}/hp-wmi.ko.stock.${KVER}${ext}"
    if [ -e "${BACKUP_KO}" ]; then
        mkdir -p "${STOCK_KO_DIR}"
        cp -a "${BACKUP_KO}" "${STOCK_KO_DIR}/hp-wmi.ko${ext}"
        restored="${STOCK_KO_DIR}/hp-wmi.ko${ext}"
        break
    fi
done
if [ -n "${restored}" ]; then
    echo "已恢复: ${restored}"
else
    warn "未找到 ${BACKUP_DIR}/hp-wmi.ko.stock.${KVER}* — 跳过恢复"
fi
depmod -a "${KVER}"

step "4/4 重新加载 hp_wmi 验证回到 stock"
if lsmod | grep -q '^hp_wmi'; then
    rmmod hp_wmi || warn "rmmod hp_wmi 失败 (可能被持有)"
fi
modprobe hp_wmi
sleep 1
KO_PATH=$(modinfo hp_wmi 2>/dev/null | awk '/^filename:/{print $2}')
echo "当前 hp_wmi 来自: ${KO_PATH}"
if echo "${KO_PATH}" | grep -q '/updates/'; then
    die "回滚未生效:仍在加载 DKMS 版本。手动 rmmod 后 modprobe。"
fi
echo "✓ 已回到 stock hp_wmi。"
