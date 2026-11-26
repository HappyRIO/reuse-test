#!/usr/bin/env bash
# One-command install: deps → build → .env → systemd automation → start
# Usage:
#   sudo ./scripts/bootstrap.sh
#   sudo ./scripts/bootstrap.sh --no-hunt
#   sudo ./scripts/bootstrap.sh --bits 150
set -euo pipefail

START_HUNT=1
BITS_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-hunt) START_HUNT=0; shift ;;
    --bits) BITS_OVERRIDE="${2:-}"; shift 2 ;;
    -h|--help)
      echo "Usage: sudo $0 [--no-hunt] [--bits N]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "[bootstrap] root=$ROOT"

# --- deps ---
export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y build-essential python3 curl ca-certificates
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y gcc gcc-c++ make python3 curl ca-certificates
else
  echo "[bootstrap] WARNING: unknown package manager; ensure g++, make, python3 exist"
fi

command -v python3 >/dev/null
command -v g++ >/dev/null
command -v make >/dev/null

# --- build finder ---
if [[ ! -x "$ROOT/keyhunt" ]]; then
  echo "[bootstrap] building keyhunt..."
  make -j"$(nproc 2>/dev/null || echo 2)"
else
  echo "[bootstrap] keyhunt binary present"
fi

# --- .env ---
mkdir -p "$ROOT/logs" "$ROOT/manage/state" "$ROOT/scripts"
chmod +x "$ROOT/scripts/"*.sh 2>/dev/null || true

if [[ ! -f "$ROOT/.env" ]]; then
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "[bootstrap] created .env from .env.example"
  else
    echo "[bootstrap] ERROR: no .env or .env.example" >&2
    exit 1
  fi
fi
chmod 600 "$ROOT/.env"

# helpers to read/write .env keys without exporting secrets to the world
env_get() {
  local key="$1"
  python3 - "$ROOT/.env" "$key" <<'PY'
import sys
path, key = sys.argv[1], sys.argv[2]
val = ""
for raw in open(path, encoding="utf-8", errors="replace"):
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    if k.strip() == key:
        val = v.strip().strip("'").strip('"')
print(val)
PY
}

env_set() {
  local key="$1" val="$2"
  python3 - "$ROOT/.env" "$key" "$val" <<'PY'
import sys
path, key, val = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
out, found = [], False
for line in lines:
    if line.strip().startswith("#") or "=" not in line:
        out.append(line)
        continue
    k, _, _ = line.partition("=")
    if k.strip() == key:
        out.append(f"{key}={val}")
        found = True
    else:
        out.append(line)
if not found:
    out.append(f"{key}={val}")
open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
PY
}

TOKEN="$(env_get TELEGRAM_TOKEN)"
if [[ -z "$TOKEN" ]]; then
  TOKEN="$(env_get TELEGRAM_TOEKN)"
fi
API_TOKEN="$(env_get API_TOKEN)"
if [[ -z "$API_TOKEN" || "$API_TOKEN" == "change-me" ]]; then
  API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  env_set API_TOKEN "$API_TOKEN"
  echo "[bootstrap] generated API_TOKEN"
fi

if [[ -n "$BITS_OVERRIDE" ]]; then
  env_set BITS "$BITS_OVERRIDE"
  env_set INSTANCE "$BITS_OVERRIDE"
  env_set FILE "tests/${BITS_OVERRIDE}.txt"
fi

BITS="$(env_get BITS)"
INSTANCE="$(env_get INSTANCE)"
[[ -z "$INSTANCE" ]] && INSTANCE="$BITS"
[[ -z "$INSTANCE" ]] && INSTANCE=145
API_PORT="$(env_get API_PORT)"
[[ -z "$API_PORT" ]] && API_PORT=8787

PYTHON="$(command -v python3)"

# --- systemd: manage ---
cat > /etc/systemd/system/keyhunt-manage.service <<EOF
[Unit]
Description=keyhunt manage daemon (API + Telegram)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=PYTHONUNBUFFERED=1
ExecStart=$PYTHON -m manage.daemon
Restart=always
RestartSec=3
Nice=15
# Do NOT set MemoryMax here: starting the finder via API would inherit
# the manage cgroup and get OOM-killed while allocating bloom filters.

[Install]
WantedBy=multi-user.target
EOF

# --- systemd: finder template (own cgroup; preferred on small VPS) ---
cat > /etc/systemd/system/keyhunt@.service <<EOF
[Unit]
Description=keyhunt puzzle instance %i (auto-restart)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
EnvironmentFile=-$ROOT/scripts/keyhunt-%i.env
ExecStart=$ROOT/scripts/run-keyhunt.sh
Restart=always
RestartSec=5
Nice=5

[Install]
WantedBy=multi-user.target
EOF

# env file for finder unit (mirrors .env hunt settings)
cat > "$ROOT/scripts/keyhunt-${INSTANCE}.env" <<EOF
INSTANCE=$INSTANCE
MODE=$(env_get MODE)
FILE=$(env_get FILE)
BITS=$(env_get BITS)
THREADS=$(env_get THREADS)
KFACTOR=$(env_get KFACTOR)
STATS=$(env_get STATS)
EXTRA_ARGS=$(env_get EXTRA_ARGS)
LOG_DIR=$ROOT/logs
EOF
chmod 600 "$ROOT/scripts/keyhunt-${INSTANCE}.env"

systemctl daemon-reload
systemctl enable --now keyhunt-manage.service

# wait for API
echo "[bootstrap] waiting for API on :$API_PORT ..."
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    echo "[bootstrap] API up"
    break
  fi
  sleep 0.5
  if [[ "$i" -eq 30 ]]; then
    echo "[bootstrap] WARNING: API not healthy yet; check: journalctl -u keyhunt-manage -e" >&2
  fi
done

if [[ "$START_HUNT" -eq 1 ]]; then
  echo "[bootstrap] starting finder via systemd keyhunt@${INSTANCE} (own memory cgroup)..."
  systemctl enable --now "keyhunt@${INSTANCE}" || \
    echo "[bootstrap] WARNING: failed to start keyhunt@${INSTANCE}" >&2
fi

echo
echo "======== bootstrap complete ========"
echo "path:     $ROOT"
echo "manage:   systemctl status keyhunt-manage"
echo "API:      http://127.0.0.1:${API_PORT}/health"
echo "API auth: Authorization: Bearer <API_TOKEN from .env>"
echo "instance: $INSTANCE"
if [[ -z "$TOKEN" ]]; then
  echo
  echo "ACTION REQUIRED: set TELEGRAM_TOKEN in $ROOT/.env then:"
  echo "  sudo systemctl restart keyhunt-manage"
fi
echo "Telegram: open your bot → send /start → /status"
echo "Docs:     $ROOT/docs/INSTALL.md  $ROOT/docs/API.md"
echo "===================================="
