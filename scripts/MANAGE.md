# Manage daemon (quick reference)

Full guides:

- **Install:** [docs/INSTALL.md](../docs/INSTALL.md)
- **API:** [docs/API.md](../docs/API.md)
- **Multi-host:** [DEPLOY.md](./DEPLOY.md)

## One-command install (new host)

```bash
sudo ./scripts/bootstrap.sh
```

See [docs/INSTALL.md](../docs/INSTALL.md).

## Start (already installed)

```bash
./scripts/start-manage.sh
# or: sudo systemctl enable --now keyhunt-manage
```

## Telegram

Send `/start` to the bot once.

| Command | Action |
|---|---|
| `/status` | running status (host + IP) |
| `/config` | config + limits |
| `/start_hunt` / `/resume` | start / resume |
| `/stop_hunt` | stop |
| `/pause` | pause |
| `/restart_hunt` | restart |
| `/threads N` | set threads (capped) |
| `/puzzle N` | `140` / `145` / `150` / `155` / `160` |

Alerts: **START**, **STOP**, **PAUSE**, **CRASH**, highlighted **KEY FOUND**, **DAILY STATUS** (default every 1 day).

## Notes

- Pause = stop; resume = start. Bloom files (`-S`) stay on disk.
- Changing threads/puzzle while running restarts the finder.
- Thread cap ≈ `cpus − 1`.
