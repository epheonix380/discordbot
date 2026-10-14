# Weekly DB backups to Google Drive — design (draft)

Status: **preliminary design**, nothing implemented yet. Drive API credentials
are not set up; everything Drive-specific below is the planned shape and will be
confirmed once they are.

## 1. Requirements

| # | Requirement |
|---|---|
| R1 | Back up the live database (host Postgres `127.0.0.1:5432`, db `discord_bot`) every 7 days. |
| R2 | Upload each backup to one dedicated folder on Google Drive. |
| R3 | Keep only the 5 most recent backups in that folder. Uploading the 6th deletes the oldest. |
| R4 | A failed run must never cost us a good backup, and must not go unnoticed. |
| R5 | Backups must not affect the running bot (see `CLAUDE.md`: one instance, gateway heartbeat, self-healing DB). |

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

## 3. Components

```
deploy/
  discordbot-backup.py         # the job: dump -> verify -> (encrypt) -> upload -> prune -> report
  discordbot-backup.service    # Type=oneshot, EnvironmentFile=/root/discordbot/.env (+ backup env)
  discordbot-backup.timer      # OnCalendar weekly, Persistent=true
```

Installed the same way as the watchdog/monitor: script to `/usr/local/bin/`, units to
`/etc/systemd/system/`, `systemctl enable --now discordbot-backup.timer`.

Host-only state (never in git):

| Path | Contents | Perms |
|---|---|---|
| `/opt/discordbot-backup/venv/` | `google-api-python-client`, `google-auth`, `google-auth-oauthlib` | root |
| `/etc/discordbot-backup/token.json` | Drive OAuth refresh token | `0600 root` |
| `/etc/discordbot-backup/backup.env` | Folder ID, retention, encryption recipient | `0600 root` |
| `/var/lib/discordbot-backup/` | Staging dir for the dump being uploaded; `last_success` timestamp | `0700 root` |

### Timer

```ini
[Timer]
OnCalendar=Sun *-*-* 04:00:00     # weekly; pick a quiet hour
Persistent=true                   # missed while the host was off -> run at next boot
RandomizedDelaySec=15min
Unit=discordbot-backup.service
```

## 4. One run, step by step

```
lock ──> dump ──> verify ──> encrypt? ──> upload ──> verify upload ──> prune ──> record + report
                                                         │
                         any failure before this point ──┴──> abort, NO pruning, alert
```

1. **Lock.** `flock` on `/var/lib/discordbot-backup/.lock` so a manual run and the
   timer can't overlap.
2. **Dump.**
   `pg_dump --format=custom --compress=9 --no-owner --dbname="$DATABASE_URL" -f <staging>/<name>.dump`
   Custom format is compressed, and `pg_restore` can restore it selectively (one
   table, or schema only). Credentials come from `DATABASE_URL` in the existing
   `.env`, so there's no second copy of the DB password.
3. **Verify the dump locally.** `pg_restore --list <file>` must succeed and list
   a nonzero number of `TABLE DATA` entries. This catches empty or truncated
   dumps, and also catches us dumping the empty sqlite-era DB by mistake (see
   the `ENVIRONMENT` failure mode in `CLAUDE.md`).
4. **Encrypt (recommended, see §7).** `age -r <public key> -o <name>.dump.age`.
5. **Upload** into the backup folder with a resumable upload. On the Drive file, set:
   - `name`: `discordbot-db-2026-10-18T040000Z.dump.age` (sortable UTC timestamp)
   - `appProperties`: `{"discordbot_backup": "1", "backup_ts": "<ISO UTC>"}`
6. **Verify the upload.** Compare the `md5Checksum` that Drive returns with the
   local file's MD5. If they differ, delete the uploaded copy and fail the run.
7. **Prune (R3).** Runs only if steps 2–6 all succeeded.
   - List files in the folder where `appProperties has {key='discordbot_backup' and value='1'}`
     and `trashed = false`.
   - Sort by `backup_ts` descending, then keep the first `KEEP=5`.
   - Delete **all** the rest, not just one. If the folder ever holds 7 (an old
     failed prune, a manual run), it goes back to 5 by itself.
   - Guard: if the list doesn't include the file we just uploaded, don't delete
     anything and raise an alert. This means the listing is wrong, and acting on
     it could delete good backups.
8. **Clean up and record.** Delete the local staging file, write `last_success`,
   and log the outcome: size, duration, Drive file ID, number of files pruned.

### Why prune only after a verified upload

If we deleted the oldest file first and the upload then failed, every failed week
would cost us a backup, and 5 failed weeks in a row would empty the folder. With
prune-last, a broken run leaves the existing 5 untouched (R4).

### Why match on `appProperties` and not "everything in the folder"

The pruner only deletes files that the backup job itself created and tagged. If
someone drops a manual export or a note into the folder, it doesn't count toward
the 5 and is never deleted.

