# STEP 4 — Build image & migration dry-run

**Status:** ✅ complete · **Date:** 2026-07-18 · **Bot:** old instance still running — nothing cut over yet

## Goal
Prove the new image works **against the live database** before taking the running bot down. If `production`'s migration set disagreed with the 74 migrations already applied, that had to surface now, not mid-cutover.

## Build

`docker compose build` → `discordbot-bot:latest` (`b02e1cb6ea7c`, **2.35 GB**), exit 0.

Notable: the `git+https://…librespot` requirement built from source successfully (`librespot-0.0.9`), confirming `git` must stay in the image's build deps. Resolved versions match the pins: `django-4.2.9`, `numpy-1.26.3`, `discord.py-2.3.2`, `psycopg2-2.9.9`, on Python 3.9.13.

## Dry-run

All checks run with `docker run --rm --network host --env-file .env` and the entrypoint overridden to `python`, so **Django ran without ever starting the Discord client** — no risk of a second bot connecting while the old one was live.

| Check | Result |
|---|---|
| `manage.py showmigrations` \| count of `[ ]` | **0 unapplied** |
| `manage.py migrate --check` | **exit 0** — nothing pending |
| `connection.settings_dict` | `ENGINE=django.db.backends.postgresql`, `NAME=discord_bot`, `HOST=localhost` |

## What this actually confirms

Four separate risks retired in one go:

1. **Migration compatibility.** `production`'s code matches the schema already in the live DB. The cutover will not attempt a schema change, so `entrypoint.sh`'s `migrate --noinput` will be a no-op. Nothing to roll back.
2. **Host networking reaches postgres.** The container talked to `127.0.0.1:5432` through `--network host`, validating the central design decision from Step 3. Under bridge networking this would have failed.
3. **`DATABASE_URL` parses despite the literal `@` in the password.** `dj_database_url` resolved host `localhost` and database `discord_bot` correctly — `urlsplit` splits on the *last* `@`. The fragility noted in `PLAN.md` §5.3 is real but not currently biting.
4. **No silent sqlite fallback.** This was the one worth checking explicitly. `settings.py` selects postgres purely from `ENVIRONMENT` being present in the env; had `env_file` not loaded, Django would have quietly used the empty bundled `db.sqlite3` and the bot would have come up looking healthy with **no data**. Printing the resolved engine proves `.env` reached the container. The log line `Production` / `ACTIVATION` is `settings.py` confirming the same branch.

An unrelated pre-existing warning (`fields.W161`, fixed default on `Member.lastGymCheckinDate`) appears; it is upstream's, not introduced here, and is not a failure.

## Rollback
Nothing to roll back — no state was modified. The image can be discarded with `docker rmi discordbot-bot:latest`.

## Next
Step 5 — the cutover. Stop and **disable** the old `discord-bot.service`, confirm zero bot processes remain, then bring up the container. This is the only step where a duplicate instance is possible, so ordering is strict: **old fully down and verified, before new comes up.**
