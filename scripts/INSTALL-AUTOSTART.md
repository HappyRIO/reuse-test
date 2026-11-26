# Auto-start keyhunt on several machines

## Option A — systemd (best)

On each machine:

```bash
sudo cp /root/keyhunt/scripts/keyhunt@.service /etc/systemd/system/
sudo cp /root/keyhunt/scripts/keyhunt-145.env /root/keyhunt/scripts/
sudo systemctl daemon-reload
sudo systemctl enable --now keyhunt@145
```

Useful commands:

```bash
systemctl status keyhunt@145
journalctl -u keyhunt@145 -f
tail -f /root/keyhunt/logs/keyhunt-145.log
sudo systemctl stop keyhunt@145
```

More instances: copy `keyhunt-145.env` → `keyhunt-140.env`, edit values, then:
`sudo systemctl enable --now keyhunt@140`

## Option B — no systemd (loop only)

```bash
nohup /root/keyhunt/scripts/run-keyhunt.sh >/dev/null 2>&1 &
```

Add reboot survival with cron:

```bash
(crontab -l 2>/dev/null; echo '@reboot /root/keyhunt/scripts/run-keyhunt.sh') | crontab -
```

## Notes

- Same puzzle on many machines is fine with `-R` (random).
- Do not run several heavy BSGS instances on one 4GB box (RAM).
- Bloom files (`keyhunt_bsgs_*.blm`) are reused if `-S` is set.
