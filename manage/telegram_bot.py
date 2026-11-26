"""Minimal Telegram long-poll bot with multi-host targeting."""
from __future__ import annotations

import html
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import hosts
from . import process
from .config import cfg
from .puzzles import list_puzzles
from .status import format_config, format_status, host_tag

API = "https://api.telegram.org/bot{token}/{method}"

HELP = """keyhunt multi-host bot
router: [{tag}]  id={hid}

Target any host:
  /status [here|all|<id>|<ip>]
  /config [target]
  /pause [target]
  /resume [target]
  /start_hunt [target]
  /stop_hunt [target]
  /restart_hunt [target]
  /threads <n> [target]
  /puzzle <n> [target]
  /hosts

Examples:
  /status
  /status all
  /status vps
  /pause 13.42.38.253
  /threads 1 vps
  /puzzle 150 vps

Known puzzles: {puzzles}
Only this router listens for commands (TELEGRAM_LISTEN=1)."""


def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def _looks_like_target(token: str) -> bool:
    t = token.strip().lower()
    if t in ("all", "here", "local", "me", "this"):
        return True
    if t in hosts.local_aliases():
        return True
    if hosts.find_peer(t):
        return True
    # crude IP / hostname heuristic
    if any(c.isdigit() for c in t) and "." in t:
        return True
    return False


def _split_target(args: list[str]) -> tuple[str | None, list[str]]:
    """Extract optional target from args.

    Patterns:
      [] -> (None, [])
      [vps] -> (vps, [])
      [2, vps] / [vps, 2] -> handled by caller for threads/puzzle
    """
    if not args:
        return None, []
    if len(args) == 1:
        if _looks_like_target(args[0]) and not args[0].isdigit():
            return args[0], []
        return None, args
    # prefer last arg as target if it looks like one
    if _looks_like_target(args[-1]) and not args[-1].lstrip("-").isdigit():
        return args[-1], args[:-1]
    # or first arg as target
    if _looks_like_target(args[0]) and not args[0].lstrip("-").isdigit():
        return args[0], args[1:]
    return None, args


