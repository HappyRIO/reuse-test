#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs manage/state

# Stop previous daemon by PID file only (avoid pkill matching this shell)
PIDFILE=logs/manage.pid
if [[ -f "$PIDFILE" ]]; then
  old=$(cat "$PIDFILE" || true)
  if [[ -n "${old:-}" ]] && kill -0 "$old" 2>/dev/null; then
    kill "$old" 2>/dev/null || true
    sleep 1
    kill -9 "$old" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
fi

nohup python3 -m manage.daemon >> logs/manage.log 2>&1 &
echo $! > "$PIDFILE"
sleep 0.5
echo "started pid=$(cat "$PIDFILE")"
