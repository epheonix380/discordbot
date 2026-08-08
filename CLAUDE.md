# CLAUDE.md — operating guide for this Discord bot

Read this first. It is the durable "how this thing runs and how it breaks" guide.
For the deployment-migration backstory see `CONTEXT.md`; this file is about
keeping the bot **alive and healthy** day to day.

---

## 1. What it is

A single-instance Discord bot (`main.py`, discord.py 2.3.2) that also embeds a
**Django 4.2.9** app (`backend/`, `storage/`) for its database models. It runs in
Docker via `docker-compose.yml`, supervised by systemd + a watchdog.

- **One instance only.** Two instances double-handle every Discord event. The
  fixed `container_name: discordbot` makes Docker refuse a duplicate. Always
  check `docker ps` before starting anything.
- **Live data is in the HOST Postgres** at `127.0.0.1:5432`, db `discord_bot`,
  user `admin`. NOT in a Docker volume. That is why the container runs
  `network_mode: host` (loopback-only Postgres is unreachable from a bridge net).
- Postgres vs sqlite is chosen purely by `ENVIRONMENT` being set in `.env`
  (`ENVIRONMENT=PRODUCTION`). If it goes missing the bot silently runs on an
  empty `db.sqlite3` — a quiet, nasty failure.

## 2. How it's supervised (three layers)

| Layer | File | Job |
|---|---|---|
| systemd unit | `/etc/systemd/system/discordbot.service` | `docker compose up -d` at boot; enabled |
| Docker | `restart: always` in `docker-compose.yml` | restart the container if the **process exits** |
| Watchdog | `/usr/local/bin/discordbot-watchdog.sh` + `.timer` (every 2 min) | restart if the container is **alive but wedged** |

The watchdog exists because `restart: always` only reacts to the process
*exiting*. It does **not** react to a failing healthcheck, nor to a container
stopped by `docker stop`/`docker kill`. The watchdog turns those into an actual
`docker compose up -d`. **Do not "simplify" it to trust Docker's restart policy.**

The healthcheck (in compose) watches a **heartbeat file** `/tmp/discordbot-heartbeat`
that `main.py` rewrites every 30s *only while the Discord gateway is healthy*.
Stale heartbeat ⇒ unhealthy ⇒ watchdog restarts.

To take the bot down on purpose: `touch /run/discordbot.maintenance` (self-clears
on reboot); the watchdog stands down while it exists.

## 3. THE OUTAGE THIS FILE WAS BORN FROM (2026-07-23 → 07-25) — and the guardrails

**Symptom:** bot "down" for ~2 days but the container reported **healthy** and the
watchdog never fired.

**Root cause:** The host Postgres restarted. The bot is one long-running process
with **no HTTP request cycle**, so Django never ran its normal "reap dead DB
connections" hooks. The dead connection stayed cached and **every** query raised
`psycopg2.InterfaceError: connection already closed` — forever. Meanwhile the
Discord gateway stayed connected, so the heartbeat kept refreshing and everything
*looked* healthy. The bot was up but couldn't touch the database, i.e. functionally
dead. The gateway-only healthcheck was blind to it.

**The fix (self-healing DB):**
- `helpers/db.py` — a drop-in `sync_to_async` replacement that calls
  `django.db.close_old_connections()` immediately before and after each DB
  helper, in the ORM worker thread. A dead/obsolete connection is dropped and
  Django reconnects on the next query. **All DB helpers import `sync_to_async`
  from `helpers.db`, not from `asgiref.sync`.** Keep it that way.
- `backend/settings.py` — `conn_max_age=0, conn_health_checks=True`. No
  persistent connections; each unit of DB work gets a fresh, verified one.
- Verified by killing the bot's Postgres backend with `pg_terminate_backend` and
  confirming the next query self-heals instead of throwing.

A future Postgres restart now recovers on the next query — **no bot restart
needed**. That is also why the healthcheck is intentionally left as gateway-only:
the DB layer heals itself; the heartbeat guards the gateway.

## 4. Logging (added 2026-07-25) — `helpers/observability.py`

There was **no logging** before. Now:
- `setup_logging()` (called first thing in `main.py`'s `__main__`) sends the
  bot's own output, discord.py, apscheduler tracebacks, **and bare `print()`**
  (stdout/stderr are redirected into the logger) to a rotating file, while still
  echoing to real stdout so `docker logs discordbot` keeps working.
- Log file: **`/app/logs/bot.log`**, bind-mounted to **`/root/discordbot/logs/`**
  on the host. Rotated every 10 min, `backupCount` sized to keep **~30 minutes**;
  older rotations auto-deleted.

Inspect logs: `tail -f /root/discordbot/logs/bot.log` (host) or `docker logs -f discordbot`.

## 5. Disk hygiene — `cleanup_old_files()`

The bot writes generated images (`SPOILER_*.png`, `<id>.png`, previews, gifs)
into its working dir for every NSFW/preview check and **never cleaned them up**
(9 had accumulated). A scheduler job (`cleanup_job` in `main.py`, every 5 min,
first run ~30s after boot) deletes:
- images (`.png .jpg .jpeg .gif .mov .mp4 .webp`) in `/app` older than 30 min, and
- rotated log files older than 30 min (belt-and-suspenders to the handler).

All windows/paths are env-tunable: `FILE_MAX_AGE_MIN` (default 30), `LOG_DIR`,
`IMAGE_DIR`, `LOG_ROTATE_MIN`. The cleanup never raises — hygiene must not take
the bot down.

## 6. Everyday commands

```bash
# state
systemctl status discordbot
docker ps                                  # want: Up ... (healthy), name discordbot
docker inspect -f '{{.State.Health.Status}}' discordbot

# logs
tail -f /root/discordbot/logs/bot.log
docker logs --tail 80 -f discordbot

# is the DB actually working? (this was the silent failure)
docker logs discordbot 2>&1 | grep -c "connection already closed"   # want 0

# heartbeat freshness (seconds; healthy < 180)
docker exec discordbot sh -c 'echo $(( $(date +%s) - $(cut -d. -f1 /tmp/discordbot-heartbeat) ))'

# rebuild after a code change, then recreate
cd /root/discordbot && docker compose build && docker compose up -d

# planned downtime
touch /run/discordbot.maintenance        # stop watchdog fighting you
docker compose down
```

## 7. Health-check triage (when someone says "bot is down")

1. `docker ps` — is `discordbot` running & `healthy`?
2. `docker logs discordbot 2>&1 | grep -c "connection already closed"` — if >0 and
   climbing, the DB self-heal isn't kicking in; check `helpers/db.py` imports and
   that Postgres is up (`systemctl status postgresql`).
3. Heartbeat age (cmd above) — if stale, the gateway is wedged; the watchdog
   should restart within 2 min, or `docker compose restart`.
4. `tail /root/discordbot/logs/bot.log` — the last 30 min of everything.

## 8. Rules / don't-relitigate

- DB helpers import `sync_to_async` from **`helpers.db`** (resilient), never
  `asgiref.sync` directly.
- Do not add persistent DB connections (`conn_max_age>0`) without also keeping
  the `close_old_connections()` wrapper — that combination is what caused the
  outage.
- Do not weaken the watchdog to trust Docker's restart policy for stopped
  containers.
- One instance only. Host Postgres stays; don't migrate data into a container.
- `logs/` and generated media are runtime-only and git-ignored.
