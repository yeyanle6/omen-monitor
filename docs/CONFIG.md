# 运行时配置(用户态)

所有用户态配置文件都在 XDG 标准目录下,可以用任意文本编辑器手改,GUI 下次启动会读取。

| 文件 | 用途 | 改了之后 |
|---|---|---|
| `$XDG_CONFIG_HOME/omen-monitor/config.json` | 风扇模式 / 底线 / 窗口几何 / 语言 | GUI 启动时读;运行中修改也会被 GUI 覆盖 |
| `$XDG_CONFIG_HOME/omen-monitor/curve.json` | 用户自定义风扇曲线 | GUI 启动时读;曲线编辑器应用时覆盖 |
| `$XDG_STATE_HOME/omen-monitor/omen-monitor.lock` | 单实例锁(fcntl flock + 持锁 pid) | 不要手改 |
| `$XDG_CACHE_HOME/omen-monitor/matplotlib/` | matplotlib 字体缓存 | 可以随时删,会自动重建 |

> `XDG_CONFIG_HOME` 默认 `~/.config`,`XDG_STATE_HOME` 默认 `~/.local/state`,`XDG_CACHE_HOME` 默认 `~/.cache`。

---

## config.json

```json
{
  "fan_mode": "auto",
  "fan_floor_pct": 50,
  "window_geometry": [239, 121, 1180, 760],
  "language": "zh",
  "schema_version": 2
}
```

| 字段 | 取值 | 说明 |
|---|---|---|
| `fan_mode` | `"auto"` / `"manual"` / `"curve"` / `"predict"` | 启动时恢复 |
| `fan_floor_pct` | 0-100 | 在曲线/预测模式下作为推荐 PWM 的下限 |
| `window_geometry` | `[x, y, w, h]` 或 `null` | 主窗口几何;`null` 用默认 |
| `language` | 任何 `omen/locales/<code>.json` 里出现的 `_lang_code` | 默认 `zh` |
| `schema_version` | `2` | 改 schema 时升版;旧版会自动迁移(`手动`→`manual` 等) |

任何字段无效或缺失都会回落到默认值,坏的 JSON 整个回落。

---

## curve.json

```json
{
  "version": 1,
  "curve": [
    [40.0, 18],
    [58.0, 26],
    [64.0, 34],
    [80.0, 74],
    [92.0, 100]
  ]
}
```

- `curve` 是一组 `[温度°C, PWM%]`,**温度必须升序**,至少 2 个节点。
- 读取时会自动 normalize(去重 + 排序 + clamp PWM 到 0-100)。
- 推荐用 GUI 的"曲线编辑器"改;手改 JSON 重启 GUI 后生效。

---

## omen-monitor.lock

- 二进制锁文件,**fcntl.LOCK_EX | LOCK_NB**。
- 进程异常退出时 OS 自动释放,**不会**留 stale 锁。
- 文件内容是当前持锁的 pid,排查"已在运行"提示时可读:`cat $XDG_STATE_HOME/omen-monitor/omen-monitor.lock`。

---

## 加一种语言

无需改任何 Python 代码:

1. 复制 `omen/locales/en.json` 为 `omen/locales/<code>.json`(`<code>` 比如 `ja`、`de`、`fr`)
2. 把 `_lang_code` 改成 `<code>`,`_lang_display` 改成该语言**自身**的写法(例如 `日本語`)
3. 翻译所有 key 的 value(保留 `{占位符}` 不动)
4. 重启 GUI → 语言菜单自动多一项

key 缺译会自动 fallback 到英文,再缺会显示 key 名本身,便于排查。

---

## 常见手改场景

```bash
# 切回默认曲线(删 curve.json 让 GUI 用 DEFAULT_CURVE)
rm ~/.config/omen-monitor/curve.json

# 重置所有用户配置(模式 / 几何 / 语言)
rm -rf ~/.config/omen-monitor/

# 清 matplotlib 缓存(字体重新构建)
rm -rf ~/.cache/omen-monitor/

# 手动切换语言而不进 GUI
python3 -c "
import json, os
p = os.path.expanduser('~/.config/omen-monitor/config.json')
d = json.load(open(p))
d['language'] = 'en'
json.dump(d, open(p, 'w'), indent=2)
"
```
