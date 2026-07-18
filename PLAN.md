# PLAN.md — Reliable hosting for `discordbot`

**Author:** Claude (Opus 4.8) · **Started:** 2026-07-18 · **Host:** Ubuntu 24.04, systemd 255, Docker 28.5.2

---

## 1. Findings from the survey (before any changes)

| Thing | State found |
|---|---|
| Working dir | `/root/discordbot`, git repo, on branch `librespot` (tip `941b0e8`, local commits ahead of `origin/librespot`) |
| Upstream latest | **`origin/production` @ `be9c70a`** "Convert project from pipenv to Docker (#25)", dated **2026-07-18** — this is the target |
| Running bot | PID **723591**, `discordBot/bin/python3.13 main.py`, up since **Jun 10 2026** |
| Supervisor | `/etc/systemd/system/discord-bot.service` — **active but `disabled`** |
| Database | Host PostgreSQL on `127.0.0.1:5432`, DB **`discord_bot`** — **live data**: 8168 `storage_memberguildactivity`, 1193 `storage_guildactivity`, 509 `storage_item`, 74 applied migrations |
| Secrets | `.env` (untracked, correct) **and** a stray untracked `compose.yml` with the same secrets **hardcoded in plaintext** |
| Stale docker | Two exited containers `app` / `db` from 8 months ago + volume `discordbot_db-data` (an *unused* second postgres) |

### Root causes of the observed unreliability

1. **`discord-bot.service` is `disabled`.** It restarts the bot on crash (`Restart=always`) but **does not start on boot**. Any reboot = bot stays down until someone notices. This is the single biggest gap.
2. **No liveness check.** `Restart=always` only reacts to process *exit*. A discord.py bot can keep its process alive while its gateway session is wedged — systemd cannot tell the difference.
3. **Unpinned host environment.** Runs from a hand-built `discordBot/` venv on Python 3.13 against `requirements.txt` pinned for a different interpreter than upstream now targets (3.9). Drifts silently.
4. **Two competing deployment definitions** (stray `compose.yml` with its own postgres vs. the systemd unit against host postgres) — ambiguity about which is authoritative, and a real risk of two bots running.

---

## 2. Target architecture

**Docker Compose, owned by a systemd unit, against the existing host PostgreSQL.**

```
systemd: discordbot.service (enabled → survives reboot)
   └── docker compose up  (restart: always → survives crash)
         └── container "discordbot"  (network_mode: host → reaches 127.0.0.1:5432)
               └── entrypoint.sh → manage.py migrate → main.py
   
systemd: discordbot-watchdog.timer (every 2 min)
   └── heartbeat stale > 180s?  → docker compose restart
```

### Why this shape

- **Docker** — matches what upstream `production` now ships (`Dockerfile` + `docker-compose.yml` + `entrypoint.sh`), pins Python 3.9.13 and every dependency, so the runtime stops drifting from the host. Rebuilds are reproducible.
- **`network_mode: host`** — the live data is in **host** postgres at `127.0.0.1:5432`, which only listens on loopback. Host networking lets the container reach it with `DATABASE_URL` unchanged. The bot needs no inbound ports, so this costs nothing in isolation terms. *(Rejected alternatives: rebinding postgres to the docker bridge = widens its exposure; migrating data into a compose-managed postgres = needless risk to live data.)*
- **systemd owning compose** — Docker's own `restart: always` already survives crashes and daemon restarts, but a systemd unit makes boot behaviour explicit and gives one obvious place to start/stop/inspect. Belt and braces.
- **Watchdog on a heartbeat** — closes gap #2, the failure mode `Restart=always` cannot see. Requires a ~6-line addition to `main.py`.
- **Single instance** — guaranteed by a fixed `container_name` (Docker refuses a duplicate name) *plus* retiring the old `discord-bot.service`. **Not** Kubernetes: a single-replica bot on one VM gets none of k8s's benefits and inherits a control plane that is itself a reliability liability.

### Why not Kubernetes (you asked)
k3s would add ~500MB RSS and an etcd/sqlite control plane to run **one** pod that must never have two replicas. Rolling updates — its main draw — are actively harmful here: a rollout briefly runs two bots, which double-handles every Discord event. Compose + systemd is the correct scale.

---

## 3. Steps

Each step gets a `STEP_N.md` written **as it completes**, with what changed, how it was verified, and how to roll back.

| # | Step | Rollback anchor |
|---|---|---|
| 1 | **Back up everything.** `pg_dump` of `discord_bot`, tar of the working tree, record current PID/branch/unit state into `backups/`. | — |
| 2 | **Move to `origin/production`.** Preserve untracked `.env`. Delete the stray secret-bearing `compose.yml`. Keep the old `librespot` work reachable via a tag. | `git checkout librespot` |
| 3 | **Add deployment overlay:** `docker-compose.override.yml` (host networking, `container_name`, log rotation, healthcheck), heartbeat in `main.py`, `.env` left as the single secret source. | delete overlay |
| 4 | **Build the image** and run `manage.py migrate --check` against host postgres to confirm the new code's migrations match the live DB **before** cutting over. | abort, stay on old bot |
| 5 | **Cut over.** Stop + disable + remove old `discord-bot.service`, confirm zero bot processes, then `docker compose up -d`. Only one instance at any moment. | re-enable old unit |
| 6 | **Install `discordbot.service` (enabled)** + `discordbot-watchdog.timer`. Prune the stale 8-month-old containers/volume. | `systemctl disable` |
| 7 | **Verify + reboot test.** Confirm outbound Discord gateway/API traffic, `on_ready` in logs, heartbeat fresh, and that it comes back after a simulated reboot. **Then ping the user to confirm the bot responds in Discord.** | — |

---

## 4. Success criteria

- [ ] Exactly **one** bot process/container running, at all times during and after cutover
- [ ] Established outbound TLS to Discord gateway + `We have logged in as ...` in logs
- [ ] Survives `docker kill` (auto-restart) and `reboot` (auto-start)
- [ ] Watchdog restarts a wedged-but-alive bot
- [ ] Live postgres data intact (row counts match §1), backed up beforehand
- [ ] **User confirms the bot responds in Discord** ← final sign-off

---

## 5. Open items to raise with the user

1. **Secret exposure.** The Discord token, Steam key and Spotify client secret were sitting in plaintext in an untracked `compose.yml`. Not committed to git, so not public — but I'd still **recommend rotating the Discord token**, since a leaked bot token is game over for the bot. Not doing this unprompted; it would require updating `.env` and would briefly disconnect the bot.
2. `origin/production` diverges from the local `librespot` branch, which contains ~9 months of local commits (microservice/librespot work). Step 2 tags them rather than discarding — confirm you don't need them live.
3. `DATABASE_URL`'s password contains a literal `@` (`admin:<DB_PASSWORD>@localhost`). `urlsplit` splits on the *last* `@` so this parses correctly today, but it is fragile. Worth percent-encoding to `%40` at some point.
