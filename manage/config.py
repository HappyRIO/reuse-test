"""Load lean runtime config from .env (stdlib only)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
STATE_DIR = ROOT / "manage" / "state"
LOG_DIR = ROOT / "logs"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        # Do not override real environment
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(ENV_PATH)


def _get(*keys: str, default: str = "") -> str:
    for k in keys:
        v = os.environ.get(k)
        if v is not None and v != "":
            return v
    return default


class Config:
    root = ROOT
    state_dir = STATE_DIR
    log_dir = LOG_DIR

    # Accept typo TELEGRAM_TOEKN from user .env
    telegram_token = _get("TELEGRAM_TOKEN", "TELEGRAM_TOEKN")
    telegram_username = _get("TELEGRAM_USERNAME")
    telegram_chat_id = _get("TELEGRAM_CHAT_ID")  # filled after /start

    api_token = _get("API_TOKEN")
    api_host = _get("API_HOST", default="0.0.0.0")
    api_port = int(_get("API_PORT", default="8787"))

    progress_interval_sec = int(_get("PROGRESS_INTERVAL_SEC", default="3600"))
    poll_sec = float(_get("POLL_SEC", default="5"))

    instance = _get("INSTANCE", default="145")
    mode = _get("MODE", default="bsgs")
    file = _get("FILE", default="tests/145.txt")
    bits = _get("BITS", default="145")
    threads = _get("THREADS", default="4")
    kfactor = _get("KFACTOR", default="128")
    stats = _get("STATS", default="10")
    extra_args = _get("EXTRA_ARGS", default="-R -q -S")
    automation = _get("AUTOMATION", default="1") not in ("0", "false", "False", "no")

    keyfound_path = ROOT / "KEYFOUNDKEYFOUND.txt"
    wrapper = ROOT / "scripts" / "run-keyhunt.sh"
    binary = ROOT / "keyhunt"


cfg = Config()
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