## 5. Google Drive specifics (to confirm when credentials arrive)

- **Auth: OAuth user credentials with a refresh token. A service account won't
  work if this is a personal Google account.** Since 2025, service accounts have
  no storage quota of their own, and uploading into a personal "My Drive" folder
  shared with one fails with `storageQuotaExceeded`. A service account only works
  with a **Shared Drive**, which needs Google Workspace. Personal account: an
  OAuth "Desktop app" client, one consent on a machine with a browser, and the
  saved refresh token copied to the host.
- **Scope: `https://www.googleapis.com/auth/drive.file`.** The app can only see
  and delete files and folders that it created. Even a buggy prune can't touch
  anything else in the Drive. Consequence: **the backup job creates the folder
  itself.** A one-time `--init` step finds or creates `discordbot-db-backups` and
  writes its ID into `backup.env`. A folder made by hand in the Drive UI would be
  invisible to the job.
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
  its own alert ("Drive auth broken, re-run consent") instead of a generic failure.

## 6. Failure visibility (R4)

Reuse what already exists rather than adding a new channel:

- **Alert on failure.** Post to `ALERT_CHANNEL_ID` through the Discord REST API
  with the bot token, the same way `deploy/discordbot_monitor.py` does. That
  works even when the bot is down. Optionally post a short success line too
  ("backup 2026-10-18 ok, 4.2 MB, 5 kept").
- **Staleness check.** Add one check to `discordbot_monitor.py`: if
  `/var/lib/discordbot-backup/last_success` is older than **8 days**, alert. This
  catches the failure where the job never ran at all: timer disabled, unit file
  missing, host clock wrong. An alert on a failed run can't catch that.
- Everything goes to the journal as well: `journalctl -u discordbot-backup`.

## 7. Security

- The dump contains all bot data (guild/user IDs, stored user content, Spotify
  data if any), and it ends up on a third-party service. **Recommendation: encrypt
  before upload with `age`.** Only the public key lives on the host. The private
  key stays offline, e.g. in a password manager. If the Google account is
  compromised, the attacker gets encrypted blobs, and a compromised host can
  write backups but not read old ones.
  Trade-off: **lose the private key and you lose every backup.** This is a
  decision for you (see open questions).
- `token.json` and `backup.env` are `0600 root`, outside the repo, and never
  under `backups/` (that directory already holds a plaintext `.env` copy).
- No secrets on the command line: `pg_dump` gets its credentials through
  `DATABASE_URL`/`PGPASSWORD` in its environment, not in `argv`.

## 8. Restore runbook (draft)

1. Download the wanted file from the Drive folder (UI, or `discordbot-backup.py --fetch <name>`).
2. `age -d -i key.txt -o restore.dump file.dump.age`
3. **Restore into a scratch DB first:**
   `createdb discord_bot_restore && pg_restore --no-owner -d discord_bot_restore restore.dump`
   and check row counts.
4. To make it live: `touch /run/discordbot.maintenance`, `docker compose down`,
   rename the DBs (or `pg_restore --clean` into `discord_bot`), `docker compose up -d`,
   `rm /run/discordbot.maintenance`.

A backup that has never been restored is only assumed to work. Suggestion: do one
manual end-to-end restore right after go-live, then a quick one occasionally.
Automated restore tests can come later.

## 9. Configuration (`backup.env`)

| Var | Default | Meaning |
|---|---|---|
| `BACKUP_DRIVE_FOLDER_ID` | — (set by `--init`) | Target folder |
| `BACKUP_KEEP` | `5` | Backups retained on Drive |
| `BACKUP_AGE_RECIPIENT` | — | `age` public key; unset = no encryption |
| `BACKUP_TOKEN_FILE` | `/etc/discordbot-backup/token.json` | OAuth token |
| `BACKUP_STAGING_DIR` | `/var/lib/discordbot-backup` | Local temp |
| `BACKUP_ALERT_ON_SUCCESS` | `0` | Also post success lines to Discord |

`DATABASE_URL`, `TOKEN` and `ALERT_CHANNEL_ID` come from the existing `/root/discordbot/.env`.

CLI: `discordbot-backup.py [--init | --dry-run | --list | --fetch NAME]`.
`--dry-run` dumps and verifies, then prints what it would upload and prune,
without touching Drive.

## 10. Open questions

1. **Google account type:** personal Gmail or Workspace? This decides between
   OAuth with a refresh token and a service account with a Shared Drive (§5).
2. **Encrypt with `age`?** Recommended. If yes, where will the private key be kept?
3. **DB size today?** This is for staging disk on a small host and upload time.
   (`SELECT pg_size_pretty(pg_database_size('discord_bot'));`)
4. **Day and time:** Sunday 04:00 UTC OK?
5. **Success notifications in Discord**, or only failures?
6. Should the **local `backups/`** directory also keep the latest dump, as a
   second copy that doesn't depend on Drive?
