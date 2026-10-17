# Weekly DB backups to Google Drive — design (draft)

Status: **design, decisions agreed**. Nothing implemented yet. Drive API
credentials are not set up; the Drive-specific parts below are the planned
shape and will be confirmed once they are.

## 0. Decisions so far

| Question | Decision |
|---|---|
| Google account | **Personal** Gmail, so OAuth user credentials, not a service account (§5) |
| Encryption | **None.** The backup holds no PII, *provided* secrets are excluded (§3) |
| Secrets | **Never backed up.** Spotify auth tokens and other credentials are left out of the dump (§3) |
| Schedule | Weekly, **Sunday 04:00 UTC** |
| Discord notifications | **Both** success and failure |
| Local copy | **Yes.** Keep the newest dump on the host too |
| DB size | Unknown. Measure before go-live: `sudo -u postgres psql -d discord_bot -c "SELECT pg_size_pretty(pg_database_size('discord_bot'));"` |

## 1. Requirements

| # | Requirement |
|---|---|
| R1 | Back up the live database (host Postgres `127.0.0.1:5432`, db `discord_bot`) every 7 days. |
| R2 | Upload each backup to one dedicated folder on Google Drive. |
| R3 | Keep only the 5 most recent backups in that folder. Uploading the 6th deletes the oldest. |
| R4 | A failed run must never cost us a good backup, and must not go unnoticed. |
| R5 | Backups must not affect the running bot (see `CLAUDE.md`: one instance, gateway heartbeat, self-healing DB). |
| R6 | Only non-sensitive user and server data is backed up. Credentials and auth tokens never leave the host. |

5 weekly backups give ~5 weeks of history.

## 2. Where it runs: on the host, not in the bot

The backup runs as a **host-side systemd timer + oneshot service**, the same way
`deploy/discordbot-watchdog.*` and `deploy/discordbot-monitor.*` already do. It
does **not** run as an APScheduler job inside `main.py`.

Why:

- **APScheduler `interval` jobs restart their clock when the process does.**
  `scheduler.add_job(..., 'interval', days=7)` counts 7 days from bot start. The
  watchdog restarts the container on any wedge, and any restart pushes the next
  backup out another 7 days. A bot that restarts at least once a week would never
  back up. A systemd timer with `Persistent=true` runs on the calendar, and if
  the host was off at that time it catches up at the next boot.
- **The backup has to work when the bot is down.** If the container is crash-
  looping, that's when we most want a backup to exist. The monitor runs on the
  host for the same reason.
- **`pg_dump` version match.** `pg_dump` must be at least as new as the server.
  The bot image is `python:3.9.13-slim` (bullseye, ships `pg_dump` 13). The host's
  own `pg_dump` comes from the same install as the server, so it always matches.
- **Keeps the bot image and its dependencies unchanged.** Google client
  libraries go into a separate venv on the host, not into `requirements.txt`.
- A dump of a big table plus an upload would block or slow the bot's event loop
  and DB connections. Running it outside the container avoids that.

## 3. What gets backed up (R6)

### Excluded: table data that holds secrets

`pg_dump` can leave out a whole table's **rows** while still dumping its
**structure** (`--exclude-table-data`). It cannot leave out a single column. So
any table that holds a secret has all of its rows left out. A restored database
still has these tables, just empty.

| Table | Why excluded | Effect after a restore |
|---|---|---|
| `storage_spotifylink` | `credentials` is each member's Spotify OAuth token blob (`helpers/spotifyStore.py`, `music/credentials.py`) | Members run `,spotify` again to re-link |
| `auth_user` | Django password hashes | Re-create the admin user with `createsuperuser` if it's ever needed |
| `auth_user_groups`, `auth_user_user_permissions`, `django_admin_log` | Foreign keys to `auth_user`. Their rows would fail to restore without it | None in practice |
| `django_session` | Session keys, which are login tokens | None. The bot has no web sessions |

Everything else is dumped in full: guilds, channels, members, activity stats,
reminders, playlists, games, time zones, choice lists, and so on. Plus all
schema and migration history (`django_migrations`), so a restore lines up with
the code.

### Fail closed on new tables

A denylist alone fails open. If someone later adds, say, a `storage_twitchlink`
holding tokens, it would be uploaded silently. To prevent that, the script holds
**two lists**:

- `EXCLUDE_DATA`: the tables above.
- `INCLUDE`: every other table that exists today, each one checked as non-sensitive.

Before dumping, the script reads the live table list
(`SELECT tablename FROM pg_tables WHERE schemaname='public'`). **If a table
appears in neither list, the run fails before anything is uploaded**, and posts
to Discord: "new table `storage_xyz` is not classified. Add it to INCLUDE or
EXCLUDE_DATA in `discordbot-backup.py`." Classifying a new table is then a
one-line, deliberate change.

### Post-dump check

After dumping, `pg_restore --list` is scanned. If any excluded table shows a
`TABLE DATA` entry, the run is aborted and the file deleted. This checks the
output itself, not just the flags we passed to `pg_dump`.

### Developer rule (to add to `CLAUDE.md` §8 on implementation)

