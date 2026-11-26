"""Start/stop/pause/resume keyhunt via the auto-restart wrapper."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from .config import cfg
from . import runtime
from .puzzles import list_puzzles


def pidfile() -> Path:
    return cfg.log_dir / f"keyhunt-{cfg.instance}.pid"


def logfile() -> Path:
    return cfg.log_dir / f"keyhunt-{cfg.instance}.log"


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def finder_pids() -> list[int]:
    """PIDs of keyhunt binary (not wrapper shells that merely mention it)."""
    pids: list[int] = []
    try:
        out = subprocess.check_output(["pgrep", "-x", "keyhunt"], text=True)
    except subprocess.CalledProcessError:
        return []
    for line in out.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        try:
            exe = Path(f"/proc/{pid}/exe").resolve()
            if exe.name != "keyhunt":
                continue
        except OSError:
            pass
        pids.append(pid)
    return pids


def wrapper_pid() -> int | None:
    pid = _read_pid(pidfile())
    if pid and _alive(pid):
        return pid
    return None


def is_running() -> bool:
    return bool(finder_pids()) or wrapper_pid() is not None


def start(clear_pause: bool = True) -> dict:
    runtime.save_runtime(runtime.get_runtime())  # sync cfg
    if clear_pause:
        runtime.set_control(paused=False, pause_reason="", expect_down=False)

    if is_running():
        return {
            "ok": True,
            "started": False,
            "reason": "already_running",
            "pids": finder_pids(),
            "host": os.uname().nodename,
        }

    ok, msg = runtime.validate_threads(int(cfg.threads))
    if not ok:
        return {"ok": False, "started": False, "error": msg, "host": os.uname().nodename}

    env = os.environ.copy()
    env.update(
        {
            "INSTANCE": cfg.instance,
            "MODE": cfg.mode,
            "FILE": cfg.file,
            "BITS": cfg.bits,
            "THREADS": cfg.threads,
            "KFACTOR": cfg.kfactor,
            "STATS": cfg.stats,
            "EXTRA_ARGS": cfg.extra_args,
            "LOG_DIR": str(cfg.log_dir),
        }
    )
    proc = subprocess.Popen(
        [str(cfg.wrapper)],
        cwd=str(cfg.root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(0.8)
    return {
        "ok": True,
        "started": True,
        "wrapper_spawn": proc.pid,
        "pids": finder_pids(),
        "bits": cfg.bits,
        "threads": cfg.threads,
        "host": os.uname().nodename,
    }


def stop(grace_sec: float = 3.0, *, intentional: bool = True, reason: str = "stop") -> dict:
    if intentional:
        runtime.set_control(expect_down=True, paused=(reason == "pause"), pause_reason=reason)

    killed: list[int] = []
    wp = wrapper_pid()
    targets = set(finder_pids())
    if wp:
        targets.add(wp)

    for pid in sorted(targets):
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except OSError:
            pass

    deadline = time.time() + grace_sec
    while time.time() < deadline and finder_pids():
        time.sleep(0.2)

    for pid in finder_pids():
        try:
            os.kill(pid, signal.SIGKILL)
            if pid not in killed:
                killed.append(pid)
        except OSError:
            pass

    if wp and _alive(wp):
        try:
            os.kill(wp, signal.SIGKILL)
        except OSError:
            pass

    try:
        pidfile().unlink(missing_ok=True)
    except OSError:
        pass

    return {
        "ok": True,
        "stopped": True,
        "killed": killed,
        "running": is_running(),
        "reason": reason,
        "host": os.uname().nodename,
    }


def pause() -> dict:
    return stop(intentional=True, reason="pause")


def resume() -> dict:
    runtime.set_control(paused=False, pause_reason="", expect_down=False)
    return start(clear_pause=True)


def restart() -> dict:
    stop(intentional=True, reason="restart")
    time.sleep(0.5)
    return start(clear_pause=True)


def set_threads(n: int, *, apply_now: bool = True) -> dict:
    res = runtime.apply_threads(n)
    if not res.get("ok"):
        return res
    if apply_now and is_running():
        restart_res = restart()
        res["restarted"] = True
        res["restart"] = restart_res
    else:
        res["restarted"] = False
        res["note"] = "saved; takes effect on next start" if not is_running() else None
    res["host"] = os.uname().nodename
    return res


def set_puzzle(bits: int, *, apply_now: bool = True) -> dict:
    try:
        res = runtime.apply_puzzle(int(bits))
    except ValueError as e:
        return {"ok": False, "error": str(e), "known_puzzles": list_puzzles()}
    if apply_now and is_running():
        restart_res = restart()
        res["restarted"] = True
        res["restart"] = restart_res
    else:
        res["restarted"] = False
        res["note"] = "saved; takes effect on next start" if not is_running() else None
    res["host"] = os.uname().nodename
    return res
