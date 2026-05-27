#!/usr/bin/env bash
# Install the systemd --user unit that auto-launches OMEN Monitor on login.
#
# Usage:  ./scripts/install_autostart.sh
#         (do NOT run with sudo — this manages the *user* unit)

set -euo pipefail

UNIT_NAME="omen-monitor.service"
TARGET_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${REPO_ROOT}/scripts/templates/${UNIT_NAME}.in"

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
die()  { printf "\033[1;31mxx %s\033[0m\n" "$*" >&2; exit 1; }

[ "$EUID" -ne 0 ] || die "不要用 sudo 跑;这管理的是 user systemd,需要 \$USER 的会话。"
[ -f "${TEMPLATE}" ] || die "未找到模板 ${TEMPLATE}"

step "1/3 渲染模板到 ${TARGET_DIR}/${UNIT_NAME}"
mkdir -p "${TARGET_DIR}"
sed "s|@REPO_DIR@|${REPO_ROOT}|g" "${TEMPLATE}" > "${TARGET_DIR}/${UNIT_NAME}"
echo "已写入:"
grep -E '^ExecStart' "${TARGET_DIR}/${UNIT_NAME}"

step "2/3 reload + enable + start"
systemctl --user daemon-reload
systemctl --user enable --now "${UNIT_NAME}"

step "3/3 状态"
systemctl --user --no-pager status "${UNIT_NAME}" | head -20

cat <<'EOF'

完成。下次登录会自动启动 OMEN Monitor。
关闭自启: systemctl --user disable --now omen-monitor.service
卸载 unit: rm ~/.config/systemd/user/omen-monitor.service && systemctl --user daemon-reload
EOF