> A new model that stores a token, password, API key or OAuth credential must be
> added to `EXCLUDE_DATA` in `deploy/discordbot-backup.py`. A new model that
> doesn't must be added to `INCLUDE`. The weekly backup refuses to run until
> every table is classified.

## 4. Components

```
deploy/
  discordbot-backup.py         # dump -> verify -> keep local -> upload -> prune -> report
  discordbot-backup.service    # Type=oneshot, EnvironmentFile=/root/discordbot/.env (+ backup env)
  discordbot-backup.timer      # OnCalendar Sun 04:00 UTC, Persistent=true
```

Installed the same way as the watchdog/monitor: script to `/usr/local/bin/`, units to
`/etc/systemd/system/`, `systemctl enable --now discordbot-backup.timer`.

Host-only state (never in git):

| Path | Contents | Perms |
|---|---|---|
| `/opt/discordbot-backup/venv/` | `google-api-python-client`, `google-auth`, `google-auth-oauthlib` | root |
| `/etc/discordbot-backup/token.json` | Drive OAuth refresh token | `0600 root` |
| `/etc/discordbot-backup/backup.env` | Folder ID, retention | `0600 root` |
| `/var/lib/discordbot-backup/staging/` | The dump being built and uploaded | `0700 root` |
| `/var/lib/discordbot-backup/latest/` | The newest verified dump (local copy, exactly 1 file) | `0700 root` |
| `/var/lib/discordbot-backup/last_success` | Timestamp of the last fully successful run | root |

The local copy lives under `/var/lib`, not the repo's `backups/` directory.
`backups/` holds the migration-era plaintext `.env` and a full dump, and
shouldn't be mixed with routine output.

### Timer

```ini
[Timer]
OnCalendar=Sun *-*-* 04:00:00 UTC
Persistent=true                   # missed while the host was off -> run at next boot
RandomizedDelaySec=15min
Unit=discordbot-backup.service
```

## 5. One run, step by step

```
lock ─> classify tables ─> dump ─> verify ─> keep local copy ─> upload ─> verify upload ─> prune ─> report
              │               │        │                           │            │
              └───────────────┴────────┴── any failure ────────────┴────────────┴─> abort, NO pruning, alert
```

1. **Lock.** `flock` on `/var/lib/discordbot-backup/.lock` so a manual run and the
   timer can't overlap.
2. **Classify tables** (§3). Fail if any table is unclassified.
3. **Dump.**
   ```
   pg_dump --format=custom --compress=9 --no-owner \
           --exclude-table-data=<each EXCLUDE_DATA table> \
           --dbname="$DATABASE_URL" -f staging/<name>.dump
   ```
   Custom format is compressed, and `pg_restore` can restore it selectively (one
   table, or schema only). Credentials come from `DATABASE_URL` in the existing
   `.env`, so there's no second copy of the DB password.
4. **Verify the dump.** `pg_restore --list` must succeed, list a nonzero number
   of `TABLE DATA` entries, and show **no** data for excluded tables. This also
   catches dumping the empty sqlite-era DB by mistake (see the `ENVIRONMENT`
   failure mode in `CLAUDE.md`).
5. **Keep the local copy.** Copy into `latest/`, replacing the previous one. This
   happens before the upload, so a Drive outage still leaves a fresh local backup.
6. **Upload** into the backup folder with a resumable upload. On the Drive file, set:
   - `name`: `discordbot-db-2026-10-18T040000Z.dump` (sortable UTC timestamp)
   - `appProperties`: `{"discordbot_backup": "1", "backup_ts": "<ISO UTC>"}`
7. **Verify the upload.** Compare the `md5Checksum` that Drive returns with the
   local file's MD5. If they differ, delete the uploaded copy and fail the run.
8. **Prune (R3).** Runs only if steps 2–7 all succeeded.
   - List files in the folder where `appProperties has {key='discordbot_backup' and value='1'}`
     and `trashed = false`.
   - Sort by `backup_ts` descending, then keep the first `KEEP=5`.
   - Delete **all** the rest, not just one. If the folder ever holds 7 (an old
     failed prune, a manual run), it goes back to 5 by itself.
   - Guard: if the list doesn't include the file we just uploaded, don't delete
     anything and raise an alert. This means the listing is wrong, and acting on
     it could delete good backups.
9. **Clean up and report.** Empty `staging/` and write `last_success`. Post a
   success line to Discord (§7) and log the same: size, duration, Drive file ID,
   number of files pruned.

### Why prune only after a verified upload

If we deleted the oldest file first and the upload then failed, every failed week
would cost us a backup, and 5 failed weeks in a row would empty the folder. With
prune-last, a broken run leaves the existing 5 untouched (R4).

### Why match on `appProperties` and not "everything in the folder"

The pruner only deletes files that the backup job itself created and tagged. If
someone drops a manual export or a note into the folder, it doesn't count toward
the 5 and is never deleted.

### Disk use on the host

At peak, about 2× the compressed dump: the staging file plus the previous
`latest/` copy. Measure the DB size (§0) before go-live. The host is small
(2 cores / 3 GB RAM), so if the dump turns out large, revisit this.

