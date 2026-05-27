#!/usr/bin/env bash
# 一键部署 OMEN Monitor 的用户态依赖:
#   1. /usr/local/sbin/omen-fanctl                       (root helper)
#   2. /etc/sudoers.d/omen-monitor                       (NOPASSWD 给 helper)
#   3. ~/.local/share/applications/OMEN-Monitor.desktop  (GNOME Activities 入口)
#   4. ~/Desktop/OMEN-Monitor                            (ELF launcher,双击直接启动)
#
# Usage:  ./scripts/setup_helper.sh           # 安装并检查
#         ./scripts/setup_helper.sh --check   # 仅检查现状,不修改
#         ./scripts/setup_helper.sh --remove  # 卸载

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER_SRC="${REPO_ROOT}/omen_fanctl_helper.py"
HELPER_DST="/usr/local/sbin/omen-fanctl"
SUDOERS_FILE="/etc/sudoers.d/omen-monitor"
DESKTOP_TEMPLATE="${REPO_ROOT}/scripts/templates/OMEN-Monitor.desktop.in"
DESKTOP_DST="${XDG_DATA_HOME:-$HOME/.local/share}/applications/OMEN-Monitor.desktop"
LAUNCHER_SRC="${REPO_ROOT}/scripts/templates/launcher.c"
LAUNCHER_DST="${HOME}/Desktop/OMEN-Monitor"
RUN_SCRIPT="${REPO_ROOT}/run_omen_monitor.sh"

USER_NAME="${SUDO_USER:-$USER}"
USER_HOME="$(getent passwd "${USER_NAME}" | cut -d: -f6)"
if [ -n "${USER_HOME}" ] && [ "${USER_HOME}" != "${HOME}" ]; then
    LAUNCHER_DST="${USER_HOME}/Desktop/OMEN-Monitor"
fi

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m!! %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
bad()  { printf "\033[1;31m✗\033[0m %s\n" "$*"; }

require_root() {
    if [ "$EUID" -ne 0 ]; then
        exec sudo -E "$0" "$@"
    fi
}

cmd_check() {
    step "检查 helper 安装状态"
    if [ -x "${HELPER_DST}" ]; then ok "${HELPER_DST}"; else bad "${HELPER_DST} 不存在"; fi
    if [ -f "${SUDOERS_FILE}" ]; then ok "${SUDOERS_FILE}"; else bad "${SUDOERS_FILE} 不存在"; fi
    if [ -f "${DESKTOP_DST}" ]; then ok "${DESKTOP_DST}"; else bad "${DESKTOP_DST} 不存在"; fi
    if [ -x "${LAUNCHER_DST}" ]; then
        if file "${LAUNCHER_DST}" 2>/dev/null | grep -q ELF; then
            ok "${LAUNCHER_DST} (ELF launcher)"
        else
            warn "${LAUNCHER_DST} 存在但不是 ELF"
        fi
    else
        bad "${LAUNCHER_DST} 不存在(双击桌面启动会缺)"
    fi
    # helper 内容一致性
    if [ -x "${HELPER_DST}" ] && [ -f "${HELPER_SRC}" ]; then
        if cmp -s "${HELPER_SRC}" "${HELPER_DST}"; then
            ok "helper 与 repo 副本一致"
        else
            warn "已部署 helper 与 repo 副本不同(可能 repo 更新后未重装)"
        fi
    fi
    # NOPASSWD 实际生效?
    if sudo -n -l "${HELPER_DST}" >/dev/null 2>&1; then
        ok "NOPASSWD 对 ${HELPER_DST} 已生效"
    else
        bad "NOPASSWD 未生效(检查 ${SUDOERS_FILE} 内容 + chmod 440)"
    fi
}

cmd_install() {
    require_root "$@"

    step "1/4 安装 helper → ${HELPER_DST}"
    [ -f "${HELPER_SRC}" ] || { bad "未找到 ${HELPER_SRC}"; exit 1; }
    install -m 755 -o root -g root "${HELPER_SRC}" "${HELPER_DST}"
    ok "已安装"

    step "2/4 写 sudoers NOPASSWD → ${SUDOERS_FILE}"
    cat > "${SUDOERS_FILE}.tmp" <<EOF
# OMEN Monitor — 允许桌面用户在不输密码的前提下调用风扇 helper
${USER_NAME} ALL=(root) NOPASSWD: ${HELPER_DST}
EOF
    # visudo 语法检查后再启用
    if visudo -c -f "${SUDOERS_FILE}.tmp" >/dev/null; then
        chmod 440 "${SUDOERS_FILE}.tmp"
        mv "${SUDOERS_FILE}.tmp" "${SUDOERS_FILE}"
        ok "已写入 (user=${USER_NAME})"
    else
        rm -f "${SUDOERS_FILE}.tmp"
        bad "visudo 语法检查失败,已回滚"
        exit 1
    fi

    step "3/5 安装桌面入口 → ${DESKTOP_DST}"
    sudo -u "${USER_NAME}" mkdir -p "$(dirname "${DESKTOP_DST}")"
    sudo -u "${USER_NAME}" sh -c "sed 's|@REPO_DIR@|${REPO_ROOT}|g' '${DESKTOP_TEMPLATE}' > '${DESKTOP_DST}'"
    sudo -u "${USER_NAME}" update-desktop-database "$(dirname "${DESKTOP_DST}")" 2>/dev/null || true
    ok "已安装(从 GNOME Activities 即可启动 OMEN Monitor)"

    step "4/5 编译桌面 ELF 启动器 → ${LAUNCHER_DST}"
    if command -v gcc >/dev/null; then
        sudo -u "${USER_NAME}" mkdir -p "$(dirname "${LAUNCHER_DST}")"
        sudo -u "${USER_NAME}" rm -f "${LAUNCHER_DST}" "${LAUNCHER_DST}.desktop"
        sudo -u "${USER_NAME}" gcc \
            -DSCRIPT_PATH="\"${RUN_SCRIPT}\"" \
            "${LAUNCHER_SRC}" -o "${LAUNCHER_DST}"
        sudo -u "${USER_NAME}" chmod 755 "${LAUNCHER_DST}"
        ok "ELF 已就位(双击可直接启动,无需 GNOME '允许启动')"
    else
        warn "未找到 gcc,跳过桌面 ELF。装 build-essential 后重跑可获得双击启动。"
    fi

    step "5/5 复检"
    sudo -u "${USER_NAME}" "$0" --check
}

cmd_remove() {
    require_root "$@"
    step "移除 ${HELPER_DST}"
    rm -f "${HELPER_DST}" && ok "已删" || warn "helper 不存在或删除失败"
    step "移除 ${SUDOERS_FILE}"
    rm -f "${SUDOERS_FILE}" && ok "已删" || warn "sudoers 文件不存在或删除失败"
    step "移除 ${DESKTOP_DST}"
    sudo -u "${USER_NAME}" rm -f "${DESKTOP_DST}" && ok "已删" || true
    step "移除 ${LAUNCHER_DST}"
    sudo -u "${USER_NAME}" rm -f "${LAUNCHER_DST}" && ok "已删" || true
}

case "${1:-install}" in
    install|"")   cmd_install ;;
    --check|-c)   cmd_check ;;
    --remove|-r)  cmd_remove ;;
    *)            echo "Usage: $0 [install|--check|--remove]"; exit 2 ;;
esac
