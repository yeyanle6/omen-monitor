# 系统层配置 + 权限 / 密码

OMEN Monitor 触及若干系统级文件:风扇控制走 sudo helper、自定义内核模块走 DKMS、开机自启走 systemd user 单元。本文档把所有"在 / 下面的东西"列清楚 + 修改方法。

## 一键部署 / 检查 / 移除

```bash
sudo ./scripts/setup_helper.sh           # 装 helper + sudoers NOPASSWD + 桌面入口
./scripts/setup_helper.sh --check        # 仅检查,不改
sudo ./scripts/setup_helper.sh --remove  # 全部卸载
```

下面是每一项的细节,需要绕过 setup_helper 手改时参考。

---

## 1. Root helper:`/usr/local/sbin/omen-fanctl`

**来源**:`omen_fanctl_helper.py`(repo 根)
**作用**:GUI 通过 `sudo -n` 调它写 `pwm1` / `pwm1_enable`。GUI 自身不 root,降低权限暴露。
**安全策略**:helper 只接受两个文件名(`pwm1` / `pwm1_enable`),严格值校验(`pwm1_enable ∈ {1,2}`,`pwm1 ∈ [0, 255]`)。

```bash
# 手动安装/更新(等价于 setup_helper.sh 的步骤 1)
sudo install -m 755 -o root -g root omen_fanctl_helper.py /usr/local/sbin/omen-fanctl

# 检查
sudo ls -la /usr/local/sbin/omen-fanctl

# 卸载
sudo rm /usr/local/sbin/omen-fanctl
```

---

## 2. sudoers NOPASSWD:`/etc/sudoers.d/omen-monitor`

**作用**:让桌面用户在不输密码的前提下调用 helper。

**内容**:
```
# OMEN Monitor — 允许桌面用户在不输密码的前提下调用风扇 helper
<USER> ALL=(root) NOPASSWD: /usr/local/sbin/omen-fanctl
```

> `<USER>` 是你的登录用户名(GUI 跑在哪个用户下,这里就写哪个)。

**安全声明**:这个白名单**只**给一个 helper 程序免密,helper 又只能写 `pwm1*`,因此即便被恶意调用,最坏后果是风扇被设满 100% / 重启。**不要**用 `ALL` 替代 helper 路径,那样等于全 sudo 免密。

```bash
# 手动写入(等价于 setup_helper.sh 的步骤 2)
echo "$(whoami) ALL=(root) NOPASSWD: /usr/local/sbin/omen-fanctl" \
  | sudo tee /etc/sudoers.d/omen-monitor
sudo chmod 440 /etc/sudoers.d/omen-monitor
# 一定要 visudo 检查语法
sudo visudo -c -f /etc/sudoers.d/omen-monitor

# 检查 NOPASSWD 是否真的生效
sudo -n -l /usr/local/sbin/omen-fanctl

# 卸载
sudo rm /etc/sudoers.d/omen-monitor
```

**编辑这个文件务必用 visudo** — `sudo visudo -f /etc/sudoers.d/omen-monitor`,语法错误会让 sudo 整个失效。

---

## 3. Patched 内核模块:`hp-wmi.ko`

由 DKMS 安装/管理。文件位置:

| 路径 | 角色 |
|---|---|
| `/usr/src/hp-wmi-omen-1.0/` | DKMS 源码副本(driver/ 的内容) |
| `/var/lib/dkms/hp-wmi-omen/1.0/<KVER>/` | DKMS 构建产物 |
| `/lib/modules/<KVER>/updates/dkms/hp-wmi.ko` | 实际加载位置(覆盖 stock) |
| `/var/backups/hp-wmi.ko.stock.<KVER>` | 安装时备份的原版 ko |

```bash
# 安装 / 重装
sudo ./scripts/install_driver.sh

# 查状态
dkms status hp-wmi-omen
modinfo hp_wmi | grep filename     # 应在 /updates/dkms/

# 回滚到 stock
sudo ./scripts/uninstall_driver.sh
```

详情见 `driver/README.md` 和 `driver/PATCH.md`。

---

## 4. 桌面入口:`~/.local/share/applications/OMEN-Monitor.desktop`

由 `setup_helper.sh` 从模板 `scripts/templates/OMEN-Monitor.desktop.in` 渲染(把 `@REPO_DIR@` 换成 repo 实际路径)。

```bash
# 手改 Exec/Icon 后:
update-desktop-database ~/.local/share/applications/

# 也可以把 .desktop 拷一份到 ~/Desktop 双击启动
cp ~/.local/share/applications/OMEN-Monitor.desktop ~/Desktop/
chmod +x ~/Desktop/OMEN-Monitor.desktop
# GNOME 上首次双击会问"是否信任",右键 → 允许启动
```

---

## 5. 开机自启:`~/.config/systemd/user/omen-monitor.service`

由 `scripts/install_autostart.sh` 从 `scripts/templates/omen-monitor.service.in` 渲染。

```bash
# 启用
./scripts/install_autostart.sh

# 关闭自启(保留 unit 文件,只 disable)
systemctl --user disable --now omen-monitor.service

# 彻底卸载
systemctl --user disable --now omen-monitor.service
rm ~/.config/systemd/user/omen-monitor.service
systemctl --user daemon-reload
```

---

## 6. 修改系统密码

OMEN Monitor 不存储任何密码。如需改 Linux 登录密码:

```bash
passwd                  # 改当前用户密码 (交互输入旧密码 + 两次新密码)
sudo passwd <username>  # 改别人的(root 不需要旧密码)
```

提醒:`/etc/sudoers.d/omen-monitor` 是 **NOPASSWD only for helper**;改密码**不会**影响 helper 调用(因为根本不查密码)。但如果你以前为了快设了 `<USER> ALL=(ALL) NOPASSWD: ALL`(全 sudo 免密),那是另外的安全风险,**强烈建议**单独清掉:

```bash
sudo grep -r 'NOPASSWD: ALL' /etc/sudoers /etc/sudoers.d/
# 如果发现,sudo visudo 删掉该行,保留 omen-monitor 这个最小白名单
```

---

## 7. BIOS Secure Boot

Patched `hp-wmi.ko` **未签名**,需要 BIOS 关闭 Secure Boot 才能加载:

1. 重启时按 `F10` 进 BIOS
2. Security → Secure Boot Configuration → Secure Boot = Disabled
3. 保存退出

如果你坚持开 Secure Boot,需要自签模块 + MOK enrollment,不在本项目范围。

---

## 8. 全套部署 / 还原对照表

| 想做的事 | 命令 |
|---|---|
| 全新机器一次性装好 | `sudo ./scripts/install_driver.sh && sudo ./scripts/setup_helper.sh && ./scripts/install_autostart.sh` |
| 仅 GUI 试用(不动驱动) | `./run_omen_monitor.sh` |
| 检查当前装了哪些 | `./scripts/setup_helper.sh --check && dkms status hp-wmi-omen && systemctl --user status omen-monitor` |
| 完全卸载 | `systemctl --user disable --now omen-monitor.service && rm ~/.config/systemd/user/omen-monitor.service && sudo ./scripts/uninstall_driver.sh && sudo ./scripts/setup_helper.sh --remove` |
