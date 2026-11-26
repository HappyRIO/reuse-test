"""Mutable runtime settings (persisted) + safe caps."""
from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path

from .config import cfg
from .puzzles import get_puzzle, list_puzzles

_lock = threading.RLock()
_RUNTIME_PATH = cfg.state_dir / "runtime.json"
_CONTROL_PATH = cfg.state_dir / "control.json"


def _cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def primary_ip() -> str:
    """Best-effort primary IPv4 (outbound interface)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "unknown"


def max_threads() -> int:
    """Leave at least 1 core free on small boxes when possible."""
    n = _cpu_count()
    return n if n <= 2 else n - 1


def _defaults() -> dict:
    return {
        "instance": str(cfg.instance),
        "mode": str(cfg.mode),
        "file": str(cfg.file),
        "bits": str(cfg.bits),
        "threads": str(cfg.threads),
        "kfactor": str(cfg.kfactor),
        "stats": str(cfg.stats),
        "extra_args": str(cfg.extra_args),
        "automation": bool(cfg.automation),
    }


def _load_json(path: Path, default: dict) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return dict(default)


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _clamp_threads(value: str | int) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 1
    n = max(1, min(n, max_threads()))
    return str(n)


def get_runtime() -> dict:
    with _lock:
        base = _defaults()
        saved = _load_json(_RUNTIME_PATH, {})
        base.update({k: saved[k] for k in base if k in saved})
        base["threads"] = _clamp_threads(base.get("threads", 1))
        return base


def save_runtime(data: dict) -> dict:
    with _lock:
        cur = get_runtime()
        cur.update(data)
        cur["threads"] = _clamp_threads(cur.get("threads", 1))
        _save_json(_RUNTIME_PATH, cur)
        # Keep cfg object in sync for modules that read cfg.*
        cfg.instance = str(cur["instance"])
        cfg.mode = str(cur["mode"])
        cfg.file = str(cur["file"])
        cfg.bits = str(cur["bits"])
        cfg.threads = str(cur["threads"])
        cfg.kfactor = str(cur["kfactor"])
        cfg.stats = str(cur["stats"])
        cfg.extra_args = str(cur["extra_args"])
        cfg.automation = bool(cur["automation"])
        return cur


def get_control() -> dict:
    with _lock:
        return _load_json(
            _CONTROL_PATH,
            {"paused": False, "pause_reason": "", "expect_down": False},
        )


def set_control(**kwargs) -> dict:
    with _lock:
        cur = get_control()
        cur.update(kwargs)
        _save_json(_CONTROL_PATH, cur)
        return cur


def ensure_puzzle_file(bits: int) -> Path:
    info = get_puzzle(bits)
    if not info:
        raise ValueError(f"unsupported puzzle/bits: {bits}. known={list_puzzles()}")
    path = cfg.root / "tests" / f"{bits}.txt"
    path.write_text(info["pubkey"] + "\n", encoding="utf-8")
    return path


def validate_threads(n: int) -> tuple[bool, str]:
    cap = max_threads()
    if n < 1:
        return False, "threads must be >= 1"
    if n > cap:
        return False, f"threads {n} exceeds safe max {cap} (cpus={_cpu_count()})"
    return True, "ok"


def apply_threads(n: int) -> dict:
    ok, msg = validate_threads(n)
    if not ok:
        return {"ok": False, "error": msg, "max_threads": max_threads()}
    rt = save_runtime({"threads": str(n)})
    return {"ok": True, "threads": rt["threads"], "max_threads": max_threads(), "runtime": rt}


def apply_puzzle(bits: int) -> dict:
    path = ensure_puzzle_file(bits)
    info = get_puzzle(bits)
    rt = save_runtime(
        {
            "bits": str(bits),
            "instance": str(bits),
            "file": str(path.relative_to(cfg.root)),
            "mode": "bsgs",
        }
    )
    return {
        "ok": True,
        "bits": bits,
        "file": rt["file"],
        "pubkey": info["pubkey"] if info else None,
        "address": (info or {}).get("address") or None,
        "runtime": rt,
        "known_puzzles": list_puzzles(),
    }


def config_view() -> dict:
    rt = get_runtime()
    ctrl = get_control()
    return {
        "host": os.uname().nodename,
        "ip": primary_ip(),
        "runtime": rt,
        "control": ctrl,
        "limits": {"max_threads": max_threads(), "cpus": _cpu_count()},
        "known_puzzles": list_puzzles(),
        "progress_interval_sec": cfg.progress_interval_sec,
        "api_port": cfg.api_port,
    }


# Initialize puzzle file for current bits + sync cfg from disk overrides
save_runtime(get_runtime())
try:
    ensure_puzzle_file(int(get_runtime()["bits"]))
except Exception:
    pass
