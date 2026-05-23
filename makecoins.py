#!/usr/bin/env python3
"""SlimeNodes AutoCoin - earn coins by watching ads."""
import os, sys, json, time, subprocess, re

log = lambda *a: print(*a, flush=True)

# ── proxy helpers ──────────────────────────────────────────────
PX = os.environ.get("SOCKS_PROXY") or os.environ.get("HTTP_PROXY") or ""
log(f"DEBUG: SOCKS_PROXY={os.environ.get('SOCKS_PROXY','<MISSING>')!r} PX={PX!r}")

def px():
    if not PX:
        return []
    p = PX.replace("socks5://", "socks5h://")
    return ["--proxy", p]

# ── curl helper ────────────────────────────────────────────────
def run_curl(args, timeout=30):
    base = ["curl", "-s", "--connect-timeout", "20", "--max-time", str(timeout)]
    cmd = base + px() + args
    log(f"  CMD: {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
        if r.stderr:
            log(f"  curl stderr: {r.stderr[:200]}")
        return r.stdout.strip()
    except Exception as e:
        log(f"  curl error: {e}")
        return ""

# ── Discord OAuth ──────────────────────────────────────────────
CID = "1267847469501513799"
SCO = "identify email guilds.join"
BASE = "https://dash.slimenodes.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"

def discord_oauth(tok):
    log("Discord OAuth...")
    log(f"  tok len={len(tok)} prefix={tok[:15]}...")
    from urllib.parse import quote
    url = (
        f"https://discord.com/api/v9/oauth2/authorize"
        f"?client_id={CID}&scope={quote(SCO, safe='')}"
        f"&response_type=code"
        f"&redirect_uri={quote(f'{BASE}/callback', safe='')}"
    )
    body = json.dumps({"authorize": True})
    out = run_curl([
        "-X", "POST",
        "-H", f"User-Agent: {UA}",
        "-H", f"Authorization: {tok}",
        "-H", "Content-Type: application/json",
        "-d", body,
        url,
    ])
    try:
        d = json.loads(out)
        if "code" in d:
            log(f"  OAuth ✅ code={d['code'][:20]}...")
            return d["code"]
        log(f"  OAuth ❌ {d}")
        return None
    except:
        log(f"  OAuth parse error: {out[:200]}")
        return None

# ── SlimeNodes session ────────────────────────────────────────
def get_session(code):
    log("Getting SlimeNodes session...")
    r = subprocess.run([
        "curl", "-s", "-D", "-", "--connect-timeout", "20", "--max-time", "25",
        *px(),
        f"{BASE}/callback?code={code}",
    ], capture_output=True, text=True, timeout=30)
    cookie = ""
    for line in r.stdout.splitlines():
        m = re.match(r"set-cookie:\s*([^=]+)=([^;]+)", line, re.I)
        if m:
            cookie = f"{m.group(1)}={m.group(2)}"
    if cookie:
        log(f"  Session ✅ cookie={cookie[:30]}...")
        return cookie
    log(f"  Session ❌ no cookie in:\n{r.stdout[:300]}")
    return None

# ── Coin operations ────────────────────────────────────────────
def redeem_ad(cookie):
    out = run_curl([
        "-H", f"User-Agent: {UA}",
        "-H", f"Cookie: {cookie}",
        f"{BASE}/api/redeem-ad",
    ], timeout=15)
    try:
        return json.loads(out)
    except:
        log(f"  redeem parse error: {out[:200]}")
        return None

def get_balance(cookie):
    out = run_curl([
        "-H", f"User-Agent: {UA}",
        "-H", f"Cookie: {cookie}",
        f"{BASE}/api/user",
    ], timeout=15)
    try:
        d = json.loads(out)
        return d.get("coins", -1), d.get("servers", [])
    except:
        return -1, []

def renew_server(cookie, sid):
    out = run_curl([
        "-H", f"User-Agent: {UA}",
        "-H", f"Cookie: {cookie}",
        f"{BASE}/api/lastrenew?id={sid}",
    ], timeout=15)
    try:
        return json.loads(out)
    except:
        log(f"  renew parse error: {out[:200]}")
        return None

# ── main ───────────────────────────────────────────────────────
def main():
    raw = os.environ.get("SLIME_ACCOUNTS", "").strip()
    if not raw:
        log("❌ SLIME_ACCOUNTS not set"); return

    # Parse accounts - supports JSON format (list of dicts with "token" key)
    try:
        accts = json.loads(raw)
        if isinstance(accts, str):
            accts = [{"token": accts}]
        elif isinstance(accts, dict):
            accts = [accts]
    except:
        # Fallback: treat as plain token string
        accts = [{"token": raw}]

    log(f"Parsed {len(accts)} account(s)")
    max_ads = int(os.environ.get("MAX_ADS", "20"))
    total_coins = 0

    for a in accts:
        tok = a.get("token", "")
        label = a.get("label", a.get("email", f"acct"))
        if not tok:
            log(f"❌ [{label}] no token, skipping"); continue

        log(f"\n{'='*40}")
        log(f"Account: {label}")
        log(f"  token len={len(tok)} prefix={tok[:12]}...")

        # OAuth
        code = discord_oauth(tok)
        if not code:
            log(f"❌ {label}: OAuth failed, skipping")
            total_coins += 0
            continue

        # Session
        sess = get_session(code)
        if not sess:
            log(f"❌ {label}: session failed, skipping")
            continue

        # Check balance before
        coins_before, servers = get_balance(sess)
        log(f"  Balance before: {coins_before}, servers: {len(servers)}")

        # Watch ads
        earned = 0
        for i in range(max_ads):
            r = redeem_ad(sess)
            if not r:
                log(f"  Ad #{i+1}: no response"); break
            if r.get("success"):
                earned += 12
                log(f"  Ad #{i+1}: ✅ +12 (total +{earned})")
            else:
                msg = r.get("message", str(r))
                log(f"  Ad #{i+1}: ❌ {msg}")
                if "limit" in str(r).lower() or "max" in str(r).lower() or "cooldown" in str(r).lower():
                    break
            time.sleep(16)

        # Check balance after
        coins_after, _ = get_balance(sess)
        diff = coins_after - coins_before if coins_after >= 0 and coins_before >= 0 else earned
        log(f"  Balance after: {coins_after} (Δ={diff})")
        total_coins += diff

        # Renew servers if expiring soon
        for s in servers:
            sid = s.get("id") or s.get("server_id")
            exp = s.get("expires") or s.get("expiry", "")
            if sid:
                log(f"  Checking server {sid} (expires: {exp})")
                r = renew_server(sess, sid)
                log(f"  Renew result: {r}")

    log(f"\n{'='*40}")
    log(f"Total earned: +{total_coins} coins")

    # Telegram notification
    bot_tok = os.environ.get("TG_BOT_TOKEN", "")
    chat_id = os.environ.get("TG_CHAT_ID", "")
    if bot_tok and chat_id:
        msg = f"🟢 SlimeNodes 刷币\n✅ +{total_coins}币\n💰 总计: +{total_coins}币"
        run_curl([
            f"https://api.telegram.org/bot{bot_tok}/sendMessage",
            "-d", f"chat_id={chat_id}",
            "-d", f"text={msg}",
        ])
        log("  TG notify sent")

if __name__ == "__main__":
    main()
