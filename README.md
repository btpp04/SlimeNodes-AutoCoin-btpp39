# SlimeNodes-AutoCoin 🔵

Automated coin earning for SlimeNodes (dash.slimenodes.com) via GitHub Actions.

## How it works

1. Discord OAuth API → session cookie
2. Generate linkvertise link → decode r parameter → get redeem URL  
3. Wait 15+ seconds (server-side timer bypass)
4. Redeem with Referer header → +12 coins per ad
5. Repeat until daily limit

**No browser needed** - pure HTTP approach using curl.

## Setup

### 1. Get your Discord Token

Open Discord in browser → DevTools → Network → find any `discord.com/api` request → copy the `authorization` header value.

### 2. Set GitHub Secrets

| Secret | Description |
|--------|-------------|
| `SLIME_ACCOUNTS` | JSON array: `[{"token":"DISCORD_TOKEN","label":"name"}]` |
| `TG_BOT_TOKEN` | Telegram bot token for notifications |
| `TG_CHAT_ID` | Telegram chat ID |

### 3. Enable Workflow

The workflow runs twice daily at 00:30 and 12:30 UTC. Use `workflow_dispatch` for manual trigger.

## Multiple Accounts

```json
[
  {"token": "TOKEN_1", "label": "account1"},
  {"token": "TOKEN_2", "label": "account2"}
]
```

## Notes

- Each ad earns **12 coins**
- Server validates a minimum ~12s delay between generate and redeem
- Script adds 16-20s random delay to safely bypass this check
- Daily limit appears to be ~15 ads per account
