# STEP 5 — Cutover to the container

**Status:** ✅ complete · **Date:** 2026-07-18 · ⚠️ The only step with a duplicate-instance risk. Ordering was strict.

## Goal
Replace the venv/systemd bot with the container, without ever having two bots connected to Discord at once.

## Sequence (old fully down and *verified* before new came up)

### 1. Old instance retired
```
systemctl stop discord-bot.service      -> inactive
systemctl disable discord-bot.service   -> disabled
ps aux | grep main.py                   -> NONE   <- verified empty before proceeding
```
Then the unit file itself was retired, not just disabled:
```
cp /etc/systemd/system/discord-bot.service backups/discord-bot.service.retired
rm /etc/systemd/system/discord-bot.service
systemctl daemon-reload && systemctl mask discord-bot.service
```
**Why mask and not just disable:** a disabled unit can still be started by hand or pulled in as a dependency, which would launch a *second* bot against the same token. Masking symlinks it to `/dev/null` so `systemctl start discord-bot` now fails outright. The original is preserved in `backups/` for rollback.

*(Note: `mask` initially failed because the real unit file was still in place — masking cannot shadow an existing file in `/etc/systemd/system`. Removing the file first, then masking, is the correct order.)*

### 2. New instance up
```
docker compose up -d --remove-orphans
```
`--remove-orphans` also swept away the abandoned 8-month-old `app` and `db` containers from the stray `compose.yml` — folding the Step 6 prune in here. That is a genuine safety win: the orphaned `app` container was a second bot definition sitting one `docker start` away from running.

## Verification

| Check | Result |
|---|---|
| `Ready!` in logs | ✅ — `on_ready` fired **and** `tree.sync()` completed, both of which require Discord API round-trips |
| Migrations at startup | `No migrations to apply.` — exactly as Step 4 predicted |
| **Outbound gateway** | `ESTAB 67.217.243.44:36118 -> 162.159.130.234:443` |
| **Peer is Discord** | `getent hosts gateway.discord.gg` returns `162.159.130.234` among its IPs — the peer is verified as the Discord gateway by DNS, not assumed from the address block |
| Heartbeat | `/tmp/discordbot-heartbeat`, age **1s** |
| Healthcheck | `docker inspect` → **`healthy`** (the Step 3 mechanism proven end to end, not just syntactically valid) |
| **Single instance** | 1 container · 1 `main.py` process on the host · that process is the container's own PID |

## Known non-blocking issue

Startup logs an upstream model/migration drift:
> `Your models in app(s): 'storage' have changes that are not yet reflected in a migration`

This is **pre-existing upstream drift** — `models.py` has edits nobody generated a migration for. It is harmless right now (no schema change is attempted, and the app runs against the existing schema), but it means `makemigrations` on a future change will produce a migration bundling those stale edits too. Flagged for the user; **not** fixed here, since generating a migration against a live production database is well outside "make the hosting reliable".

## Rollback
```bash
docker compose down
systemctl unmask discord-bot.service
cp backups/discord-bot.service.retired /etc/systemd/system/discord-bot.service
systemctl daemon-reload && systemctl start discord-bot
```

## Next
Step 6 — install `discordbot.service` **enabled** (the boot-survival gap, root cause #1) and the watchdog timer.
