# STEP 1 — Backups & pre-change snapshot

**Status:** ✅ complete · **Date:** 2026-07-18 · **Destructive changes made:** none

## Goal
Capture a restorable snapshot of the live system *before* any modification, so every later step has a rollback anchor.

## What was created

All under `/root/discordbot/backups/`:

| File | Size | Contents |
|---|---|---|
| `discord_bot_20260718.dump` | 204 KB | `pg_dump -Fc` of the live `discord_bot` database |
| `worktree_20260718.tar.gz` | 125 MB | Full working tree incl. `.git` and `.env`; excludes `.venv/`, `discordBot/`, `temp/`, `db-data/`, `*.mov` |
| `env.backup` | 377 B | Copy of `.env`, mode `600` |
| `state_20260718.txt` | — | Branch/commit, running PID, unit state, full table row counts |

## Verification performed

- `pg_restore -l` on the dump lists **33 `TABLE DATA` entries** → dump is well-formed and readable, not a truncated write.
- Confirmed `./.env` and `./main.py` are present inside the tarball (checked the archive index, not just the exit code).
- The dump succeeded using password `<DB_PASSWORD>`, which incidentally **confirms the `@`-in-password `DATABASE_URL` parses as intended** (see `PLAN.md` §5.3).

## State recorded

- Branch `librespot` @ `941b0e87c0dda3076368659ee30b8143a57d4948`
- Bot PID **723591**, started Wed Jun 10 06:58:13 2026, owned by `discord-bot.service`
- `discord-bot.service`: **active** but **disabled** (the boot-survival gap)
- Row counts: `storage_memberguildactivity` 8168 · `storage_guildactivity` 1193 · `storage_weightedguildactivity` 533 · `storage_item` 509 · `django_migrations` **74**

The `django_migrations` count of **74** is the number to check against in Step 4 — it tells us whether `production`'s migration set matches what the live DB has already applied.

## Rollback from here

```bash
# restore database
PGPASSWORD="$(grep -oP '(?<=://admin:).*?(?=@localhost)' .env)" pg_restore -h 127.0.0.1 -U admin -d discord_bot \
  --clean --if-exists /root/discordbot/backups/discord_bot_20260718.dump

# restore code
tar xzf /root/discordbot/backups/worktree_20260718.tar.gz -C /root/discordbot
```

## Note
`backups/` must be added to `.gitignore` in Step 2 — it contains `env.backup` (plaintext secrets) and a database dump. Neither may ever be committed.

## Next
Step 2 — switch the working tree to `origin/production`, preserving `.env`, and remove the stray secret-bearing `compose.yml`.
