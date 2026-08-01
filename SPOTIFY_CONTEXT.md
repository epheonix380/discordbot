# SPOTIFY_CONTEXT.md — session state for the Spotify Connect feature

**Purpose:** onboard a fresh agent fast on the *feature* work (Spotify Connect bot). Read
`SPOTIFY_CONNECT_PLAN.md` first, then this file.

> This is **not** the repo's `CONTEXT.md` (that one documents the completed, live hosting/
> deployment project — containerization, systemd, watchdog — and must not be overwritten or
> reused for this feature's notes).

---

## Where this stands

Branch: `claude/spotify-connect-bot-step-1-in130u`, based directly on `production`
(`d91273a`, the containerized/watchdog-supervised state — already includes the hosting work).

**Phase 1 of `SPOTIFY_CONNECT_PLAN.md` §13 is done:** the data model & store.
Phase 0 (de-risk experiments against a live Spotify Premium account) was explicitly **skipped**
for this session — it needs interactive/live credentials this sandbox doesn't have — and is
still open; see "Still open" below.

## What was built (Phase 1)

- `storage/models.py` — added `SpotifyLink`:
  ```python
  class SpotifyLink(models.Model):
      member = models.OneToOneField(Member, on_delete=models.CASCADE)
      credentials = models.TextField()      # base64 librespot reusable-creds blob (save_creds())
      spotify_username = models.TextField(default='')
      scope = models.TextField(default='')
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)
  ```
  Exactly the shape `SPOTIFY_CONNECT_PLAN.md` §6 specifies. Stores the **librespot** reusable
  credentials blob, **not** a Web-API OAuth token (see plan §2.1 for why that distinction
  matters).
- `storage/migrations/0047_spotifylink.py` — hand-written (see "Migration note" below), verified
  by applying it against a copy of `db.sqlite3` with `manage.py migrate storage`.
- `helpers/spotifyStore.py` — async CRUD, mirrors the existing `helpers/*Store.py` pattern
  (`@sync_to_async`, `Member.objects.get_or_create(member_id=uid)`, `update_or_create`):
  - `getLink(uid)` → `{"credentials", "spotify_username", "scope"}` dict, or `None`.
  - `setLink(uid, credentials, spotify_username="", scope="")` → upsert, returns `created: bool`.
  - `deleteLink(uid)` → `True`/`False`. This is what `,spotify unlink` (plan §1.3) should call.
  - Round-tripped manually against a scratch sqlite DB (create/update/delete) — all paths work.

### Deliberate omissions (flag if anyone asks "why isn't this wired up")
- **Not registered in `storage/admin.py`** and **no DRF serializer added** for `SpotifyLink`.
  This is intentional: the plan (§11) treats these credentials as full-account secrets that must
  stay out of logs/API surfaces, and this repo's Django admin / DREST layer isn't scoped with
  that in mind for other sensitive data. Keep it that way unless there's a real access-control
  story for exposing it.
- **Not encrypted at rest yet** — stored as plain `TextField`. The plan (§6, §11) says "encrypt
  if feasible" but doesn't block Phase 1 on it. Worth raising with the user before Phase 4
  (persist real creds) ships, not before.

### Migration note (read before touching migrations again)
`manage.py makemigrations storage` on this tree **also** regenerates an unrelated
`AlterField` for `Member.lastGymCheckinDate` / `TimeZone.time_zone` every single day. Root cause:
`storage/models.py` sets `lastGymCheckinDate = models.DateField(default=datetime.datetime.now().date())`
— a call evaluated at **import time**, so the "current" default drifts from whatever date the
last migration froze. This is pre-existing and unrelated to Spotify. **Migration
`0047_spotifylink.py` was hand-written** (copied from an auto-generated one, then stripped down)
to contain *only* the `SpotifyLink` `CreateModel` op, deliberately excluding that noise. If you
run `makemigrations` again, expect it to want to generate that same unrelated diff — do not fold
it into a Spotify migration; leave it for whoever decides to fix the underlying default.

## Environment used to verify (not part of the app)
Verification was done in a throwaway venv (`django==4.2.9`, `dj-database-url==2.1.0`,
`djangorestframework==3.14.0`, `django-filter==23.5`, `pytz`) against a **copy** of `db.sqlite3`
in `/tmp` — never against the tracked `db.sqlite3` or a real postgres. Nothing from that venv is
committed. The repo's actual runtime is Python 3.9.13 in Docker per the `Dockerfile`.

## Still open / for the next phase(s)

Per `SPOTIFY_CONNECT_PLAN.md` §13, **Phase 2 — Audio pipeline (no Discord)** is next:
creds → `Session` → `content_feeder` → ffmpeg → PCM to file, off the asyncio loop. Concretely,
still needed before that can work at all:

- **`requirements.txt`** still pins the **old** librespot commit
  (`git+https://github.com/kokarare1212/librespot-python@81ecec3b682e1bec5b3ee80342f8db6c15a84047`,
  line 43). Plan §0/§10 says repin to
  `@18104622b3be02062f1f8abe8dafc396413e9784` (v0.0.10) — the old pin lacks the OAuth/connect-state
  pieces the feature needs. **Not yet done.**
- **`PyNaCl` is missing** from `requirements.txt` (needed later for Discord voice, plan §10) —
  not needed for Phase 2 itself but will be for Phase 3.
- **`Dockerfile`** doesn't install `ffmpeg` or `libopus0` yet (plan §10) — Phase 2 needs `ffmpeg`
  at minimum; `libopus0` can wait for Phase 3 (Discord voice).
- No `music/` package exists yet (plan §7: `oauth_flow.py`, `session_manager.py`,
  `connect_device.py`, `search.py`, `playback.py`, `commands.py`). Phase 2 only needs enough of
  `session_manager.py` (creds → `Session`, built in an executor) and a scratch script driving
  `content_feeder()` to prove the audio path — full module layout can wait for Phase 4+.
- **Phase 0 (de-risk) was never run.** Nobody has confirmed against a real account that: (a) the
  new librespot pin's OAuth flow completes via paste-back, (b) `content_feeder().load(...)`
  actually yields bytes, (c) `put_connect_state` + dealer registration makes a device appear in
  the Spotify app. Phase 2/3 work can proceed on the *assumption* these work (per the plan's own
  findings in §2.1/§2.2, which cite the librespot-python source directly), but the first person
  with a real Premium account + this branch should run Phase 0's checklist and report back —
  it's the plan's own recommended gate before Phase 5 (Connect receiver) in particular.
- `,spotify unlink` (plan §1.3/§12) has no command handler yet — trivial once `music/commands.py`
  exists; it's just `await spotifyStore.deleteLink(uid)`.

## Decisions already made (don't relitigate)
- Base branch is `production`, not `librespot` (plan §0) — confirmed still true, this branch's
  parent is `production`.
- Data model stores librespot creds, not a Web-API token (plan §2.1, §6).
- Bot integration will be `,`-prefix branches in `main.py`'s existing `discord.Client`/
  `on_message` router (plan §9) — **not** `commands.Bot`/Cogs. Confirmed the router shape still
  matches: `client = discord.Client(...)`, `tree = app_commands.CommandTree(client)`,
  `if/elif message.content.startswith(",...")` in `on_message` (`main.py`).
