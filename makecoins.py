#!/usr/bin/env python3
"""SlimeNodes Auto-Coin + Auto-Renew (btpp39 session cookie mode)"""
import os, sys, re, json, time, base64, random, subprocess
from urllib.parse import unquote
from datetime import datetime, timezone

BASE = "https://dash.slimenodes.com"
CPC = 12
WAIT = 16
MAX = int(os.environ.get("MAX_ADS", "20"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
TGT = os.environ.get("TG_BOT_TOKEN", "")
TGC = os.environ.get("TG_CHAT_ID", "")
PX = os.environ.get("SOCKS_PROXY", os.environ.get("HTTP_PROXY", ""))
SESSION = os.environ.get("SLIME_SESSION", "")
SERVER_ID = os.environ.get("SERVER_ID", "")
RENEW_THRESHOLD = int(os.environ.get("RENEW_THRESHOLD", "50"))
RENEW_HOURS = int(os.environ.get("RENEW_HOURS", "24"))

def px(): return ["-x", PX] if PX else []
def log(m): print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {m}", flush=True)
def ok(m): log(f"\u2705 {m}")
def er(m): log(f"\u274c {m}")

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
              "-d", json.dumps({"chat_id": TGC, "text": msg, "parse_mode": "HTML"})], timeout=15)

def ck(s): return f"connect.sid={s}"

def cooldown(s):
    body = run_curl(["-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}", f"{BASE}/api/lvcooldown"])
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
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    body = result.stdout or ""
    loc = ""
    with open(hdr) as f:
        for line in f:
            if line.lower().startswith("location:"):
                loc = line.split(":",1)[1].strip(); break
    # linkvertise 加了 Cloudflare bot 拦截, 看到 "Attention Required" 直接放弃整个循环
    if "Attention Required" in body or "cf-mitigated" in body:
        return "BLOCKED"
    if "success=true" in loc: return "OK"
    if "LVBYPASSERROR" in loc: return "BYPASS"
    if "/login" in loc: return "SESSION_EXPIRED"
    if "daily" in loc.lower(): return "DAILY_LIMIT"
    return f"UNK:{loc[:40]}"

def bal(s):
    body = run_curl(["-L", "-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}", f"{BASE}/dashboard"])
    m = re.search(r'balance\.textContent\s*=\s*Math\.floor\((\d+)\s*\*\s*100\)', body)
    return int(m.group(1)) if m else None

