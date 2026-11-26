# Deploy to another instance

Primary install guide: [docs/INSTALL.md](../docs/INSTALL.md) · API: [docs/API.md](../docs/API.md)

## 1. Copy project

```bash
# from this machine (example)
rsync -az --exclude '.git' --exclude 'logs/' --exclude 'manage/state/' --exclude '*.blm' --exclude '*.tbl' \
  /root/keyhunt/ user@OTHER:/root/keyhunt/
```

Or `git clone` your repo if you push it.

## 2. On the new host (one command)

```bash
cd /root/keyhunt   # or wherever you synced
cp -n .env.example .env
nano .env          # set TELEGRAM_TOKEN (API_TOKEN auto-generated if empty)
sudo ./scripts/bootstrap.sh
# sudo ./scripts/bootstrap.sh --bits 145
# sudo ./scripts/bootstrap.sh --no-hunt
```

Required: `TELEGRAM_TOKEN` (or `TELEGRAM_TOEKN`). `API_TOKEN` is created if missing.

Use a **different `API_PORT`** per host if you reverse-proxy many boxes, or keep `8787` and reach each by IP.

## 3. Register Telegram on that host

Open the bot → `/start` once **from each machine’s bot session** (same bot is fine; each daemon stores chat ids locally after you message it).  
If one shared bot: message `/start` while that host’s manage is running, or set `TELEGRAM_CHAT_ID=` in `.env` to your numeric chat id on every host.

## Checklist

- [ ] `keyhunt` binary present
- [ ] `.env` with tokens (do not commit)
- [ ] `python3 -m manage.daemon` / `start-manage.sh` running
- [ ] `/health` returns ok
- [ ] Telegram `/status` shows correct `instance@host/ip`
