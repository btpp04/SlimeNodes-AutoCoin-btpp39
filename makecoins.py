#!/usr/bin/env python3
"""SlimeNodes Auto-Coin - Pure HTTP, no browser needed."""
import os, sys, re, json, time, base64, random, subprocess
from urllib.parse import unquote, quote
from datetime import datetime, timezone

BASE = "https://dash.slimenodes.com"
CID = "1267847469501513799"
SCO = "identify email guilds.join"
CPC = 12  # coins per claim
WAIT = 20  # min seconds between gen and redeem
MAX = int(os.environ.get("MAX_ADS", "20"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
TGT = os.environ.get("TG_BOT_TOKEN", "")
TGC = os.environ.get("TG_CHAT_ID", "")
PX = os.environ.get("SOCKS_PROXY", os.environ.get("HTTP_PROXY", ""))
SID = os.environ.get("SERVER_ID", "")
RENEW_HOURS = int(os.environ.get("RENEW_HOURS", "24"))
RENEW_THRESHOLD = int(os.environ.get("RENEW_THRESHOLD", "50"))

def px(): return ["-x", PX] if PX else []
def log(m): print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {m}", flush=True)
def ok(m): log(f"✅ {m}")
def er(m): log(f"❌ {m}")

def run_curl(args, timeout=25):
    cmd = ["curl", "-s", "--connect-timeout", "20", "--max-time", str(timeout)] + px() + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+10)
        return r.stdout
    except Exception as e:
        return f"ERR:{e}"

def send_tg(msg):
    if not TGT or not TGC: return
    run_curl(["-s", "-X", "POST", f"https://api.telegram.org/bot{TGT}/sendMessage",
              "-H", "Content-Type: application/json",
              "-d", json.dumps({"chat_id": TGC, "text": msg, "parse_mode": "HTML"})],
             timeout=15)

def discord_oauth(tok):
    log("Discord OAuth...")
    url = (f"https://discord.com/api/v9/oauth2/authorize"
           f"?client_id={CID}&scope={quote(SCO)}"
           f"&response_type=code&redirect_uri={quote(BASE+'/callback',safe='')}")
    body = run_curl(["-X", "POST", "-H", f"User-Agent: {UA}",
                     "-H", "Authorization: " + tok,
                     "-H", "Content-Type: application/json",
                     "-d", json.dumps({"authorize": True}), url])
    try:
        loc = json.loads(body).get("location", "")
    except:
        er(f"OAuth fail: {body[:150]}"); return None
    if "code=" not in loc:
        er(f"OAuth no code: {body[:150]}"); return None
    code = loc.split("code=")[1].split("&")[0]
    log(f"Code: {code[:6]}...")

    # Get session - NO -L (don't follow redirect to /dashboard)
    jar = "/tmp/sn-j.txt"
    hdr = "/tmp/sn-h.txt"
    cmd = ["curl", "-s", "-c", jar, "-D", hdr,
           "--connect-timeout", "20", "--max-time", "20"] + px()
    cmd += ["-H", f"User-Agent: {UA}",
            f"{BASE}/submitlogin?code={code}"]
    subprocess.run(cmd, timeout=30, capture_output=True)

    # Parse session from cookie jar
    try:
        with open(jar) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 7 and "connect.sid" in line:
                    ok("Session OK")
                    return parts[-1]  # Last field is the value
    except: pass

    # Fallback: parse from headers
    try:
        with open(hdr) as f:
            for line in f:
                m = re.search(r'connect\.sid=([^;\s]+)', line)
                if m:
                    ok("Session OK (hdr)")
                    return m.group(1)
    except: pass

    er("Session fail"); return None

def ck(s): return f"connect.sid={s}"

def cooldown(s):
    body = run_curl(["-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}",
                     f"{BASE}/api/lvcooldown"])
    try: return json.loads(body)
    except: return {"error": body[:80]}

def gen(s):
    hdr = "/tmp/sng.txt"
    cmd = ["curl", "-s", "-D", hdr, "--connect-timeout", "20", "--max-time", "20"] + px()
    cmd += ["-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}",
            "-H", f"Referer: {BASE}/lv", f"{BASE}/lv/gen"]
    try:
        body = subprocess.run(cmd, capture_output=True, text=True, timeout=25).stdout
        loc = ""
        with open(hdr) as f:
            for line in f:
                if line.lower().startswith("location:"):
                    loc = line.split(":",1)[1].strip(); break
        if not loc:
            m = re.search(r'href="(https://link-to\.net/[^"]+)"', body)
            if m: loc = m.group(1)
        if not loc:
            if "daily" in body.lower() and "limit" in body.lower(): return "DAILY_LIMIT"
            if "/login" in (loc or body): return "SESSION_EXPIRED"
            er(f"Gen fail: {body[:120]}"); return None
        rm = re.search(r'[?&]r=([^&\s]+)', loc)
        if not rm: er(f"No r: {loc[:60]}"); return None
        rp = unquote(rm.group(1)).replace("-","+").replace("_","/")
        rp += "=" * ((4-len(rp)%4)%4)
        try: return base64.b64decode(rp).decode()
        except: er("b64 fail"); return None
    except Exception as e:
        er(f"Gen err: {e}"); return None

def red(s, url):
    hdr = "/tmp/snr.txt"
    cmd = ["curl", "-s", "-D", hdr, "--connect-timeout", "20", "--max-time", "20"] + px()
    cmd += ["-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}",
            "-H", "Referer: https://linkvertise.com/", url]
    subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    loc = ""
    with open(hdr) as f:
        for line in f:
            if line.lower().startswith("location:"):
                loc = line.split(":",1)[1].strip(); break
    if "success=true" in loc: return "OK"
    if "LVBYPASSERROR" in loc: return "BYPASS"
    if "/login" in loc: return "SESSION_EXPIRED"
    if "daily" in loc.lower(): return "DAILY_LIMIT"
    return f"UNK:{loc[:40]}"

def bal(s):
    body = run_curl(["-L", "-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}",
                     f"{BASE}/dashboard"])
    m = re.search(r'balance\.textContent\s*=\s*Math\.floor\((\d+)\s*\*\s*100\)', body)
    return int(m.group(1)) if m else None

def get_renew_info(s):
    """Get server expiration from dashboard page. Returns hours_left or None"""
    if not SID: return None
    import re
    try:
        body = run_curl(["-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}",
                         f"{BASE}/servers"], timeout=15)
        # Parse "Server expires in X hours"
        m = re.search(r'expires? in (\d+) hours?', body, re.IGNORECASE)
        if m:
            return int(m.group(1))
        # Try "expires in X days"
        m = re.search(r'expires? in (\d+) days?', body, re.IGNORECASE)
        if m:
            return int(m.group(1)) * 24
        return None
    except:
        return None



def renew_server(s):
    """Renew server - click renew on dashboard page"""
    if not SID: return False
    # Try direct renew URL
    body = run_curl(["-L", "-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}",
                     f"{BASE}/renew?id={SID}"], timeout=20)
    if "success" in body.lower() or "renewed" in body.lower():
        return True
    # Check if redirected to dashboard (success)
    if "/dashboard" in body[:500].lower():
        return True
    log(f"[renew] Renew failed - needs manual renew")
    return False

def process(tok, lab="acct"):
    log(f"\n{'='*40}\n账号: {lab}\n{'='*40}")
    s = discord_oauth(tok)
    if not s: er(f"[{lab}] 登录失败"); return 0, False
    b0 = bal(s)
    if b0 is not None: log(f"[{lab}] 余额: {b0}币")

    earned = 0; bypass = 0; daily = False
    for i in range(MAX):
        cd = cooldown(s)
        if cd.get("dailyLimit"): log(f"[{lab}] 每日上限"); daily = True; break
        ru = gen(s)
        if ru == "DAILY_LIMIT": daily = True; break
        if ru == "SESSION_EXPIRED": er(f"[{lab}] Session过期"); break
        if not ru: er(f"[{lab}] gen失败"); break
        w = WAIT + random.randint(1, 4)
        log(f"[{lab}] 广告{i+1}/{MAX}: 等{w}s...")
        time.sleep(w)
        r = red(s, ru)
        if r == "OK":
            earned += CPC; bypass = 0
            ok(f"[{lab}] +{CPC}币 (累计+{earned})")
        elif r == "BYPASS":
            bypass += 1; er(f"[{lab}] BYPASS")
            if bypass >= 3: break
            time.sleep(10)
        elif r == "SESSION_EXPIRED": er(f"[{lab}] Session过期"); break
        elif r == "DAILY_LIMIT": daily = True; break
        else:
            er(f"[{lab}] {r}")
            if "UNK" in r and i < MAX - 1:
                log(f"[{lab}] retry redeem (wait 30s)...")
                time.sleep(30)
                r2 = red(s, ru)
                if r2 == "OK":
                    earned += CPC; bypass = 0
                    ok(f"[{lab}] +{CPC} retry OK (total +{earned})")
                    continue
                elif r2 == "SESSION_EXPIRED":
                    er(f"[{lab}] Session expired"); break
                elif r2 == "DAILY_LIMIT":
                    daily = True; break
                else:
                    er(f"[{lab}] retry also failed: {r2}")
            time.sleep(random.randint(3, 6))

    b1 = bal(s)
    if b1 is not None:
        actual = max(b1 - b0, 0) if b0 is not None else earned
        log(f"[{lab}] 最终: {b1}币 (本次实际+{actual})")
        return actual, daily, b1
    return earned, daily, None

def main():
    raw = os.environ.get("SLIME_ACCOUNTS", "").strip()
    if not raw: er("SLIME_ACCOUNTS未设置!"); sys.exit(1)
    try:
        accts = json.loads(raw)
        if isinstance(accts, str): accts = [{"token": accts}]
        elif isinstance(accts, dict): accts = [accts]
        elif isinstance(accts, list):
            for i, a in enumerate(accts):
                if isinstance(a, str): accts[i] = {"token": a}
        elif isinstance(accts, (int, float)): accts = [{"token": raw}]
    except (json.JSONDecodeError, ValueError): accts = [{"token": raw}]

    total = 0; res = []
    for a in accts:
        t = a.get("token",""); l = a.get("label", a.get("email", f"acct{len(res)+1}"))
        if not t: er(f"[{l}] 无token"); continue
        c, d, b1 = process(t, l); total += c
        res.append({"l": l, "c": c, "d": d, "b": b1})
        
        # Auto-renew check
        if SID and b1 is not None and b1 >= RENEW_THRESHOLD:
            hours_left = get_renew_info(t)
            if hours_left is not None:
                log(f"[{l}] 服务器剩余: {hours_left}小时")
                if hours_left < RENEW_HOURS:
                    log(f"[{l}] 续期中...")
                    if renew_server(t):
                        log(f"[{l}] ✅ 服务器已续期")
                        res[-1]["r"] = True
                    else:
                        log(f"[{l}] ⚠️ 续期失败, 请手动续期")
                        res[-1]["r"] = False
                else:
                    log(f"[{l}] 离到期还有{hours_left}小时，暂不续期")
                    res[-1]["r"] = None
            else:
                log(f"[{l}] 无法获取到期时间")
                res[-1]["r"] = None
        elif SID and b1 is not None and b1 < RENEW_THRESHOLD:
            log(f"[{l}] 余额不足续期 (需{RENEW_THRESHOLD}币)")
            res[-1]["r"] = None

    log(f"\n总计: +{total}币")
    dt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"<b>🟢 SlimeNodes 刷币</b>  {dt}"]
    for r in res:
        s = "✅" if r["c"]>0 else "❌"; dl = " (上限)" if r["d"] else ""
        bl = f" | 余额{r['b']}" if r.get("b") is not None else ""
        renew = ""
        if r.get("r") is True: renew = " | 🔄已续期"
        elif r.get("r") is False: renew = " | ❌续期失败"
        lines.append(f"{s} {r['l']}: +{r['c']}币{dl}{bl}{renew}")
    lines.append(f"\n💰 总计: +{total}币")
    send_tg("\n".join(lines))
    log("完成!")

if __name__ == "__main__":
    main()


