#!/usr/bin/env python3
"""Lean management daemon: HTTP API + Telegram (stdlib only)."""
from __future__ import annotations

import os
import signal
import sys
import time

from .api import start_api_thread
from .config import cfg
from . import runtime
from .status import collect, format_status, host_tag
from .telegram_bot import TelegramBot, start_bot_thread


def _keyfound_mtime() -> float | None:
    try:
        return cfg.keyfound_path.stat().st_mtime
    except OSError:
        return None


def main() -> int:
    if not cfg.api_token:
        print("API_TOKEN missing in .env", file=sys.stderr)
        return 1
    if not cfg.telegram_token:
        print("[manage] WARNING: TELEGRAM_TOKEN missing — API only until set", flush=True)

    # Ensure runtime + puzzle file ready
    runtime.save_runtime(runtime.get_runtime())
    try:
        runtime.ensure_puzzle_file(int(runtime.get_runtime()["bits"]))
    except Exception as e:  # noqa: BLE001
        print(f"[manage] puzzle file warning: {e}", flush=True)

    bot = TelegramBot()
    httpd, _api_t = start_api_thread()
    if bot.enabled():
        start_bot_thread(bot)

    pid_path = cfg.log_dir / "manage.pid"
    try:
        pid_path.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass

    print(
        f"[manage] API http://{cfg.api_host}:{cfg.api_port}  "
        f"telegram=on  progress={cfg.progress_interval_sec}s  host={host_tag()}",
        flush=True,
    )
    if not bot.chats:
        print("[manage] Send /start to your bot to register for alerts.", flush=True)

    stop = False

    def _sig(_s, _f):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    last_progress = time.time()  # don't spam immediately on boot
    last_found = _keyfound_mtime()
    was_running = collect()["running"]

    while not stop:
        now = time.time()
        st = collect()
        ctrl = runtime.get_control()

        # Key found alert
        mt = _keyfound_mtime()
        if mt is not None and mt != last_found:
            last_found = mt
            try:
                preview = cfg.keyfound_path.read_text(encoding="utf-8", errors="replace")[-800:]
            except OSError:
                preview = "(unreadable)"
            bot.broadcast_keyfound(preview)

        # Running state change → start/stop/crash/pause notifications
        if st["running"] != was_running:
            going_up = st["running"]
            if going_up:
                runtime.set_control(expect_down=False, paused=False, pause_reason="")
                bot.broadcast(f"START\n{format_status(st)}")
            else:
                if ctrl.get("paused") or ctrl.get("pause_reason") == "pause":
                    bot.broadcast(f"PAUSE\n{format_status(st)}")
                elif ctrl.get("expect_down"):
                    bot.broadcast(f"STOP\n{format_status(st)}")
                    runtime.set_control(expect_down=False)
                else:
                    bot.broadcast(f"CRASH / unexpected exit\n{format_status(st)}")
            was_running = going_up

        # Daily progress (or configured interval)
        if (
            bot.chats
            and cfg.progress_interval_sec > 0
            and (now - last_progress) >= cfg.progress_interval_sec
        ):
            last_progress = now
            bot.broadcast(f"DAILY STATUS\n{format_status(st)}")

        time.sleep(cfg.poll_sec)

    httpd.shutdown()
    bot.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
