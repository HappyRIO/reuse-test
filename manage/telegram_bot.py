"""Minimal Telegram long-poll bot (urllib only)."""
from __future__ import annotations

import html
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import process
from .config import cfg
from .puzzles import list_puzzles
from .status import format_config, format_status, host_tag

API = "https://api.telegram.org/bot{token}/{method}"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)

HELP = """keyhunt control bot
[{tag}]

Status
/status — running status
/config — current config

Control
/start_hunt | /resume — start/resume finder
/stop_hunt — stop finder
/pause — pause (stop, keep settings)
/restart_hunt — restart finder

Tune
/threads N — set threads (safe max enforced)
/puzzle N — switch puzzle (known: {puzzles})

/help — this message"""


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
        """High-visibility KEY FOUND alert (Telegram HTML)."""
        body = (
            f"🚨 <b>KEY FOUND</b> 🚨\n"
            f"<code>{_esc(host_tag())}</code>\n\n"
            f"<b>Details</b>\n"
            f"<pre>{_esc(preview.strip() or '(empty)')}</pre>"
        )
        self.send(body, parse_mode="HTML", prefix_host=False)

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
            return HELP.format(tag=host_tag(), puzzles=list_puzzles())

        if cmd == "/status":
            return format_status()
        if cmd == "/config":
            return format_config()

        if cmd in ("/start_hunt", "/resume"):
            return json.dumps(process.resume() if cmd == "/resume" else process.start(), indent=2)
        if cmd == "/stop_hunt":
            return json.dumps(process.stop(reason="stop"), indent=2)
        if cmd == "/pause":
            return json.dumps(process.pause(), indent=2)
        if cmd == "/restart_hunt":
            return json.dumps(process.restart(), indent=2)

        if cmd == "/threads":
            if not args:
                return "Usage: /threads N"
            try:
                n = int(args[0])
            except ValueError:
                return "threads must be an integer"
            return json.dumps(process.set_threads(n), indent=2)

        if cmd in ("/puzzle", "/bits", "/mode"):
            if not args:
                return f"Usage: /puzzle N\nKnown: {list_puzzles()}"
            try:
                bits = int(args[0])
            except ValueError:
                return "bits must be an integer"
            return json.dumps(process.set_puzzle(bits), indent=2)

        return "Unknown command. Try /help"

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
                self.send(reply, chat_id=str(chat_id))

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001
                time.sleep(3)

    def stop(self) -> None:
        self._stop.set()


def start_bot_thread(bot: TelegramBot) -> threading.Thread | None:
    if not bot.enabled():
        return None
    t = threading.Thread(target=bot.run_forever, name="telegram-bot", daemon=True)
    t.start()
    return t
