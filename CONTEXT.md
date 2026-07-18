# CONTEXT.md — session state for resuming this task

**Purpose:** onboard a fresh agent fast. Read `PLAN.md` first, then this, then the highest-numbered `STEP_N.md`.

---

## Where things live

| Item | Path |
|---|---|
| App | `/root/discordbot` (git, remote `epheonix380/discordbot`) |
| Secrets | `/root/discordbot/.env` — **untracked, never commit, single source of truth** |
| Backups | `/root/discordbot/backups/` (pg dump + tree tarball, created in Step 1) |
| Live DB | host PostgreSQL `127.0.0.1:5432`, database **`discord_bot`**, user `admin` |
| Old supervisor | `/etc/systemd/system/discord-bot.service` (hyphen) — being retired |
| New supervisor | `/etc/systemd/system/discordbot.service` + `discordbot-watchdog.{service,timer}` |

## Key facts that are non-obvious

- **Target branch is `production`** (`be9c70a`, 2026-07-18), *not* the checked-out `librespot`. `production` is the Docker conversion.
- The **live data is in host postgres**, not in any Docker volume. The volume `discordbot_db-data` is an abandoned 8-month-old second postgres — **not** the real data. Don't confuse them.
- Because of that, the container uses **`network_mode: host`** to reach `127.0.0.1:5432`. Bridge networking will *not* work — postgres listens on loopback only.
- `backend/settings.py` picks postgres over sqlite purely from **`ENVIRONMENT` being set** in the env (any value ⇒ `DEBUG=False` ⇒ read `DATABASE_URL`). If `ENVIRONMENT` goes missing the bot silently runs on the empty `db.sqlite3` instead — a nasty, quiet failure mode. `.env` sets `ENVIRONMENT=PRODUCTION`.
- Upstream `Dockerfile` pins **Python 3.9.13**; `requirements.txt` is pinned to match (django 4.2.9, numpy 1.26.3, discord.py 2.3.2). The old host venv was 3.13 with different pins. Don't mix them.
- `requirements.txt` installs `librespot` from a git URL, so `git` must stay in the image build deps.
- **Only one bot instance may run.** Discord double-handles events otherwise. Always verify with `ps aux | grep main.py` **and** `docker ps` before starting anything.

## Useful commands

```bash
# state
systemctl status discordbot
docker compose -f /root/discordbot/docker-compose.yml ps
docker logs --tail 50 -f discordbot

# is it actually talking to Discord?
ss -tnp | grep -E 'discordbot|python'          # want ESTAB :443
docker logs discordbot 2>&1 | grep 'logged in as'

# live data sanity
sudo -u postgres psql -d discord_bot -c \
  "select relname,n_live_tup from pg_stat_user_tables order by n_live_tup desc limit 5;"

# restart / rebuild
systemctl restart discordbot
cd /root/discordbot && docker compose build && systemctl restart discordbot
```

## Progress log

| Step | Status | Notes |
|---|---|---|
| 0 — Survey & plan | ✅ done | `PLAN.md`, `CONTEXT.md` written |
| 1 — Backups | ✅ done | `backups/` — pg dump (33 tables), worktree tarball, `.env` copy |
| 2 — Move to `production` | ✅ done | now on `be9c70a`; old work at tag `pre-migration-librespot-20260718` |
| 3 — Deployment overlay + heartbeat | ✅ done | `docker-compose.yml` rewritten, heartbeat added to `main.py` |
| 4 — Build & migration dry-run | ✅ done | image `discordbot-bot` 2.35GB; 0 pending migrations; postgres confirmed |
| 5 — Cutover | ✅ done | old unit stopped/disabled/**masked**; container live, single instance |
| 6 — systemd + watchdog | ✅ done | `discordbot.service` **enabled**; watchdog timer every 2 min |
| 7 — Verify & durability tests | ✅ done | crash/kill/maintenance/daemon-restart all pass; **1 bug found & fixed** |
| 8 — User sign-off | ✅ **done** | **2026-07-18: user confirmed "Bot is responsive" in Discord** |

## CURRENT STATE (as of 2026-07-18 ~16:45 UTC)

**The bot is live, healthy, and connected to the Discord gateway.** Single instance.

```
systemctl is-active discordbot   -> active
systemctl is-enabled discordbot  -> enabled     # survives reboot (was the root cause)
discord-bot.service (old)        -> masked      # cannot be started by accident
```

### ⚠️ Maintainer warning
**Do not "simplify" `deploy/discordbot-watchdog.sh` to defer to Docker's restart policy when the
container is not running.** Docker does *not* apply restart policies to a container stopped by
`docker stop`/`docker kill` — it stays exited forever. An earlier version of the watchdog assumed
it did, and left the bot down indefinitely. Found by test B in `STEP_7.md`. The watchdog must
actively `docker compose up -d`.

To take the bot down on purpose: `touch /run/discordbot.maintenance` (self-clears on reboot).

### Files created so far
- `deploy/discordbot.service` — compose lifecycle, enabled at boot (**installs to `/etc/systemd/system/`**)
- `deploy/discordbot-watchdog.{sh,service,timer}` — restarts on stale heartbeat (**script installs to `/usr/local/bin/`**)
- `docker-compose.yml` — rewritten; see `STEP_3.md` for each deviation from upstream and why

## Decisions already made (don't relitigate)

- Compose + systemd, **not** Kubernetes — rationale in `PLAN.md` §2.
- Keep host postgres; do **not** migrate data into a container.
- Old `librespot` commits get tagged, not deleted.

## Awaiting user

- Recommendation to **rotate the Discord token** (was in plaintext in a stray `compose.yml`). Not actioned unprompted.
- Final sign-off: user must confirm the bot responds in Discord.
