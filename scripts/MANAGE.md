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

## Telegram (multi-host)

Send `/start` once to the **router** host (`TELEGRAM_LISTEN=1`).  
Other hosts use `TELEGRAM_LISTEN=0` (alerts only) + `manage/peers.json` on the router.

| Command | Action |
|---|---|
| `/hosts` | list this host + peers |
| `/status` | **all** instances — **one Telegram message each** |
| `/status here\|vps\|IP` | one instance |
| `/config [target]` | config |
| `/start_hunt` `/resume` `/stop_hunt` `/pause` `/restart_hunt` `[target]` | control |
| `/threads N [target]` | set threads |
| `/puzzle N [target]` | `140`/`145`/`150`/`155`/`160` |

Examples: `/status all` · `/pause vps` · `/threads 1 vps` · `/puzzle 150 13.42.38.253`

Alerts: **START**, **STOP**, **PAUSE**, **CRASH**, highlighted **KEY FOUND**, **DAILY STATUS**.

## Notes

- Pause = stop; resume = start. Bloom files (`-S`) stay on disk.
- Changing threads/puzzle while running restarts the finder.
- Thread cap ≈ `cpus − 1`.
