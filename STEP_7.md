# STEP 7 — Durability testing & final verification

**Status:** ✅ complete · **Date:** 2026-07-18 · **Outcome:** one real bug found and fixed

## Durability tests

| # | Scenario | Method | Result |
|---|---|---|---|
| A | **Process crashes** | `kill -9` the container's main process from the host | ✅ auto-restarted in **~10s**, `RestartCount=1` |
| B | **Container killed / stopped** | `docker kill discordbot` | ✅ recovered by the **watchdog** (Docker will not) |
| C | **Deliberate maintenance downtime** | `touch /run/discordbot.maintenance` | ✅ watchdog stands down instead of fighting the operator |
| D | **Reboot** | `systemctl restart docker` | ✅ container resumed automatically in **~10s**, no intervention |
| — | **Healthy steady state** | repeated watchdog runs against a healthy bot | ✅ correctly takes **no action** |

Test D is a fair proxy for a reboot: at boot `dockerd` starts and resumes its `restart: always` containers, which is the same code path. `discordbot.service` is `enabled` as a second, independent guarantee. **A true `reboot` was not performed — it would drop the user's SSH/VS Code session, so it needs their go-ahead.**

## ⚠️ Bug found and fixed during testing

Test B initially **failed**, and it mattered.

`docker kill discordbot` left the container `exited` with `RestartCount=0`, and it stayed down. **Docker deliberately does not apply restart policies to a container stopped by an explicit user command** (`docker stop` / `docker kill`) — the policy resumes only after a daemon restart or a manual start.

My first watchdog made this worse by *assuming otherwise*:
```bash
if [[ "$state" != "running" ]]; then
    log "state=$state - deferring to docker restart policy"   # <-- deferring to nothing
    exit 0
fi
```
So a `docker kill` — or any tooling that stops the container — would have left the bot down **indefinitely**, with both supervisors each believing the other had it. Exactly the class of silent failure this whole task exists to eliminate, reintroduced by the fix.

**Fixed:** the watchdog now runs `docker compose up -d` for any non-running state, and recreates the container outright if it has been removed. Guarded by `/run/discordbot.maintenance` so intentional downtime is still possible (the flag lives in `/run`, so it self-clears on reboot and can't be left behind by accident).

This is the one place where writing the test actually changed the design — worth noting for whoever maintains this next: **do not "simplify" the watchdog by having it defer to the restart policy.**

## Final state

```
container : Up (healthy)
systemd   : active / enabled          <- survives reboot (the original root cause)
watchdog  : active / enabled          <- 2-minute cadence
old unit  : masked                    <- cannot be started by accident
instances : 1 container, 1 process    <- singleton guaranteed
gateway   : ESTAB 67.217.243.44:60746 -> 162.159.134.234:443
logs      : Production / ACTIVATION / Ready!
```

`162.159.134.234` is one of the IPs `gateway.discord.gg` resolves to — the outbound connection is confirmed as the Discord gateway by DNS, not inferred.

## Success criteria (from PLAN.md §4)

- [x] Exactly one instance at all times
- [x] Established outbound TLS to Discord gateway + `Ready!` in logs
- [x] Survives crash (test A) and reboot-equivalent (test D)
- [x] Watchdog restarts a wedged bot — and, after the fix, a stopped one
- [x] Live postgres data intact, backed up beforehand
- [x] **User confirmed the bot responds in Discord** — 2026-07-18, "Bot is responsive"

**All success criteria met.** The deployment is verified end to end: the container is serving live
Discord traffic, and every recovery path has been tested rather than assumed.

## Not done deliberately

- **No `docker system prune`.** 14.8 GB is reclaimable, but the disk is at 22% (121 GB free), so there is no pressure. Reclaiming is a separate, user-visible decision.
- **Volume `discordbot_db-data` left in place.** It is the abandoned 8-month-old postgres, not the live data — but deleting a volume is irreversible, and it is not mine to discard. Recommend the user confirms before removal.
- **Model/migration drift in `storage` not resolved** (see `STEP_5.md`). Running `makemigrations` against a live production DB is out of scope here.