def renew(s, server_id):
    """Renew server. Returns True if successful."""
    log(f"Renewing server {server_id}...")
    cmd = ["curl", "-s", "-L", "-w", "\n%{url_effective}", "--connect-timeout", "20", "--max-time", "20"] + px()
    cmd += ["-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}", f"{BASE}/renew?id={server_id}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        output = result.stdout
        lines = output.strip().split("\n")
        final_url = lines[-1] if lines else ""
        log(f"Renew URL: {final_url[:80]}")
        if "success=RENEWED" in final_url or "RENEWED" in final_url:
            ok("Server renewed!"); return True
        if "/login" in final_url:
            er("Session expired during renew"); return False
        er(f"Renew failed: {final_url[:80]}"); return False
    except Exception as e:
        er(f"Renew error: {e}"); return False

def process(session_id, label="acct"):
    log(f"\n{'='*40}\n账号: {label}\n{'='*40}")
    b0 = bal(session_id)
    if b0 is not None: log(f"余额: {b0}币")
    else: er("无法获取余额")

    earned = 0; bypass = 0; daily = False
    for i in range(MAX):
        cd = cooldown(session_id)
        if cd.get("dailyLimit"): log("每日上限"); daily = True; break
        ru = gen(session_id)
        if ru == "DAILY_LIMIT": daily = True; break
        if ru == "SESSION_EXPIRED": er("Session过期"); break
        if not ru: er("gen失败"); break
        w = WAIT + random.randint(1, 4)
        log(f"广告{i+1}/{MAX}: 等{w}s...")
        time.sleep(w)
        r = red(session_id, ru)
        if r == "OK":
            earned += CPC; bypass = 0
            ok(f"+{CPC}币 (累计+{earned})")
        elif r == "BLOCKED":
            er("linkvertise 拦了 (CF bot challenge) - 跳过剩余")
            break
        elif r == "BYPASS":
            bypass += 1; er("BYPASS")
            if bypass >= 3: break
            time.sleep(10)
        elif r == "SESSION_EXPIRED": er("Session过期"); break
        elif r == "DAILY_LIMIT": daily = True; break
        else:
            er(r)
            if "UNK" in r and i < MAX - 1:
                log("retry redeem (wait 30s)...")
                time.sleep(30)
                r2 = red(session_id, ru)
                if r2 == "OK":
                    earned += CPC; bypass = 0
                    ok(f"+{CPC} retry OK (total +{earned})")
                    continue
                elif r2 == "SESSION_EXPIRED": er("Session expired"); break
                elif r2 == "DAILY_LIMIT": daily = True; break
                else: er(f"retry also failed: {r2}")
            time.sleep(random.randint(3, 6))

    b1 = bal(session_id)
    actual = max(b1 - b0, 0) if b0 is not None and b1 is not None else earned
    log(f"刷币完成: {b1}币 (本次+{actual})")

    # Auto-renew
    renewed = False
    hours_left = None
    if SERVER_ID and b1 is not None and b1 >= RENEW_THRESHOLD:
        cd_body = run_curl(["-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(session_id)}",
                            f"{BASE}/lastrenew?id={SERVER_ID}"])
        try:
            last_renew_ms = json.loads(cd_body).get("lastrenew", 0)
            now_ms = time.time() * 1000
            hours_left = (last_renew_ms - now_ms) / (1000 * 60 * 60)
            if last_renew_ms == 0:
                log(f"/lastrenew返回0 (Server ID格式可能不对)")
                hours_left = None
            else:
                log(f"服务器剩余: {hours_left:.0f}小时")
        except:
            log("无法获取到期时间")
        if hours_left is not None and hours_left > RENEW_HOURS:
            log(f"暂不续期 (>{RENEW_HOURS}h)")
        elif hours_left is not None:
            renewed = renew(session_id, SERVER_ID)
            if renewed:
                b2 = bal(session_id)
                if b2 is not None: log(f"续期后余额: {b2}")
    elif SERVER_ID and b1 is not None:
        log(f"余额不足续期 (需要{RENEW_THRESHOLD}币, 当前{b1}币)")

    return actual, daily, b1, renewed, hours_left if SERVER_ID else None

def main():
    if not SESSION: er("SLIME_SESSION未设置!"); sys.exit(1)
    label = "39btpp"
    c, d, b1, renewed, hours_left = process(SESSION, label)

    # TG notification
    lines = [f"<b>🟢 SlimeNodes 刷币</b>  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"]
    s = "✅" if c > 0 else "❌"
    dl = " (上限)" if d else ""
    bl = f" | 余额{b1}" if b1 is not None else ""
    lines.append(f"{s} {label}: +{c}币{dl}{bl}")
    if hours_left is not None and hours_left > 0:
        days = hours_left / 24
        lines.append(f"⏰ 剩余: {hours_left:.0f}小时 ({days:.1f}天)")
    elif hours_left is not None:
        lines.append(f"⏰ 到期时间获取异常 (Server ID可能不对)")
    if renewed:
        lines.append("🔄 续期: ✅ 已续期")
    elif hours_left is not None and hours_left > RENEW_HOURS:
        lines.append(f"🔄 续期: ⏭️ 暂不需要 (>{RENEW_HOURS}h)")
    elif hours_left is not None and hours_left > 0:
        lines.append("🔄 续期: ❌ 失败")
    elif not SERVER_ID:
        lines.append("🔄 续期: 未配置SERVER_ID")
    lines.append(f"\n💰 总计: +{c}币")
    send_tg("\n".join(lines))
    log("完成!")

if __name__ == "__main__":
    main()
