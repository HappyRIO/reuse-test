"""Host identity + peer routing for multi-instance Telegram/API control."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from typing import Any

from .config import cfg
from . import runtime


def host_id() -> str:
    return (cfg.host_id or os.uname().nodename.split(".")[0] or "local").strip()


def local_aliases() -> set[str]:
    aliases = {
        host_id().lower(),
        "here",
        "local",
        "me",
        os.uname().nodename.lower(),
        runtime.primary_ip().lower(),
    }
    if cfg.public_ip:
        aliases.add(cfg.public_ip.lower())
    # short hostname pieces
    aliases.add(os.uname().nodename.split(".")[0].lower())
    return {a for a in aliases if a}


def is_local_target(target: str | None) -> bool:
    if target is None or target == "":
        return True
    t = target.strip().lower()
    if t in ("here", "local", "me", "this"):
        return True
    return t in local_aliases()


def load_peers() -> list[dict[str, Any]]:
    """Peers from manage/peers.json and/or PEERS env.

    peers.json example:
      [{"id":"vps","url":"http://13.42.38.253:8787","token":"...","aliases":["vps","13.42.38.253"]}]

    PEERS env (semicolon-separated):
      id|url|token|alias1,alias2; id2|url2|token2
    """
    peers: list[dict[str, Any]] = []
    path = cfg.root / "manage" / "peers.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                peers.extend(data)
        except (OSError, json.JSONDecodeError):
            pass

    raw = cfg.peers_env.strip()
    if raw:
        for chunk in raw.split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = [p.strip() for p in chunk.split("|")]
            if len(parts) < 3:
                continue
            aliases = [a.strip() for a in parts[3].split(",")] if len(parts) > 3 and parts[3] else []
            peers.append(
                {
                    "id": parts[0],
                    "url": parts[1].rstrip("/"),
                    "token": parts[2],
                    "aliases": aliases,
                }
            )
    # normalize
    out = []
    for p in peers:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "").strip()
        url = str(p.get("url") or "").strip().rstrip("/")
        token = str(p.get("token") or "").strip()
        if not pid or not url or not token:
            continue
        aliases = [str(a).lower() for a in (p.get("aliases") or []) if a]
        aliases.extend([pid.lower(), url.lower()])
        # extract host from URL
        try:
            hostpart = url.split("://", 1)[-1].split("/", 1)[0]
            aliases.append(hostpart.lower())
            if ":" in hostpart:
                aliases.append(hostpart.split(":", 1)[0].lower())
        except Exception:  # noqa: BLE001
            pass
        item = {
            "id": pid,
            "url": url,
            "token": token,
            "aliases": sorted(set(aliases)),
        }
        if p.get("ssh"):
            item["ssh"] = str(p["ssh"]).strip()
        if p.get("ssh_key"):
            item["ssh_key"] = str(p["ssh_key"]).strip()
        if p.get("via"):
            item["via"] = str(p["via"]).strip()
        out.append(item)
    return out


def find_peer(target: str) -> dict[str, Any] | None:
    t = target.strip().lower()
    for p in load_peers():
        if t == p["id"].lower() or t in p["aliases"]:
            return p
    return None


def list_targets() -> str:
    lines = [f"this host: {host_id()}  aliases={sorted(local_aliases())}"]
    peers = load_peers()
    if not peers:
        lines.append("peers: (none — add manage/peers.json or PEERS in .env)")
    for p in peers:
        lines.append(f"peer: {p['id']}  url={p['url']}  aliases={p['aliases']}")
    lines.append("targets: here | all | <host_id> | <ip>")
    return "\n".join(lines)


def _api_call_direct(peer: dict[str, Any], method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    url = peer["url"] + path
    data = None
    headers = {
        "Authorization": f"Bearer {peer['token']}",
        "X-API-Token": peer["token"],
    }
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": f"HTTP {e.code}", "body": raw[:300]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "peer": peer.get("id")}


def _api_call_ssh(peer: dict[str, Any], method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    """Call peer API over SSH (no public :8787 needed)."""
    ssh_host = peer.get("ssh")
    ssh_key = peer.get("ssh_key") or ""
    if not ssh_host:
        return {"ok": False, "error": "ssh peer missing ssh=user@host"}
    payload = json.dumps({"method": method, "path": path, "token": peer["token"], "body": body})
    remote_py = (
        "import json,urllib.request;"
        f"req=json.loads({payload!r});"
        "url='http://127.0.0.1:8787'+req['path'];"
        "data=None; headers={'Authorization':'Bearer '+req['token']};"
        "body=req.get('body');"
        "\n"
        "if body is not None:\n"
        " data=json.dumps(body).encode(); headers['Content-Type']='application/json'\n"
        "r=urllib.request.Request(url,data=data,headers=headers,method=req['method']);"
        "print(urllib.request.urlopen(r,timeout=20).read().decode())"
    )
    # Use a cleaner multiline script via stdin
    script = f"""
import json, urllib.request
req = json.loads({payload!r})
url = "http://127.0.0.1:8787" + req["path"]
headers = {{"Authorization": "Bearer " + req["token"]}}
data = None
if req.get("body") is not None:
    data = json.dumps(req["body"]).encode()
    headers["Content-Type"] = "application/json"
r = urllib.request.Request(url, data=data, headers=headers, method=req["method"])
print(urllib.request.urlopen(r, timeout=20).read().decode())
"""
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if ssh_key:
        cmd.extend(["-i", ssh_key])
    cmd.extend([ssh_host, "python3", "-"])
    try:
        out = subprocess.check_output(cmd, input=script.encode(), stderr=subprocess.STDOUT, timeout=35)
        return json.loads(out.decode())
    except subprocess.CalledProcessError as e:
        return {
            "ok": False,
            "error": "ssh_api_failed",
            "detail": e.output.decode(errors="replace")[:400],
            "peer": peer.get("id"),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "peer": peer.get("id")}


def api_call(peer: dict[str, Any], method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    if peer.get("ssh"):
        return _api_call_ssh(peer, method, path, body)
    return _api_call_direct(peer, method, path, body)


def peer_text(resp: dict[str, Any]) -> str:
    if isinstance(resp.get("text"), str) and resp["text"].strip():
        return resp["text"]
    return json.dumps(resp, indent=2)
