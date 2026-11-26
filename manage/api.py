"""Tiny authenticated HTTP API (stdlib http.server)."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import process
from . import runtime
from .config import cfg
from .status import collect, format_config, format_status


def _json(handler: BaseHTTPRequestHandler, code: int, payload: Any) -> None:
    body = json.dumps(payload, indent=2).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _auth_ok(handler: BaseHTTPRequestHandler) -> bool:
    if not cfg.api_token:
        return False
    auth = handler.headers.get("Authorization", "")
    if auth == f"Bearer {cfg.api_token}":
        return True
    return handler.headers.get("X-API-Token") == cfg.api_token


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode() or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _query(handler: BaseHTTPRequestHandler) -> dict[str, list[str]]:
    return parse_qs(urlparse(handler.path).query)


class Handler(BaseHTTPRequestHandler):
    server_version = "keyhunt-manage/0.2"

    def log_message(self, fmt: str, *args) -> None:
        return

    def _unauthorized(self) -> None:
        _json(self, 401, {"ok": False, "error": "unauthorized"})

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            _json(self, 200, {"ok": True})
            return
        if not _auth_ok(self):
            self._unauthorized()
            return
        if path == "/status":
            st = collect()
            _json(self, 200, {"ok": True, "status": st, "text": format_status(st)})
            return
        if path == "/config":
            _json(self, 200, {"ok": True, "config": runtime.config_view(), "text": format_config()})
            return
        if path == "/":
            _json(
                self,
                200,
                {
                    "ok": True,
                    "endpoints": [
                        "GET /health",
                        "GET /status",
                        "GET /config",
                        "POST /start",
                        "POST /stop",
                        "POST /pause",
                        "POST /resume",
                        "POST /restart",
                        "POST /threads  {\"threads\": N}",
                        "POST /puzzle   {\"bits\": 145|150|155|160|140}",
                    ],
                },
            )
            return
        _json(self, 404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not _auth_ok(self):
            self._unauthorized()
            return
        path = urlparse(self.path).path
        body = _read_json(self)
        qs = _query(self)

        if path == "/start":
            _json(self, 200, process.start())
            return
        if path == "/stop":
            _json(self, 200, process.stop(reason="stop"))
            return
        if path == "/pause":
            _json(self, 200, process.pause())
            return
        if path == "/resume":
            _json(self, 200, process.resume())
            return
        if path == "/restart":
            _json(self, 200, process.restart())
            return
        if path == "/threads":
            raw = body.get("threads", qs.get("threads", [None])[0])
            try:
                n = int(raw)
            except (TypeError, ValueError):
                _json(self, 400, {"ok": False, "error": "threads must be an integer"})
                return
            _json(self, 200, process.set_threads(n))
            return
        if path == "/puzzle":
            raw = body.get("bits", body.get("puzzle"))
            if raw is None:
                raw = (qs.get("bits") or qs.get("puzzle") or [None])[0]
            try:
                bits = int(raw)
            except (TypeError, ValueError):
                _json(self, 400, {"ok": False, "error": "bits must be an integer"})
                return
            _json(self, 200, process.set_puzzle(bits))
            return
        _json(self, 404, {"ok": False, "error": "not_found"})


def start_api_thread() -> tuple[ThreadingHTTPServer, threading.Thread]:
    httpd = ThreadingHTTPServer((cfg.api_host, cfg.api_port), Handler)
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, name="api", daemon=True)
    t.start()
    return httpd, t