class TelegramBot:
    def __init__(self) -> None:
        self.token = cfg.telegram_token
        self.offset = 0
        self._stop = threading.Event()
        self.chat_ids_path = cfg.state_dir / "telegram_chats.json"
        self.chats: set[str] = set()
        if cfg.telegram_chat_id:
            self.chats.add(str(cfg.telegram_chat_id))
        self._load_chats()

    def enabled(self) -> bool:
        return bool(self.token)

    def listens(self) -> bool:
        return self.enabled() and cfg.telegram_listen

    def _load_chats(self) -> None:
        try:
            data = json.loads(self.chat_ids_path.read_text(encoding="utf-8"))
            for c in data.get("chats", []):
                self.chats.add(str(c))
        except (OSError, json.JSONDecodeError):
            pass

    def _save_chats(self) -> None:
        self.chat_ids_path.write_text(
            json.dumps({"chats": sorted(self.chats)}, indent=2),
            encoding="utf-8",
        )

    def _call(self, method: str, **params):
        url = API.format(token=self.token, method=method)
        data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            return {"ok": False, "error": f"HTTP {e.code}", "body": body[:300]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def send(
        self,
        text: str,
        chat_id: str | None = None,
        *,
        parse_mode: str | None = None,
        prefix_host: bool = True,
    ) -> None:
        targets = [chat_id] if chat_id else list(self.chats)
        if not targets:
            return
        if prefix_host:
            if parse_mode == "HTML":
                if "<code>" not in text[:80]:
                    text = f"<code>{_esc(host_tag())}</code>\n{text}"
            elif not text.startswith("["):
                text = f"[{host_tag()}]\n{text}"
        for cid in targets:
            params = {"chat_id": cid, "text": text[:4000], "disable_web_page_preview": True}
            if parse_mode:
                params["parse_mode"] = parse_mode
            self._call("sendMessage", **params)

    def broadcast(self, text: str, *, parse_mode: str | None = None) -> None:
        self.send(text, parse_mode=parse_mode)

    def broadcast_keyfound(self, preview: str) -> None:
        body = (
            f"🚨 <b>KEY FOUND</b> 🚨\n"
            f"<code>{_esc(host_tag())}</code>\n\n"
            f"<b>Details</b>\n"
            f"<pre>{_esc(preview.strip() or '(empty)')}</pre>"
        )
        self.send(body, parse_mode="HTML", prefix_host=False)

    def _run_local(self, action: str, args: list[str]) -> str:
        if action == "status":
            return format_status()
        if action == "config":
            return format_config()
        if action == "start":
            return json.dumps(process.start(), indent=2)
        if action == "resume":
            return json.dumps(process.resume(), indent=2)
        if action == "stop":
            return json.dumps(process.stop(reason="stop"), indent=2)
        if action == "pause":
            return json.dumps(process.pause(), indent=2)
        if action == "restart":
            return json.dumps(process.restart(), indent=2)
        if action == "threads":
            if not args:
                return "Usage: /threads <n> [target]"
            try:
                n = int(args[0])
            except ValueError:
                return "threads must be an integer"
            return json.dumps(process.set_threads(n), indent=2)
        if action == "puzzle":
            if not args:
                return f"Usage: /puzzle <n> [target]\nKnown: {list_puzzles()}"
            try:
                bits = int(args[0])
            except ValueError:
                return "bits must be an integer"
            return json.dumps(process.set_puzzle(bits), indent=2)
        return f"unknown action {action}"

    def _run_peer(self, peer: dict, action: str, args: list[str]) -> str:
        label = peer["id"]
        if action == "status":
            return f"[{label}]\n" + hosts.peer_text(hosts.api_call(peer, "GET", "/status"))
        if action == "config":
            return f"[{label}]\n" + hosts.peer_text(hosts.api_call(peer, "GET", "/config"))
        path_map = {
            "start": "/start",
            "resume": "/resume",
            "stop": "/stop",
            "pause": "/pause",
            "restart": "/restart",
        }
        if action in path_map:
            return f"[{label}]\n" + hosts.peer_text(hosts.api_call(peer, "POST", path_map[action]))
        if action == "threads":
            if not args:
                return "Usage: /threads <n> [target]"
            try:
                n = int(args[0])
            except ValueError:
                return "threads must be an integer"
            return f"[{label}]\n" + hosts.peer_text(
                hosts.api_call(peer, "POST", "/threads", {"threads": n})
            )
        if action == "puzzle":
            if not args:
                return f"Usage: /puzzle <n> [target]\nKnown: {list_puzzles()}"
            try:
                bits = int(args[0])
            except ValueError:
                return "bits must be an integer"
            return f"[{label}]\n" + hosts.peer_text(
                hosts.api_call(peer, "POST", "/puzzle", {"bits": bits})
            )
        return f"unknown action {action}"

    def dispatch(self, action: str, target: str | None, args: list[str]) -> str:
        t = (target or "here").strip().lower()

        if t == "all":
            chunks = [f"=== {hosts.host_id()} (here) ===\n{self._run_local(action, args)}"]
            for peer in hosts.load_peers():
                chunks.append(f"=== {peer['id']} ===\n{self._run_peer(peer, action, args)}")
            return "\n\n".join(chunks)

        if hosts.is_local_target(t):
            return self._run_local(action, args)

        peer = hosts.find_peer(t)
        if not peer:
            return (
                f"Unknown target '{target}'.\n"
                f"Use /hosts to list.\n"
                f"{hosts.list_targets()}"
            )
        return self._run_peer(peer, action, args)

    def handle_command(self, chat_id: str, text: str) -> str:
        parts = (text or "").strip().split()
        if not parts:
            return "Empty command. Try /help"
        cmd = parts[0].lower()
        if "@" in cmd:
            cmd = cmd.split("@", 1)[0]
        args = parts[1:]

        if cmd in ("/start", "/help"):
            self.chats.add(str(chat_id))
            self._save_chats()
            return HELP.format(tag=host_tag(), hid=hosts.host_id(), puzzles=list_puzzles())

        if cmd == "/hosts":
            return hosts.list_targets()

        action_map = {
            "/status": "status",
            "/config": "config",
            "/start_hunt": "start",
            "/resume": "resume",
            "/stop_hunt": "stop",
            "/pause": "pause",
            "/restart_hunt": "restart",
            "/threads": "threads",
            "/puzzle": "puzzle",
            "/bits": "puzzle",
            "/mode": "puzzle",
        }
        action = action_map.get(cmd)
        if not action:
            return "Unknown command. Try /help"

        if action in ("threads", "puzzle"):
            target, rest = _split_target(args)
            # rest should contain the numeric arg
            if not rest and args and args[0].lstrip("-").isdigit():
                rest = [args[0]]
                target = args[1] if len(args) > 1 else target
            return self.dispatch(action, target, rest)

        target, rest = _split_target(args)
        return self.dispatch(action, target, rest)

    def poll_once(self) -> None:
        res = self._call(
            "getUpdates",
            offset=self.offset,
            timeout=25,
            allowed_updates=json.dumps(["message"]),
        )
        if not res.get("ok"):
            time.sleep(2)
            return
        for upd in res.get("result", []):
            self.offset = max(self.offset, int(upd["update_id"]) + 1)
            msg = upd.get("message") or {}
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            text = msg.get("text") or ""
            if chat_id is None:
                continue
            if text.startswith("/"):
                reply = self.handle_command(str(chat_id), text)
                # split long replies
                while reply:
                    chunk, reply = reply[:4000], reply[4000:]
                    self.send(chunk, chat_id=str(chat_id), prefix_host=False)

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001
                time.sleep(3)

    def stop(self) -> None:
        self._stop.set()


def start_bot_thread(bot: TelegramBot) -> threading.Thread | None:
    # Alerts work without listen; command polling only if TELEGRAM_LISTEN=1
    if not bot.enabled():
        return None
    if not bot.listens():
        print("[manage] TELEGRAM_LISTEN=0 — alerts only (no command polling)", flush=True)
        return None
    t = threading.Thread(target=bot.run_forever, name="telegram-bot", daemon=True)
    t.start()
    print(f"[manage] Telegram command router id={hosts.host_id()}", flush=True)
    return t
