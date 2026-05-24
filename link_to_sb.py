#!/usr/bin/env python3
"""Convert proxy links to sing-box config. Supports: vmess, vless, hysteria2."""
import sys, json, base64, urllib.parse, re

def parse_vmess(link):
    data = base64.urlsafe_b64decode(link.split("://")[1] + "==").decode('utf-8')
    config = json.loads(data)
    outbound = {
        "type": "vmess", "tag": config.get("ps", "vmess-out"),
        "server": config["add"], "server_port": int(config["port"]),
        "uuid": config["id"], "security": config.get("scy", "auto"),
        "alter_id": int(config.get("aid", 0)),
    }
    if config.get("net") == "ws":
        path = config.get("path", "/")
        match = re.search(r'\?ed=(\d+)', path)
        transport = {"type": "ws", "headers": {"Host": config.get("host", "")} if config.get("host") else {}}
        if match:
            transport["max_early_data"] = int(match.group(1))
            transport["early_data_header_name"] = "Sec-WebSocket-Protocol"
            path = re.sub(r'\?ed=\d+', '', path)
        transport["path"] = path
        outbound["transport"] = transport
    if config.get("tls") == "tls":
        alpn_list = config.get("alpn", "").split(",") if config.get("alpn") else []
        outbound["tls"] = {"enabled": True, "server_name": config.get("sni") or config.get("host", ""),
            "insecure": config.get("insecure", "0") == "1", "alpn": alpn_list,
            "utls": {"enabled": True, "fingerprint": config.get("fp", "chrome")}}
    return outbound

def parse_vless(link):
    parsed = urllib.parse.urlparse(link)
    query = urllib.parse.parse_qs(parsed.query)
    outbound = {"type": "vless", "tag": "vless-out", "server": parsed.hostname,
        "server_port": parsed.port, "uuid": parsed.username}
    if query.get("security") == ["tls"]:
        alpn_list = query.get("alpn", [""])[0].split(",") if query.get("alpn") else []
        outbound["tls"] = {"enabled": True, "server_name": query.get("sni", [None])[0] or "",
            "insecure": query.get("allowInsecure", ["0"])[0] == "1", "alpn": alpn_list,
            "utls": {"enabled": True, "fingerprint": query.get("fp", ["chrome"])[0]}}
    if query.get("type") == ["ws"]:
        transport = {"type": "ws", "headers": {"Host": query.get("host", [""])[0]} if query.get("host") else {}}
        path = query.get("path", ["/"])[0]
        match = re.search(r'\?ed=(\d+)', path)
        if match:
            transport["max_early_data"] = int(match.group(1))
            transport["early_data_header_name"] = "Sec-WebSocket-Protocol"
            path = re.sub(r'\?ed=\d+', '', path)
        transport["path"] = path
        outbound["transport"] = transport
    if query.get("flow"):
        outbound["flow"] = query["flow"][0]
    return outbound

def parse_hysteria2(link):
    parsed = urllib.parse.urlparse(link)
    query = urllib.parse.parse_qs(parsed.query)
    sni = query.get("peer", [None])[0] or query.get("sni", [None])[0] or parsed.hostname
    insecure = query.get("insecure", ["0"])[0] == "1"
    outbound = {
        "type": "hysteria2", "tag": "hy2-out",
        "server": parsed.hostname, "server_port": parsed.port,
        "password": parsed.username,
        "tls": {"enabled": True, "server_name": sni, "insecure": insecure}
    }
    return outbound

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 link_to_sb.py '<proxy_link>'"); sys.exit(1)
    link = sys.argv[1].strip()
    if link.startswith("vmess://"):
        outbound = parse_vmess(link)
    elif link.startswith("vless://"):
        outbound = parse_vless(link)
    elif link.startswith("hysteria2://"):
        outbound = parse_hysteria2(link)
    else:
        print(f"不支持的链接类型: {link[:20]}..."); sys.exit(1)
    full_config = {
        "log": {"level": "info"},
        "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1",
            "listen_port": 1080, "sniff": True, "sniff_override_destination": True}],
        "outbounds": [outbound],
        "route": {"final": outbound["tag"]}
    }
    print(json.dumps(full_config, indent=2))

