import os, sys, json, time, re, subprocess
from datetime import datetime, timezone

CID  = "1267847469501513799"
SCO  = "identify email guilds.join"
BASE = "https://dash.slimenodes.com"
CPC  = 12
WAIT = 16
UA   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"

def log(msg):
    print(msg, flush=True)

def px():
    p = os.environ.get("PROXY_URL", "")
    return ["--proxy", p, "-x", p] if p else []

def run_curl(*args, timeout=30):
    cmd = ["curl", "-s", "-m", str(timeout)] + list(args)
    log(f"  CMD: {' '.join(cmd[:8])}{'...' if len(cmd)>8 else ''}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+10)
        return r.stdout
    except Exception as e:
        log(f"  curl error: {e}")
        return ""

# ─── OAuth ───
def discord_oauth(tok):
    url  = f"https://discord.com/api/v9/oauth2/authorize?client_id={CID}&scope={SCO}&response_type=code&redirect_uri={BASE}/callback"
    hdrs = ["-H", f"Authorization: {tok}", "-H", "Content-Type: application/json",
            "-H", f"User-Agent: {UA}", "-d", '{"authorize":true}']
    out  = run_curl(*px(), *hdrs, url)
    try:
        j = json.loads(out)
        code = j.get("location", "").split("code=")[-1] if "location" in j else j.get("code","")
        if not code or len(code) < 5:
            log(f"❌ OAuth no code: {out[:200]}")
            return None
        return code
    except:
        log(f"❌ OAuth parse error: {out[:200]}")
        return None

def get_session(code):
    out = run_curl(*px(), "-D", "-", f"{BASE}/callback?code={code}")
    sid = ""
    for line in out.splitlines():
        if "set-cookie" in line.lower() and "connect.sid" in line:
            m = re.search(r'connect\.sid=([^;]+)', line)
            if m: sid = m.group(1); break
    if not sid:
        m = re.search(r'connect\.sid=([^;\s]+)', out)
        if m: sid = m.group(1)
    return sid

# ─── Balance & Servers ───
def get_balance(sid):
    hdrs = ["-H", f"Cookie: connect.sid={sid}", "-H", f"User-Agent: {UA}"]
    out = run_curl(*px(), *hdrs, f"{BASE}/api/user")
    try:
        j = json.loads(out)
        return j.get("coins", j.get("balance", 0))
    except:
        log(f"  balance parse error: {out[:100]}")
        return 0

def get_servers(sid):
    """Fetch server list and return expiry info."""
    hdrs = ["-H", f"Cookie: connect.sid={sid}", "-H", f"User-Agent: {UA}"]
    out = run_curl(*px(), *hdrs, f"{BASE}/api/servers")
    try:
        servers = json.loads(out)
        if isinstance(servers, list):
            return servers
        if isinstance(servers, dict) and "servers" in servers:
            return servers["servers"]
        return []
    except:
        log(f"  servers parse error: {out[:100]}")
        return []

def format_expiry(servers):
    """Format server expiry info for notification."""
    if not servers:
        return "无服务器"
    lines = []
    now = datetime.now(timezone.utc)
    for s in servers:
        name = s.get("name", s.get("hostname", "server"))
        exp = s.get("expires_at") or s.get("expiresAt") or s.get("expire", "")
        if exp:
            try:
                # Try ISO format
                if exp.endswith("Z"):
                    exp = exp[:-1] + "+00:00"
                dt = datetime.fromisoformat(exp)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                remain = dt - now
                days = remain.total_seconds() / 86400
                if days > 0:
                    lines.append(f"{name}: {days:.1f}天")
                else:
                    lines.append(f"{name}: ❌已过期")
            except:
                lines.append(f"{name}: {exp}")
        else:
            lines.append(f"{name}: 未知")
    return " | ".join(lines)

# ─── Watch Ad ───
def watch_ad(sid):
    hdrs = ["-H", f"Cookie: connect.sid={sid}", "-H", f"User-Agent: {UA}",
            "-H", "Content-Type: application/json", "-X", "POST"]
    out = run_curl(*px(), *hdrs, f"{BASE}/api/redeem-ad")
    try:
        j = json.loads(out)
        if j.get("coins", 0) > 0 or j.get("success"):
            return True
        log(f"  ad resp: {out[:120]}")
        return False
    except:
        log(f"  ad error: {out[:120]}")
        return False

# ─── Process One Account ───
def process(tok, label=""):
    code = discord_oauth(tok)
    if not code:
        return 0, 0, ""

    sid = get_session(code)
    if not sid:
        log("❌ No session cookie")
        return 0, 0, ""

    # verify
    b0 = get_balance(sid)
    log(f"✅ Session OK | balance={b0}")

    # get servers expiry
    servers = get_servers(sid)
    exp_info = format_expiry(servers)
    log(f"  📅 Servers: {exp_info}")

    earned = 0
    for i in range(20):
        if watch_ad(sid):
            earned += CPC
            log(f"  +{CPC}币 ({i+1}/20)")
        else:
            log(f"  ❌ claim {i+1} failed")
        if i < 19:
            time.sleep(WAIT)

    b1 = get_balance(sid)
    return b0, b1, exp_info

# ─── TG Notify ───
def send_tg(msg):
    bt = os.environ.get("TG_BOT_TOKEN", "")
    ci = os.environ.get("TG_CHAT_ID", "")
    if not bt or not ci:
        log("⚠️ TG not configured, skip notify")
        return
    run_curl("-s", "-X", "POST", f"https://api.telegram.org/bot{bt}/sendMessage",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"chat_id": ci, "text": msg, "parse_mode": "HTML"}))

# ─── Main ───
def main():
    accts = json.loads(os.environ.get("SLIME_ACCOUNTS", "[]"))
    if not accts:
        log("❌ No SLIME_ACCOUNTS configured"); return

    total = 0
    parts = []
    dt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    for a in accts:
        label = a.get("label", "unknown")
        tok   = a.get("token", "")
        if not tok:
            log(f"⚠️ No token for {label}"); continue

        log(f"\n{'='*40}")
        log(f"▶ {label}")
        b0, b1, exp_info = process(tok, label)
        diff = b1 - b0
        total += diff
        log(f"  earned={diff}  balance={b1}")
        parts.append(f"✅ {label}: +{diff}币 | 余额{b1} | 📅{exp_info}")

    # notify
    lines = [f"<b>🟢 SlimeNodes 刷币</b>  {dt}"]
    lines.extend(parts)
    lines.append(f"💰 总计: +{total}币")
    send_tg("\n".join(lines))

if __name__ == "__main__":
    main()
