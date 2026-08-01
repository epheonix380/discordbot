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

**Phases 1, 2, and 3 of `SPOTIFY_CONNECT_PLAN.md` §13 are done:** data model & store, the audio
pipeline (creds → `Session` → `content_feeder` → ffmpeg → PCM), and Discord voice (join/leave,
`vc.play` fed by that same pipeline). Phase 0 (de-risk experiments against a live Spotify Premium
account) was explicitly **skipped** across all three sessions — it needs interactive/live
credentials and a real running bot this sandbox doesn't have — and is still open; see "Still
open" below. **Phase 2's and Phase 3's own acceptance criteria (a correct 10s PCM file / an
audible track in a real VC) are likewise unverified against a real account and a live bot for the
same reason** — the user doing the manual final pass is expected to close that gap; what *was*
verified without one is detailed under each phase below.

## What was built (Phase 3)

Goal per plan §13: "`PyNaCl` + `ffmpeg`/`libopus` in image; `vc.play`; join/leave. Acceptance:
audible hard-coded track in a real VC; clean disconnect."

- **`music/playback.py`**:
  - `ensure_opus_loaded()` — explicit `discord.opus.load_opus("libopus.so.0")` if
    `discord.opus.is_loaded()` is `False`. **This is not hypothetical** — verified locally that
    discord.py's automatic `ctypes.util.find_library('opus')` detection returns `None` even with
    the runtime `libopus.so.0` present and loadable (likely because there's no `libopus.so` dev
    symlink on a slim image), so relying on auto-load would silently break voice. Calling
    `load_opus("libopus.so.0")` directly fixes it. Matches plan §9's explicit warning.
  - `join(voice_channel)` / `leave(voice_client)` — thin wrappers; `leave()` stops playback if
    active before disconnecting (`force=True`).
  - `play_track(voice_client, session, track_uri, *, loop=None, after=None)` — the network
    `content_feeder().load()` call runs in an executor (blocking, per plan §8), then constructs
    `discord.FFmpegPCMAudio(ogg_stream, pipe=True)` directly from librespot's chunked stream
    object — **no intermediate file, no separate ffmpeg subprocess management**: discord.py spawns
    and owns its own `ffmpeg -i - -f s16le -ar 48000 -ac 2 pipe:1` reading straight from the
    librespot stream via `source.read(8192)`. This is plan §8's "approach 1" (cleaner than the
    manual-subprocess "approach 2" used in `content_pipeline.fetch_pcm()` for the no-Discord
    Phase 2 file-output case — both are kept, for different callers). Closes the librespot stream
    in the `after` callback once playback ends, then calls the caller's own `after` if given.
- **`music/phase3_smoke_test.py`** — standalone script, **not wired into the bot or `main.py`**:
  `DISCORD_TOKEN=... python -m music.phase3_smoke_test <voice_channel_id> <credentials.json>
  <spotify:track:uri>`. Logs in, joins the given voice channel, plays the track, waits for
  playback to finish, disconnects cleanly. This is the runnable form of Phase 3's acceptance test.
  **Nobody has run it against a real bot/account yet** — needs a real `DISCORD_TOKEN`, a voice
  channel the bot has access to, and real Spotify credentials (from `phase2_smoke_test.py`'s
  format), none of which exist in this sandbox.
- **`requirements.txt`** — added `pynacl==1.5.0` (Discord voice encryption; required by
  `discord.py` for `VoiceClient.connect()`/`play()`).
- **`Dockerfile`** — added `libopus0` explicitly. (Aside: `apt-get install ffmpeg` in this sandbox
  already pulled `libopus0` in transitively — `ldd $(which ffmpeg)` shows it links
  `libopus.so.0` — but that's not a declared `Depends` of the `ffmpeg` package itself, just an
  indirect pull via one of its libs, so it's not something to rely on; explicit is correct here
  and matches what the plan already specified.)

### What was actually verified vs. not (Phase 3)
- ✅ **Verified**: `PyNaCl==1.5.0` and the bumped Phase-2 deps + `discord.py==2.3.2` +
  the pinned librespot commit all install together in one venv with no resolver conflicts;
  `PyNaCl` ships `cp36-abi3` wheels (stable ABI), which cover Python 3.9 on the target image.
