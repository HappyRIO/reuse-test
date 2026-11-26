# HTTP API

Base URL (default): `http://<host>:8787`  
Config: `API_HOST`, `API_PORT`, `API_TOKEN` in `.env`.

All responses are JSON. Management process is intentionally small (stdlib only).

## Authentication

| Endpoint | Auth |
|---|---|
| `GET /health` | None |
| Everything else | Required |

Send either header:

```http
Authorization: Bearer <API_TOKEN>
```

or:

```http
X-API-Token: <API_TOKEN>
```

Unauthorized → `401`:

```json
{ "ok": false, "error": "unauthorized" }
```

## Endpoints

### `GET /health`

Liveness probe.

```bash
curl -s http://127.0.0.1:8787/health
```

```json
{ "ok": true }
```

---

### `GET /`

Lists endpoints (auth required).

---

### `GET /status`

Live finder status (process, speed, host/IP, puzzle settings).

```bash
curl -s -H "Authorization: Bearer $API_TOKEN" \
  http://127.0.0.1:8787/status
```

```json
{
  "ok": true,
  "status": {
    "host": "srv.example",
    "ip": "1.2.3.4",
    "host_tag": "145@srv.example/1.2.3.4",
    "instance": "145",
    "running": true,
    "paused": false,
    "automation": true,
    "mode": "bsgs",
    "bits": "145",
    "threads": "3",
    "max_threads": 3,
    "speed": { "speed": "9 Pkeys/s", "total_keys": 123, "elapsed_sec": 10 },
    "pids": [12345],
    "memory": "1900.0 MB",
    "keyfound": null
  },
  "text": "[145@srv.example/1.2.3.4] RUNNING\n..."
}
```

`text` is the same human-readable block used in Telegram.

---

### `GET /config`

Persisted runtime config, limits, known puzzles.

```bash
curl -s -H "Authorization: Bearer $API_TOKEN" \
  http://127.0.0.1:8787/config
```

Includes `host`, `ip`, `runtime`, `control` (`paused`, …), `limits.max_threads`, `known_puzzles`, `progress_interval_sec`.

---

### `POST /start`

Start the finder (auto-restart wrapper). No body.

```bash
curl -s -X POST -H "Authorization: Bearer $API_TOKEN" \
  http://127.0.0.1:8787/start
```

| Field | Meaning |
|---|---|
| `started: true` | New process launched |
| `reason: already_running` | No-op |
| `ok: false` | e.g. thread cap / validation error |

Clears pause state.

---

### `POST /stop`

Stop finder + wrapper (intentional stop notification).

```bash
curl -s -X POST -H "Authorization: Bearer $API_TOKEN" \
  http://127.0.0.1:8787/stop
```

---

### `POST /pause`

Same as stop, marked as pause (settings kept; bloom files on disk with `-S`).

```bash
curl -s -X POST -H "Authorization: Bearer $API_TOKEN" \
  http://127.0.0.1:8787/pause
```

---

### `POST /resume`

Clear pause and start.

```bash
curl -s -X POST -H "Authorization: Bearer $API_TOKEN" \
  http://127.0.0.1:8787/resume
```

---

### `POST /restart`

Stop then start.

```bash
curl -s -X POST -H "Authorization: Bearer $API_TOKEN" \
  http://127.0.0.1:8787/restart
```

---

### `POST /threads`

Set thread count. If the finder is running, it **restarts** with the new value.

**Body (JSON):**

```json
{ "threads": 2 }
```

Also accepts query: `POST /threads?threads=2`

```bash
curl -s -X POST -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"threads":2}' \
  http://127.0.0.1:8787/threads
```

Rejected if above safe max (`cpus − 1`, or all cpus if ≤ 2):

```json
{
  "ok": false,
  "error": "threads 99 exceeds safe max 3 (cpus=4)",
  "max_threads": 3
}
```

---

### `POST /puzzle`

Switch puzzle / bit range among known pubkey-exposed targets: **140, 145, 150, 155, 160**.  
Writes `tests/<bits>.txt`, updates runtime, and **restarts** if running.

**Body (JSON):**

```json
{ "bits": 150 }
```

Alias key: `"puzzle"`. Query: `?bits=150`

```bash
curl -s -X POST -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"bits":150}' \
  http://127.0.0.1:8787/puzzle
```

Unknown bits → `ok: false` with `known_puzzles`.

---

## Error shapes

| HTTP | When |
|---|---|
| `401` | Bad/missing token |
| `400` | Invalid JSON fields (e.g. non-integer threads) |
| `404` | Unknown path |
| `200` + `"ok": false` | Business rule failure (thread cap, unknown puzzle) |

---

## Notifications (side effects)

Control actions and watchers may emit Telegram messages (if chats registered):

| Event | When |
|---|---|
| START | Finder becomes running |
| STOP | Intentional stop |
| PAUSE | Pause |
| CRASH | Unexpected exit |
| KEY FOUND | `KEYFOUNDKEYFOUND.txt` updated (highlighted HTML) |
| DAILY STATUS | Every `PROGRESS_INTERVAL_SEC` (default 86400) |

Messages include `instance@hostname/ip`.

---

## Telegram command map

Same controls as the API. Optional target: `here` | `all` | `<HOST_ID>` | `<IP>`.

| Telegram | API |
|---|---|
| `/hosts` | (router peer list) |
| `/status [target]` | `GET /status` |
| `/config [target]` | `GET /config` |
| `/start_hunt [target]` | `POST /start` |
| `/stop_hunt [target]` | `POST /stop` |
| `/pause [target]` | `POST /pause` |
| `/resume [target]` | `POST /resume` |
| `/restart_hunt [target]` | `POST /restart` |
| `/threads N [target]` | `POST /threads` |
| `/puzzle N [target]` | `POST /puzzle` |

Multi-host: only one machine sets `TELEGRAM_LISTEN=1` (router). Peers go in `manage/peers.json` (see `peers.example.json`). SSH `via` is supported when port 8787 is closed.

---

## Security notes

- Treat `API_TOKEN` like a password; rotate if leaked.
- Prefer firewall / SSH tunnel if exposing `API_PORT` beyond localhost.
- `.env` is gitignored; use `.env.example` as the template.
