# SlimeNodes AutoCoin (btpp39)

SlimeNodes 自动刷币 + 自动续期脚本，使用 session cookie 认证。

## 功能

- 🪙 **自动刷币** — 每次运行 20 个广告，每个 +12 币，共 +240 币
- 🔄 **自动续期** — 剩余 <24h 时自动续期服务器
- 📊 **余额检测** — 从 dashboard 实时获取余额
- ⏰ **到期检测** — 通过 `/lastrenew` API 获取服务器剩余时间
- 📢 **TG 通知** — 刷币结果、余额、剩余时间、续期状态推送到 Telegram

## 运行机制

1. 使用 `connect.sid` session cookie 认证（无需 Discord OAuth）
2. 调用 `/lv/gen` → 解析 base64 `r` 参数 → 获取兑换 URL
3. 等待 16-20s 冷却 → 调用兑换 URL（Referer: linkvertise.com）→ +12 币
4. 重复 20 次，达到每日上限则停止
5. 检查 `/lastrenew?id=SERVER_ID` 获取到期时间
6. 剩余 <24h 时自动调用 `/renew?id=SERVER_ID` 续期

## GitHub Secrets 配置

| Secret | 说明 | 示例 |
|--------|------|------|
| `SLIME_SESSION` | `connect.sid` session cookie | `s%3A4qPg...` |
| `SERVER_ID` | 数字格式服务器 ID | `10106` |
| `TG_BOT_TOKEN` | Telegram Bot Token | `7935239797:AAH...` |
| `TG_CHAT_ID` | Telegram Chat ID | `644320820` |
| `VLINK` | sing-box 代理链接 | `vlk://...` |
| `RENEW_THRESHOLD` | 续期所需最低余额（默认 50） | `50` |
| `RENEW_HOURS` | 剩余多少小时触发续期（默认 24） | `24` |

> ⚠️ `SERVER_ID` 必须是**数字格式**（如 `10106`），不是 hex 格式（如 `5b0322ed`）

## Cron 定时

每天 2 次自动运行：
- `00:30 UTC` (北京时间 08:30)
- `12:30 UTC` (北京时间 20:30)

每日可获约 480 币（2 次 × 240 币）。

## TG 通知格式

```
🟢 SlimeNodes 刷币 2026-06-03 10:52 UTC
✅ 39btpp: +240币 | 余额15859
⏰ 剩余: 168小时 (7.0天)
🔄 续期: ⏭️ 暂不需要 (>24h)
💰 总计: +240币
```

## 文件结构

```
├── makecoins.py          # 主脚本（刷币 + 续期 + 通知）
├── link_to_sb.py         # VLINK → sing-box 配置转换
├── .github/workflows/
│   └── autocoin.yml      # GitHub Actions 工作流
└── README.md
```

## 注意事项

- Session cookie 会过期，失效后需从浏览器重新获取
- 续期消耗 50 币，确保余额充足
- 通过 sing-box 代理访问，需配置 `VLINK` secret