- ✅ **Verified**: `discord.opus.is_loaded()` is `False` by default here even with `libopus0`
  installed, and `discord.opus.load_opus("libopus.so.0")` fixes it — see above. This would have
  been a silent, confusing voice failure if left on auto-detection.
- ✅ **Verified the actual audio-piping mechanism `play_track` relies on**, without needing a
  Discord connection or Spotify account: built a fake object exposing just `.read(n)` (standing in
  for librespot's chunked Ogg/Vorbis stream, backed by a synthetic `ffmpeg`-generated Vorbis file),
  passed it into a real `discord.FFmpegPCMAudio(..., pipe=True)`, and called the class's own
  `.read()` in a loop the way discord.py's `AudioPlayer` thread does. Result: exactly 250 frames
  of 3840 bytes each (discord.py's Opus frame size) = 960000 bytes = exactly 5.000s of
  48kHz/stereo/s16le audio for a 5-second input, byte-for-byte. This is the same code path
  `play_track()` uses in production, just with a fake source in place of a real librespot session.
- ❌ **NOT verified**: anything requiring a real Discord voice connection (joining an actual VC,
  UDP audio transmission, the gateway voice handshake) or a real Spotify account. Both are outside
  what a sandboxed agent session can do. `music/phase3_smoke_test.py` is ready for the live
  verification pass.
- **Minor, non-blocking observation**: manually calling `FFmpegPCMAudio.cleanup()` on a source
  whose underlying stream had already been fully consumed (and had thus already closed its own
  stdin) raised `ValueError: flush of closed file` inside discord.py's own `_kill_process()` →
  `subprocess.communicate()`. This only showed up because the smoke test above called `cleanup()`
  manually after draining the source by hand; `play_track()`/`voice_client.play()` never do that —
  discord.py's `AudioPlayer` thread manages the source's lifecycle itself and this exact call
  order didn't come up. Not treated as a bug to fix (it's discord.py's own internals, and normal
  playback doesn't hit it), just flagging in case it resurfaces during live testing.

## What was built (Phase 2)

Goal per plan §13: "creds → session → `content_feeder` → ffmpeg → PCM to file, off the asyncio
loop." No Discord integration in scope for this phase.

- **`music/session_manager.py`** — `build_session(credentials_json)`, `get_session(member_id,
  credentials_json)` (in-process cache), `close_session(member_id)`.
- **`music/content_pipeline.py`** — `fetch_pcm(session, track_uri, output_path, quality=...,
  duration_seconds=None)`: loads the track via `content_feeder().load(...)`, feeds the returned
  Ogg/Vorbis chunked stream into an `ffmpeg` subprocess from a background thread, decodes to raw
  `s16le`/48kHz/stereo PCM at `output_path`. Both functions are synchronous/blocking by design —
  the caller (a future `music/playback.py` or the Phase-2 smoke script) is responsible for
  running them via `loop.run_in_executor(...)`, per plan §8's blocking-call warning.
- **`music/phase2_smoke_test.py`** — standalone script, **not wired into the bot**:
  `python -m music.phase2_smoke_test <credentials.json> <spotify:track:uri> [output.pcm]
  [duration_seconds]`. This is the runnable form of Phase 2's acceptance test — hand it real
  librespot OAuth creds (see the credential-format finding below) and a track URI and it should
  produce a playable PCM file. **Nobody has run it against a real account yet.**
- **`requirements.txt`** — librespot repinned to `@18104622b3be02062f1f8abe8dafc396413e9784`
  (v0.0.10) as the plan specified. That pin's own `PKG-INFO` declares
  `pycryptodomex>=3.22.0`, `requests>=2.32.3`, `websocket-client>=1.8.0`, `zeroconf>=0.146.4` —
  all **higher** than what was already pinned here, so those four were bumped too (verified: a
  clean venv installs the new librespot pin + all four bumped deps together with no resolver
  conflicts; `protobuf==3.20.1`, `pyogg==0.6.14a1`, `defusedxml==0.7.1`, `ifaddr==0.2.0` already
  satisfied the new pin's requirements as-is). `PyNaCl` (Phase 3, Discord voice) still not added
  — correctly out of scope here.
- **`Dockerfile`** — added `ffmpeg` to the `apt-get install` line. `libopus0` still deliberately
  not added (Phase 3/Discord-voice concern, not Phase 2).

### Important finding: `OAuth.save_creds()` output does not round-trip through `stored_file()`

This matters for **Phase 4** (OAuth link UX) and anyone tempted to copy plan Appendix B literally.
Verified by reading the actual installed source of the pinned librespot commit
(`librespot/oauth.py`, `librespot/core.py`), not just the plan text:

- `OAuth.save_creds(path)` writes `{"client_id", "access_token", "expires_at", "refresh_token",
  "type": "OAUTH_PKCE_TOKEN"}`.
- `Session.Builder().stored_file(path)` / `.stored(str)` only parse `{"type", "username",
  "credentials"}` (falling back to a Rust-librespot `{"auth_type", "auth_data"}` shape). Neither
  matches what `save_creds()` produces. Feeding one into the other silently sets no
  `login_credentials` (`KeyError` is swallowed), and `.create()` then raises `"You must select an
  authentication method."` — a confusing failure with no clue it's a format mismatch.
- **Workaround already implemented** in `session_manager._login_credentials_from_json()`: builds
  `Authentication.LoginCredentials(typ=AUTHENTICATION_SPOTIFY_TOKEN,
  auth_data=access_token.encode())` directly — exactly what `OAuth.get_credentials()` does
  internally — bypassing `stored_file()`/`stored()` entirely. It also rejects (raises) if
  `expires_at` has already passed.
- **Consequence for `SpotifyLink.credentials` (Phase 1 model):** whatever Phase 4's OAuth flow
  persists into that field should be the raw JSON dict `save_creds()` writes (or equivalent),
  since `session_manager.build_session()` is what will consume it — not a pre-encoded
  `stored_file`-compatible blob. No model change needed, just noting the shape for Phase 4.
- **Consequence for "reuse & refresh" (plan §5.5):** the plan assumed librespot "refreshes the
  underlying token itself" once built from `stored_file`. That assumption is unverified and now
  looks shakier given the format mismatch above — `Session.Builder().create()` takes a
  point-in-time access token and does not appear to hold onto the OAuth refresh_token/client_id
  needed to refresh it later. **Deliberately not solved here** (would be scope creep for "no
  Discord" Phase 2); flagging as a real open question for Phase 4/7: something will need to call
  Spotify's token endpoint with the stored `refresh_token` and re-persist before/when
  `expires_at` passes. `session_manager.get_session()` currently just raises a clear error
  telling the user to re-link if the stored token is expired — no silent failure, but also no
  auto-refresh.

### What was actually verified vs. not (be precise about this)
- ✅ **Verified**: librespot API surface used here (`Session.Builder`, `content_feeder().load()`,
  `TrackId.from_uri()`, `VorbisOnlyAudioQuality`, `LoadedStream.input_stream.stream().read()`,
  `Authentication.LoginCredentials`) matches the actual installed source at the pinned commit —
  read directly, not assumed from the plan.
- ✅ **Verified**: the `ffmpeg`-piping half of `content_pipeline.fetch_pcm()` — fed a synthetic
  Ogg/Vorbis file (via a fake session object standing in for real librespot) through the exact
  same threaded-feed → subprocess-ffmpeg → file code path used in production. Output was exactly
  `48000 Hz × 2 ch × 2 bytes × N seconds` bytes, i.e. correct PCM framing, for a requested
  2-second clip.
- ✅ **Verified**: `ffmpeg` installs cleanly via `apt-get install --no-install-recommends ffmpeg`
  on the same Debian slim family the `Dockerfile` uses (this sandbox needed `apt-get update`
  first — a stale index caused spurious 404s on unrelated transitive packages; not a real
  incompatibility).
- ✅ **Verified**: new/bumped dependency versions resolve together with no conflicts, and `cp39`
  wheels exist for all of them (checked directly against PyPI's file listing) — matches the
  `Dockerfile`'s `python:3.9.13-slim` target.
- ❌ **NOT verified**: anything requiring an actual Spotify account — OAuth token exchange,
  `Session.Builder().create()` actually authenticating against a real access point,
  `content_feeder().load()` returning real track audio. This is the same gap Phase 0 was meant to
  close. `music/phase2_smoke_test.py` is ready for whoever has real Premium credentials to close
  it.

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

Per `SPOTIFY_CONNECT_PLAN.md` §13, **Phase 4 — OAuth link UX** is next: `music/oauth_flow.py` +
pending-auth store; `,play` issues a login link when unlinked; paste-back (modal/DM) persists
creds via `helpers/spotifyStore.setLink`; auto-plays the pending query once linked. This is also
where `main.py` integration (plan §9) actually starts — nothing has touched `main.py` yet.
Concretely:

- **`music/oauth_flow.py` doesn't exist yet.** Needs: build a per-user `librespot.oauth.OAuth`
  instance (keymaster client_id is hardcoded inside `Session.Builder().oauth()` but for paste-back
  you construct `OAuth` yourself — check how `Session.Builder().oauth()` does it in
  `librespot/core.py` for the right client_id constant), `get_auth_url()` → reply as embed,
  accept a pasted code or URL (parse defensively per plan §5.3), `set_code()` →
  `request_token()` → `get_credentials()`. **Persist the same dict shape `OAuth.save_creds()`
  writes** (`access_token`/`refresh_token`/`expires_at`/`type`/`client_id`) as JSON text into
  `SpotifyLink.credentials` via `spotifyStore.setLink()` — that's what
  `session_manager.build_session()` expects (see the credential-format finding under Phase 2).
  Keep the pending-auth state (code_verifier etc.) in memory keyed by Discord user id with a
  short TTL; `OAuth` objects aren't easily serializable, so this needs to survive only until the
  user pastes back, not across bot restarts.
- **Token refresh (plan §5.5) is still unresolved** — see "Consequence for reuse & refresh" under
  Phase 2. `session_manager.get_session()` currently just raises and tells the user to re-link if
  `expires_at` has passed; decide in Phase 4 whether that's good enough for the MVP or whether
  real refresh-token exchange is needed before shipping.
- **No `main.py` wiring yet.** Phase 4 is where `,play` (and eventually `,pause`/`,skip`/etc.)
  get added as `elif message.content.startswith(",play")` branches in the existing router (plan
  §9) — not a Cog. `,spotify unlink` (plan §1.3/§12) is trivial once this exists: just
  `await spotifyStore.deleteLink(uid)`.
- **Phase 0 (de-risk) was never run, and neither were Phase 2's/Phase 3's own acceptance
  criteria** (a real PCM file from a real account; an audible track in a real VC) — see each
  phase's "What was actually verified vs. not" above. All the same underlying gap: no live
  Spotify Premium account or running bot available in this sandbox. `music/phase2_smoke_test.py`
  and `music/phase3_smoke_test.py` exist specifically so whoever does the manual pass (the user
  said they'll do this) can close both gaps without writing new code — just run them and report
  back. Worth doing **before** Phase 5 (Connect receiver) in particular, per the plan's own
  gating, since Phase 5 builds directly on Phase 2/3 working.

## Decisions already made (don't relitigate)
- Base branch is `production`, not `librespot` (plan §0) — confirmed still true, this branch's
  parent is `production`.
- Data model stores librespot creds, not a Web-API token (plan §2.1, §6).
- Bot integration will be `,`-prefix branches in `main.py`'s existing `discord.Client`/
  `on_message` router (plan §9) — **not** `commands.Bot`/Cogs. Confirmed the router shape still
  matches: `client = discord.Client(...)`, `tree = app_commands.CommandTree(client)`,
  `if/elif message.content.startswith(",...")` in `on_message` (`main.py`).
- `music/session_manager.py` and `music/content_pipeline.py` functions are synchronous/blocking
  on purpose — callers run them via `run_in_executor`, they don't do their own async wrapping.
  `music/playback.py` follows the same split (`play_track` is the one async entrypoint; the
  actual track fetch happens in an executor).
- `music/playback.play_track()` builds `discord.FFmpegPCMAudio` directly from the librespot
  stream object (plan §8 "approach 1") rather than writing PCM to a file first — don't replace
  this with `content_pipeline.fetch_pcm()` for the Discord path, that function is for the
  no-Discord Phase 2 file-output use case only.
