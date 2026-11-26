# Install

Lean stack: compile `keyhunt`, configure `.env`, run the manage daemon (API + Telegram).  
No pip packages required (Python 3.10+ stdlib only).

## One command (recommended)

On each instance, from the project root (after copy/clone):

```bash
# 1) put secrets in .env once (or copy .env from a template host)
cp -n .env.example .env
nano .env   # set TELEGRAM_TOKEN at least

# 2) install deps, build, enable automation, start manage + hunt
sudo ./scripts/bootstrap.sh
```

Options:

```bash
sudo ./scripts/bootstrap.sh --no-hunt      # manage/API only
sudo ./scripts/bootstrap.sh --bits 150     # set puzzle then start
```

This installs packages, builds `keyhunt` if needed, generates `API_TOKEN` if missing, installs **systemd** units (`keyhunt-manage` with `Restart=always`), and starts the finder via the API.

Then open Telegram → `/start` → `/status`.

## Requirements

| Item | Notes |
|---|---|
| OS | Linux (x86_64) |
| Build | `g++`, `gcc`, `make` |
| Runtime | `python3` ≥ 3.10 |
| Optional | `systemd` for auto-start on boot |

```bash
# Debian/Ubuntu example
sudo apt update
sudo apt install -y build-essential python3
```

## 1. Get the code

```bash
git clone <YOUR_REPO_URL> keyhunt
cd keyhunt
```

Or copy from an existing host:

```bash
rsync -az --exclude '.git' --exclude 'logs/' --exclude 'manage/state/' \
  --exclude '*.blm' --exclude '*.tbl' --exclude '.env' \
  user@SOURCE:/root/keyhunt/ ./keyhunt/
cd keyhunt
```

## 2. Build the finder

```bash
make -j"$(nproc)"
./keyhunt -h | head
```

Binary path: `./keyhunt` (gitignored; rebuild on each machine).

## 3. Configure environment

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

### Required

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) (`TELEGRAM_TOEKN` typo also accepted) |
| `API_TOKEN` | Secret Bearer token for the HTTP API (use a long random string) |

### Recommended

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_USERNAME` | — | Bot username (informational) |
| `TELEGRAM_CHAT_ID` | — | Optional; auto-filled after you send `/start` to the bot |
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `8787` | API port |
| `PROGRESS_INTERVAL_SEC` | `86400` | Telegram daily status interval (1 day) |
| `INSTANCE` / `BITS` | `145` | Puzzle number |
| `FILE` | `tests/145.txt` | Target pubkey file (auto-written for known puzzles) |
| `MODE` | `bsgs` | Finder mode |
| `THREADS` | `3` | Worker threads (capped to leave CPU free) |
| `KFACTOR` | `128` | BSGS `-k` (RAM tradeoff) |
| `EXTRA_ARGS` | `-R -q -S` | Random + quiet + save bloom |

**Never commit `.env`.** Generate `API_TOKEN` with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 4. Start the manage daemon

```bash
chmod +x scripts/start-manage.sh scripts/run-keyhunt.sh
./scripts/start-manage.sh
curl -s http://127.0.0.1:8787/health
```

### systemd (reboot-safe)

```bash
sudo cp scripts/keyhunt-manage.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now keyhunt-manage
sudo systemctl status keyhunt-manage
```

Service file assumes install path `/root/keyhunt`. Edit `WorkingDirectory` / `ExecStart` if different.

### Optional: auto-restart finder via systemd

```bash
sudo cp scripts/keyhunt@.service /etc/systemd/system/
# ensure scripts/keyhunt-145.env exists (or copy from example)
sudo systemctl daemon-reload
sudo systemctl enable --now keyhunt@145
```

Usually you only need the **manage** service; start/stop the finder via API or Telegram.

## 5. Connect Telegram

1. Open your bot (e.g. `https://t.me/<TELEGRAM_USERNAME>`).
2. Send `/start`.
3. Try `/status` and `/config`.

Commands: see [MANAGE.md](../scripts/MANAGE.md).  
API reference: [API.md](./API.md).

## 6. Start a hunt

Telegram: `/start_hunt`  
or API:

```bash
export API_TOKEN='(from .env)'
curl -s -X POST -H "Authorization: Bearer $API_TOKEN" \
  http://127.0.0.1:8787/start
```

## Multi-host deploy

1. Repeat build + `.env` on each machine (unique `API_TOKEN` recommended).
2. Same Telegram bot is fine; send `/start` once while that host’s manage is running, **or** set the same `TELEGRAM_CHAT_ID` on every host.
3. Reach APIs by `http://<host-ip>:8787` (firewall accordingly).
4. More detail: [DEPLOY.md](../scripts/DEPLOY.md).

## Verify

```bash
curl -s http://127.0.0.1:8787/health
curl -s -H "Authorization: Bearer $API_TOKEN" http://127.0.0.1:8787/status
pgrep -ax keyhunt || true
tail -f logs/manage.log
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `API_TOKEN missing` | Set `API_TOKEN` in `.env`, restart manage |
| Telegram silent | Send `/start` to the bot; check token |
| `threads exceeds safe max` | Lower `THREADS` (cap ≈ CPUs−1) |
| Port in use | Change `API_PORT` or stop old manage (`./scripts/start-manage.sh` restarts it) |
| OOM on BSGS | Lower `-k` / `KFACTOR`, or use fewer threads |
| No speed in status | Finder must be started via wrapper/API so logs go to `logs/keyhunt-*.log` |

## Uninstall / stop

```bash
sudo systemctl disable --now keyhunt-manage 2>/dev/null || true
kill "$(cat logs/manage.pid)" 2>/dev/null || true
curl -s -X POST -H "Authorization: Bearer $API_TOKEN" http://127.0.0.1:8787/stop || true
```
