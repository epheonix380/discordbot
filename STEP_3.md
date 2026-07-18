# STEP 3 — Deployment overlay: networking, singleton, liveness

**Status:** ✅ complete · **Date:** 2026-07-18 · **Bot:** old instance still running, untouched

## Goal
Make the upstream Docker definition actually correct for *this* host, and add a liveness signal that can detect the failure mode `restart: always` is blind to.

## Change 1 — `main.py`: heartbeat (+18 lines)

```python
HEARTBEAT_FILE = os.getenv("HEARTBEAT_FILE", "/tmp/discordbot-heartbeat")

async def heartbeat():
    while True:
        if client.is_ready() and not client.is_closed() and client.latency < 5:
            try:
                with open(HEARTBEAT_FILE, "w") as f:
                    f.write(str(time.time()))
            except OSError as e:
                print(f"Could not write heartbeat: {e}")
        await asyncio.sleep(30)
```
…plus `loop.create_task(heartbeat())` beside the existing `client.start(TOKEN)` task.

**Why this and not just `Restart=always`:** systemd/Docker restart policies only fire when the process *exits*. A discord.py bot can sit with a live process and a dead gateway session indefinitely — the exact "unreliable but not obviously down" symptom. The file is only rewritten when the gateway is genuinely healthy, so **staleness is the signal**.

The `client.latency < 5` test also handles the not-yet-ready case for free: `latency` is `NaN` until the first gateway heartbeat, and every comparison against `NaN` is `False`. Noted in a comment, since that is not obvious.

## Change 2 — `docker-compose.yml` rewritten

Upstream's version was written for a generic host and is wrong here in three ways.

| Upstream | Changed to | Why |
|---|---|---|
| *(default bridge networking)* | `network_mode: host` | The live data is in the **host** postgres on `127.0.0.1:5432`, which **listens on loopback only**. From a bridge network the container simply cannot reach it — the bot would fall back to nothing and fail on every DB call. The bot serves no inbound ports, so host networking gives up no isolation that matters. |
| `volumes: - storage:/app/storage` | **removed** | ⚠️ Real bug. `storage/` is **Django application code** — `models.py`, `serializers.py`, `migrations/`, and it is listed in `INSTALLED_APPS`. A named volume there is populated from the image once, then **never updated**. Every subsequent `docker compose build` would ship new code that the container silently ignores, running stale models and migrations. Precisely the kind of quiet drift that makes a deployment "unreliable". |
| `volumes: - ./db.sqlite3:/app/db.sqlite3` | **removed** | `.env` sets `ENVIRONMENT`, so `settings.py` takes the `DATABASE_URL`/postgres path. The sqlite file is dead weight in production, and keeping it mounted invites a silent fallback onto an empty database. |
| `restart: unless-stopped` | `restart: always` | `unless-stopped` does **not** restart a container that was stopped manually, even across a daemon restart or reboot. `always` does. For a bot that must simply always be up, `always` is the correct policy. |
| *(no name)* | `container_name: discordbot` | **Enforces the singleton.** Docker refuses to start a second container with the same name, so an accidental `docker compose up` in another shell fails loudly instead of quietly double-handling every Discord event. |
| *(unbounded logs)* | `max-size: 10m, max-file: 5` | The default json-file driver grows forever; an 8-month-old container had been logging unbounded. Caps at 50 MB. |
| *(none)* | `healthcheck` on heartbeat staleness (>180s) | Consumes Change 1. `start_period: 300s` covers the genuinely slow first boot — migrations plus the keras/onnxruntime imports in `automod/nsfw.py`. |

## Verification

- `docker compose config` → **valid**, and confirms `.env` is being read: `DATABASE_URL`, `ENVIRONMENT=PRODUCTION`, `TOKEN` all resolve. Secrets stay in `.env`; none are inlined in the compose file.
- `ast.parse(main.py)` → syntax OK, heartbeat task confirmed wired in. (An unrelated pre-existing `SyntaxWarning: invalid escape sequence '\:'` at line 64 was already there; not introduced here.)
- Healthcheck is not yet proven to *pass* — that needs a running container, and is verified in Step 5.

## Rollback
```bash
git checkout docker-compose.yml main.py
```

## Next
Step 4 — build the image and dry-run `manage.py migrate` against the live postgres to confirm `production`'s migration set matches the 74 already applied, **before** cutting over.
