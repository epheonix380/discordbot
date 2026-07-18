# STEP 6 — systemd supervision & watchdog

**Status:** ✅ complete · **Date:** 2026-07-18 · **Bot:** running throughout; adoption did not interrupt it

## Goal
Close root cause #1 (**bot did not start on boot**) and root cause #2 (**nothing detects a wedged-but-alive bot**).

## Installed

| Source (version-controlled) | Installed to | Mode |
|---|---|---|
| `deploy/discordbot.service` | `/etc/systemd/system/` | 644 |
| `deploy/discordbot-watchdog.service` | `/etc/systemd/system/` | 644 |
| `deploy/discordbot-watchdog.timer` | `/etc/systemd/system/` | 644 |
| `deploy/discordbot-watchdog.sh` | `/usr/local/bin/` | 755 |

Kept in `deploy/` inside the repo so the supervision config is versioned alongside the app, not just loose in `/etc`.

## `discordbot.service`

`Type=oneshot` + `RemainAfterExit=yes` wrapping `docker compose up -d` / `down`. Ordering:
```
Requires=docker.service                 # never start without the daemon
After=docker.service network-online.target postgresql.service
Wants=postgresql.service                # live data is in HOST postgres
```
`Requires=` (not `Wants=`) on docker, because starting without the daemon is guaranteed failure. Postgres is `Wants=`/`After=` — if it is slow, the bot crash-loops briefly rather than refusing to start, and `restart: always` recovers it.

`ExecStart` carries `--remove-orphans` so a future compose change can never strand an old container running a second bot.

**`systemctl enable`d — this is the actual fix for the original problem.** The previous unit was `active` but `disabled`: it survived crashes and would not have survived a reboot.

## `discordbot-watchdog.{sh,service,timer}`

Timer: `OnBootSec=5min`, `OnUnitActiveSec=2min`.

The script exists because of a specific Docker gap: **`restart: always` does not react to a failing healthcheck.** Docker will leave an `unhealthy` container running indefinitely. So the chain is:

```
main.py writes heartbeat only while gateway is healthy   (Step 3)
   -> compose healthcheck fails when it goes stale >180s (Step 3)
      -> watchdog turns "unhealthy" into an actual restart  (here)
```

Deliberate non-actions in the script — each would cause a restart loop:
- `health=starting` → no action (still inside `start_period`; this bot takes minutes to boot)
- `state != running` → no action, `restart: always` already owns that case
- container absent → no action, `discordbot.service` owns that case
- no healthcheck defined → warn loudly rather than silently doing nothing

On restart it dumps the last healthcheck output to the journal first, so the journal records *why*.

## Verification

| Check | Result |
|---|---|
| `systemctl is-active discordbot` | **active** |
| `systemctl is-enabled discordbot` | **enabled** ← boot survival |
| Container after adoption | `Up 10 minutes (healthy)` — unchanged, `up -d` was correctly a no-op |
| `systemctl is-active discordbot-watchdog.timer` | **active** |
| Timer schedule | next run in ~1m22s, firing on a 2-minute cadence |
| Watchdog runs so far | 4+, all `ExecMainStatus=0`, no spurious restarts against a healthy bot |

That last row matters: the watchdog has now run repeatedly against a healthy container and correctly done **nothing** each time. A watchdog that restarts a healthy service is worse than none.

## Rollback
```bash
systemctl disable --now discordbot.service discordbot-watchdog.timer
rm /etc/systemd/system/discordbot*.{service,timer} /usr/local/bin/discordbot-watchdog.sh
systemctl daemon-reload
```

## Next
Step 7 — prove it. Kill the container and confirm auto-restart; simulate a reboot and confirm auto-start; confirm the watchdog fires on a genuinely stale heartbeat.
