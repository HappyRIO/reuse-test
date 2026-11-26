#!/usr/bin/env bash
# Auto-restart wrapper for keyhunt (survives crashes; pair with systemd/@reboot for reboots)
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Override via env or edit defaults below
MODE="${MODE:-bsgs}"
FILE="${FILE:-tests/145.txt}"
BITS="${BITS:-145}"
THREADS="${THREADS:-4}"
KFACTOR="${KFACTOR:-128}"
STATS="${STATS:-10}"
EXTRA_ARGS="${EXTRA_ARGS:--R -q -S}"
LOG_DIR="${LOG_DIR:-$ROOT/logs}"
INSTANCE="${INSTANCE:-145}"
SLEEP_SEC="${SLEEP_SEC:-5}"

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/keyhunt-${INSTANCE}.log"
PIDFILE="$LOG_DIR/keyhunt-${INSTANCE}.pid"

echo $$ > "$PIDFILE"

while true; do
  echo "[$(date -Is)] starting keyhunt instance=${INSTANCE} mode=${MODE} bits=${BITS}" | tee -a "$LOG"
  # shellcheck disable=SC2086
  ./keyhunt -m "$MODE" -f "$FILE" -b "$BITS" -k "$KFACTOR" -t "$THREADS" -s "$STATS" $EXTRA_ARGS \
    >>"$LOG" 2>&1
  code=$?
  echo "[$(date -Is)] exited code=${code}; restarting in ${SLEEP_SEC}s" | tee -a "$LOG"
  sleep "$SLEEP_SEC"
done
