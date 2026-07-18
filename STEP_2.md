# STEP 2 — Switch working tree to `origin/production`

**Status:** ✅ complete · **Date:** 2026-07-18 · **Bot:** still running throughout (old PID 723591 untouched)

## Goal
Move the working tree to the latest upstream code without losing local work, secrets, or the running bot.

## Actions

### 1. Tagged the local branches before leaving them
The `librespot` branch had ~9 months of local commits (microservice / librespot work) that existed **only on this VM** — `origin/librespot` was 3 commits behind local `HEAD`. Tagged rather than risked:

```
pre-migration-librespot-20260718         -> 941b0e8 "added vps support"
pre-migration-headless-spotify-20260718
```

Recover any of it later with `git checkout pre-migration-librespot-20260718`.

### 2. Deleted the stray `compose.yml`
Untracked, and contained the **Discord token, Steam key and Spotify client secret in plaintext**. It also defined a *second* PostgreSQL that is not the live database — leaving it in place invited someone to `docker compose up` it and start a duplicate bot against an empty DB. A copy survives inside `backups/worktree_20260718.tar.gz`.

The upstream `docker-compose.yml` (which arrived with this checkout) correctly uses `env_file: .env` instead of inlining secrets.

### 3. Fast-forwarded to `production`
```
9b1c2d6 -> be9c70a  "Convert project from pipenv to Docker (#25)"
16 files changed, 242 insertions(+), 1782 deletions(-)
```
Notable: `Pipfile`/`Pipfile.lock`/`Procfile`/`runtime.txt` deleted; `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`, `.dockerignore` added; `requirements.txt` rewritten (117 lines changed); new `commands/automagic.py`.

### 4. Hardened `.gitignore`
It previously ignored `.env` but **not** `backups/`, `__pycache__/`, `.venv/`, `discordBot/` or `*.dump`. Appended those. This matters immediately — `backups/env.backup` and the DB dump created in Step 1 were otherwise one `git add -A` away from being committed.

## Verification

- `git log` → `be9c70a`, matches `origin/production`.
- `.env` **still present and untouched** (`377 B`, Aug 18 2025) — it is untracked, so the branch switch left it alone. This is the single source of secrets.
- **Bot PID 723591 still alive** after the checkout. Files changed underneath a running Python process are not re-read once imported; the risk was a lazy import failing, and it did not materialise.
- `git status` is clean apart from the intended `.gitignore` edit and the untracked planning docs.

## Rollback
```bash
git checkout pre-migration-librespot-20260718
tar xzf backups/worktree_20260718.tar.gz -C /root/discordbot   # if .env or compose.yml needed back
```

## Next
Step 3 — add the deployment overlay: host networking so the container reaches the live postgres on `127.0.0.1:5432`, a fixed container name to enforce single-instance, log rotation, and a heartbeat for the watchdog.
