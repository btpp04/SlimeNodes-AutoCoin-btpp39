#!/usr/bin/env python3
"""SlimeNodes AutoCoin - earn coins by watching ads."""
import os, sys, json, time, subprocess, re

log = lambda *a: print(*a, flush=True)

# ── proxy helpers ──────────────────────────────────────────────
PX = os.environ.get("SOCKS_PROXY") or os.environ.get("HTTP_PROXY") or ""
log(f"MODULE_LEVEL: SOCKS_PROXY={os.environ.get('SOCKS_PROXY','')!r} PX={PX!r}")

def px():
    if not PX:
        return []
    p = PX.replace("socks5://", "socks5h://")
    return ["--proxy", p]

# ── curl helper ────────────────────────────────────────────────
def run_curl(args, timeout=30):
    base = ["curl", "-s", "--connect-timeout", "20", "--max-time", str(timeout)]
    cmd = base + px() + args
    log(f"  CMD: {' '.join(cmd[:8])}...")  # debug: show first 8 args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
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
    log(f"  DEBUG PX={PX!r} px()={px()!r}")
    log(f"  DEBUG tok len={len(tok)} prefix={tok[:10]}... suffix=...{tok[-5:]}")
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
    out = subprocess.run([
        "curl", "-s", "-D", "-", "--connect-timeout", "20", "--max-time", "25",
        *px(),
        f"{BASE}/callback?code={code}",
    ], capture_output=True, text=True, timeout=30)
    cookie = ""
    for line in out.stdout.splitlines():
        m = re.match(r"set-cookie:\s*([^=]+)=([^;]+)", line, re.I)
        if m:
            cookie = f"{m.group(1)}={m.group(2)}"
    if cookie:
        log(f"  Session ✅ cookie={cookie[:20]}...")
        return cookie
    log(f"  Session ❌ no cookie in:\n{out.stdout[:300]}")
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
    accounts_raw = os.environ.get("SLIME_ACCOUNTS", "")
    if not accounts_raw:
        log("No SLIME_ACCOUNTS env var"); return

    max_ads = int(os.environ.get("MAX_ADS", "20"))
    total_coins = 0

    for line in accounts_raw.strip().splitlines():
        parts = line.strip().split(":", 2)
        if len(parts) < 3:
            log(f"Skip bad line: {line[:30]}..."); continue
        name, email, tok = parts[0], parts[1], parts[2]
        log(f"\n{'='*40}")
        log(f"Account: {name}")

        # OAuth
        code = discord_oauth(tok)
        if not code:
            log(f"❌ {name}: OAuth failed, skipping")
            continue

        # Session
        sess = get_session(code)
        if not sess:
            log(f"❌ {name}: session failed, skipping")
            continue

        # Check balance first
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
                log(f"  Ad #{i+1}: ❌ {r}")
                if "limit" in str(r).lower() or "max" in str(r).lower():
                    break
            time.sleep(16)

        # Check balance after
        coins_after, _ = get_balance(sess)
        diff = coins_after - coins_before if coins_after >= 0 and coins_before >= 0 else earned
        log(f"  Balance after: {coins_after} (Δ={diff})")
        total_coins += diff

        # Renew server if expiring soon
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
        msg = f"🟢 SlimeNodes 刷币\n✅ 39btpp: +{total_coins}币\n💰 总计: +{total_coins}币"
        run_curl([
            f"https://api.telegram.org/bot{bot_tok}/sendMessage",
            "-d", f"chat_id={chat_id}",
            "-d", f"text={msg}",
        ])
        log("  TG notify sent")

if __name__ == "__main__":
    main()
