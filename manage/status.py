"""Collect finder status from process list + log tail (no heavy deps)."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from . import process
from . import runtime
from .config import cfg

_STAT_RE = re.compile(
    r"Total\s+(\d+)\s+keys in\s+(\d+)\s+seconds:.*?([\d.]+)\s*([KMGTP]?keys/s)",
    re.IGNORECASE,
)


def _tail_text(path: Path, max_bytes: int = 16384) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            data = f.read()
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def parse_speed(log_text: str) -> dict | None:
    matches = list(_STAT_RE.finditer(log_text))
    if not matches:
        return None
    m = matches[-1]
    return {
        "total_keys": int(m.group(1)),
        "elapsed_sec": int(m.group(2)),
        "speed": f"{m.group(3)} {m.group(4)}",
        "raw": m.group(0).strip(),
    }


def rss_kb(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError):
        return None
    return None


def primary_ip() -> str:
    return runtime.primary_ip()


def host_tag() -> str:
    return f"{cfg.instance}@{os.uname().nodename}/{runtime.primary_ip()}"


def collect() -> dict:
    runtime.save_runtime(runtime.get_runtime())  # ensure cfg synced
    pids = process.finder_pids()
    wp = process.wrapper_pid()
    log = process.logfile()
    text = _tail_text(log)
    speed = parse_speed(text)
    ctrl = runtime.get_control()

    found = None
    if cfg.keyfound_path.is_file():
        try:
            found = {
                "path": str(cfg.keyfound_path),
                "mtime": cfg.keyfound_path.stat().st_mtime,
                "preview": cfg.keyfound_path.read_text(encoding="utf-8", errors="replace")[-500:],
            }
        except OSError:
            found = {"path": str(cfg.keyfound_path), "error": "unreadable"}

    mem = None
    if pids:
        rss = rss_kb(pids[0])
        if rss is not None:
            mem = f"{rss / 1024:.1f} MB"

    running = bool(pids) or wp is not None
    ip = primary_ip()
    return {
        "ts": time.time(),
        "host": os.uname().nodename,
        "ip": ip,
        "host_tag": host_tag(),
        "instance": cfg.instance,
        "running": running,
        "paused": bool(ctrl.get("paused")) and not running,
        "automation": bool(wp) or cfg.automation,
        "mode": cfg.mode,
        "bits": cfg.bits,
        "file": cfg.file,
        "threads": cfg.threads,
        "kfactor": cfg.kfactor,
        "extra_args": cfg.extra_args,
        "pids": pids,
        "wrapper_pid": wp,
        "memory": mem,
        "speed": speed,
        "log": str(log),
        "keyfound": found,
        "max_threads": runtime.max_threads(),
    }


def format_status(st: dict | None = None) -> str:
    st = st or collect()
    state = "PAUSED" if st.get("paused") else ("RUNNING" if st["running"] else "STOPPED")
    lines = [
        f"[{st['host_tag']}] {state}",
        f"host: {st['host']}  ip: {st.get('ip', primary_ip())}",
        f"automation: {st['automation']}",
        f"mode: {st['mode']}  bits: {st['bits']}  threads: {st['threads']}/{st['max_threads']}  k: {st['kfactor']}",
        f"args: {st['extra_args']}",
        f"file: {st['file']}",
        f"pids: {st['pids']}  wrapper: {st['wrapper_pid']}",
    ]
    if st.get("memory"):
        lines.append(f"finder RSS: {st['memory']}")
    if st.get("speed"):
        sp = st["speed"]
        lines.append(
            f"speed: {sp['speed']}  total_keys: {sp['total_keys']}  window: {sp['elapsed_sec']}s"
        )
    else:
        lines.append("speed: (waiting for stats)")
    if st.get("keyfound"):
        lines.append("KEY FOUND — see KEYFOUNDKEYFOUND.txt")
    return "\n".join(lines)


def format_config() -> str:
    c = runtime.config_view()
    rt = c["runtime"]
    ip = c.get("ip") or primary_ip()
    lines = [
        f"[{c['host']}/{ip}] config",
        f"host: {c['host']}  ip: {ip}",
        f"bits/instance: {rt['bits']}",
        f"mode: {rt['mode']}  file: {rt['file']}",
        f"threads: {rt['threads']} (max {c['limits']['max_threads']}, cpus {c['limits']['cpus']})",
        f"k: {rt['kfactor']}  args: {rt['extra_args']}",
        f"paused: {c['control'].get('paused')}  reason: {c['control'].get('pause_reason') or '-'}",
        f"known puzzles: {c['known_puzzles']}",
        f"progress every: {c['progress_interval_sec']}s  api: :{c['api_port']}",
    ]
    return "\n".join(lines)