## 6. Google Drive specifics (to confirm when credentials arrive)

- **Auth: OAuth "Desktop app" client with a refresh token.** This is a personal
  account, and since 2025 service accounts have no storage quota of their own:
  uploading into a personal "My Drive" folder shared with one fails with
  `storageQuotaExceeded`. Setup is one consent in a browser on any machine, then
  the saved `token.json` is copied to the host. A helper (`--authorize`) will do
  the consent step.
- **Scope: `https://www.googleapis.com/auth/drive.file`.** The app can only see
  and delete files and folders that it created. Even a buggy prune can't touch
  anything else in the Drive. Consequence: **the backup job creates the folder
  itself.** A one-time `--init` step finds or creates `discordbot-db-backups` and
  writes its ID into `backup.env`. A folder made by hand in the Drive UI would be
  invisible to the job. You can move or rename that folder in Drive afterwards;
  the job tracks it by ID.
- **Publish the OAuth consent screen ("In production").** In "Testing" status,
  Google expires refresh tokens after **7 days**, which is exactly the backup
  interval. Every weekly run would hit a dead token. `drive.file` is a
  non-sensitive scope, so a personal-use app needs no Google verification to be
  published. (We'd just click through an "unverified app" warning once.)
- **Delete permanently, not to trash.** Trashed files still count toward the
  Drive quota for 30 days. With 5 kept plus up to 4 in trash, we'd use almost
  twice the storage. `files.delete` removes the file permanently, which matches
  the "keep only 5" rule.
- Expired or revoked tokens show up as `invalid_grant`. The job reports this as
  its own alert ("Drive auth broken, re-run `--authorize`") instead of a generic
  failure.

**What I'll need from you when we get there:** a Google Cloud project with the
Drive API enabled, plus an OAuth client of type *Desktop app* (`client_secret.json`),
with its consent screen set to *In production*. I can write step-by-step setup
instructions for this when we start implementing.

## 7. Notifications and failure visibility (R4)

Reuse what already exists rather than adding a new channel: post to
`ALERT_CHANNEL_ID` through the Discord REST API with the bot token, the same way
`deploy/discordbot_monitor.py` does. That works even when the bot is down.

- **Success:** `✅ DB backup 2026-10-18 ok: 4.2 MB, uploaded in 12s, 5 kept on Drive (pruned 1)`
- **Failure:** `❌ DB backup failed at <step>: <error>`, followed by "existing
  backups untouched" when pruning was skipped.
- **Staleness check.** Add one check to `discordbot_monitor.py`: if
  `last_success` is older than **8 days**, alert. This catches the failure where
  the job never ran at all: timer disabled, unit file missing, host clock wrong.
  An alert on a failed run can't catch that.
- Everything goes to the journal as well: `journalctl -u discordbot-backup`.

## 8. Restore runbook (draft)

1. Take the file from `/var/lib/discordbot-backup/latest/`, or download one from
   the Drive folder (UI, or `discordbot-backup.py --fetch <name>`).
2. **Restore into a scratch DB first:**
   `createdb discord_bot_restore && pg_restore --no-owner -d discord_bot_restore file.dump`
   and check row counts.
3. To make it live: `touch /run/discordbot.maintenance`, `docker compose down`,
   rename the DBs (or `pg_restore --clean` into `discord_bot`), `docker compose up -d`,
   `rm /run/discordbot.maintenance`.
4. After the restore: Spotify links and Django users are empty (§3). Members
   re-link with `,spotify`.

A backup that has never been restored is only assumed to work. Suggestion: do one
manual end-to-end restore right after go-live, then a quick one occasionally.

## 9. Configuration (`backup.env`)

| Var | Default | Meaning |
|---|---|---|
| `BACKUP_DRIVE_FOLDER_ID` | — (set by `--init`) | Target folder |
| `BACKUP_KEEP` | `5` | Backups retained on Drive |
| `BACKUP_TOKEN_FILE` | `/etc/discordbot-backup/token.json` | OAuth token |
| `BACKUP_STATE_DIR` | `/var/lib/discordbot-backup` | Staging, local copy, `last_success` |
| `BACKUP_NOTIFY_SUCCESS` | `1` | Post success lines to Discord |

`DATABASE_URL`, `TOKEN` and `ALERT_CHANNEL_ID` come from the existing `/root/discordbot/.env`.
The table lists (§3) are kept in the script, under version control, not in env,
so changing what gets backed up goes through a commit.

CLI: `discordbot-backup.py [--authorize | --init | --dry-run | --list | --fetch NAME]`.
`--dry-run` classifies tables, dumps and verifies, then prints what it would
upload and prune, without touching Drive.

## 10. Open items

1. **DB size**: run the query in §0 on the host.
2. **Drive API credentials**: the OAuth client from §6, when you're ready.
3. **Confirm the table classification against production.** The lists in §3 come
   from `storage/models.py` and Django's built-in apps. `--dry-run` on the host
   will flag any table in the live DB that the code doesn't know about.
