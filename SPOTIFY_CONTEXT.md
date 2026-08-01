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

**Phases 1–4 of `SPOTIFY_CONNECT_PLAN.md` §13 are done:** data model & store, the audio pipeline
(creds → `Session` → `content_feeder` → ffmpeg → PCM), Discord voice (join/leave, `vc.play`), and
now OAuth link UX — `,play` is wired into `main.py` for the first time, issues a login link when
unlinked, accepts paste-back over DM, persists credentials, and auto-plays the track the user
originally asked for once linked. **This is Mode B (plan §1.2) — the command-driven URI player —
which the plan calls shippable at the end of Phase 4.** Phase 0 (de-risk experiments against a
live Spotify Premium account) was explicitly **skipped** across all four sessions — it needs
interactive/live credentials and a real running bot this sandbox doesn't have — and is still
open; see "Still open" below. **The user has said they'll do a manual final pass covering
everything that needs a real Spotify Premium account and a live bot** (Phases 0/2/3/4's live
acceptance criteria) — what *was* verified without one is detailed under each phase below; that
verification is thorough (dependency resolution, exact byte-level audio framing, and now full
command-logic coverage with mocked network/Discord boundaries) but is not a substitute for it.

## What was built (Phase 4)

Goal per plan §13: "`oauth_flow.py` + pending store; `,play` issues link when unlinked;
modal/DM paste-back persists creds; auto-plays pending query. Acceptance: a fresh user links in
Discord and hears their track (Mode B shippable here)."

- **`music/oauth_flow.py`**:
  - `start_link(user_id, pending_query=None, guild_id=None, voice_channel_id=None)` — builds a
    per-user `librespot.oauth.OAuth(KEYMASTER_CLIENT_ID, DEFAULT_REDIRECT_URL, None)`, returns
    `get_auth_url()`. Not blocking (no network — PKCE math is local). Stores the `OAuth` instance
    plus the query/guild/channel the user was trying to play in, keyed by
    `str(discord_user_id)`, with a 10-minute TTL (matches plan §5.1), purged lazily on next
    access.
  - `KEYMASTER_CLIENT_ID` = `librespot.mercury.MercuryRequests.keymaster_client_id` (read from
    the actual installed source, not guessed — it's the same first-party client ID
    `Session.Builder().oauth()` uses internally).
  - `DEFAULT_REDIRECT_URL = "http://127.0.0.1:5588/login"` — deliberately reused from
    `Session.Builder().oauth()`'s own default flow (`librespot/core.py`), since that's a redirect
    URI already proven accepted by the keymaster client (upstream uses it for its own
    non-listening default). This is the plan's §2.4(b) "paste-back" path: the browser will fail
    to load that URL after authorizing (nothing is listening on it), but the `code=` is still
    visible in the address bar for the user to copy. **The plan's §2.4(a) public-callback
    upgrade was not attempted** — no hosted HTTPS redirect available in this environment to test
    whether keymaster would even accept one; paste-back is what's implemented.
  - `parse_code(raw_text)` — accepts either a bare code or a full pasted URL/redirect, regex-pulls
    `code=...` if present, URL-decodes it.
  - `complete_link(user_id, raw_code_or_url)` — blocking (does `oauth.request_token()`, a real
    network call). Pops the pending entry (raises `KeyError` if none/expired), exchanges the
    code, then **extracts the resulting credentials via `oauth.save_creds(tmp_path)` and reads
    the file back** rather than reaching into `OAuth`'s private (name-mangled) fields — that's
    the only public way to get the token out, since `OAuth.__token`/`__refresh_token`/etc. are
    real Python name-mangled attributes, not just conventionally-private. Returns
    `(credentials_json, pending_dict)`.
- **`music/search.py`** — `resolve_track_uri(query)`: regex-matches a direct
  `spotify:track:<id>` URI or an `open.spotify.com/track/<id>` URL (with or without a `?si=...`
  suffix) and returns the canonical URI, else `None`. **Free-text search via the Web API is
  explicitly plan Phase 6, not implemented here** — `,play <song name>` currently replies that
  only direct links/URIs work for now. This was a deliberate scope call, not an oversight: the
  plan's own phase table assigns Web-API search to Phase 6, after Connect-receiver Phase 5.
- **`music/commands.py`** — the handlers plan §7/§9 call for (`async def handler(message,
  client)`, not a Cog):
  - `handle_play` — parses the query, checks the caller is in a voice channel, checks
    `spotifyStore.getLink`; if unlinked, calls `oauth_flow.start_link` (via executor) with the
    query/guild/channel attached and replies with the login link + Premium notice; if linked,
    resolves the track URI via `search.resolve_track_uri`, builds/reuses a session via
    `session_manager.get_session` (via executor), then joins/moves voice and calls
    `playback.play_track` through a shared `_join_and_play` helper.
  - `handle_spotify` — `,spotify unlink` deletes the stored link and closes any cached session;
    anything else replies with usage.
  - `handle_spotify_pasteback` — the DM-side handler. Calls `oauth_flow.complete_link` (via
    executor), builds a session from the fresh credentials, stores `spotify_username` (from
    `session.username()` — a real librespot `Session` method, confirmed by reading `core.py`) via
    `spotifyStore.setLink`, caches the session (`session_manager.cache_session`, a small addition
    made this phase so callers don't have to reach into `session_manager._sessions` directly),
    then checks whether the user is **still** in the voice channel they started linking from
    (looked up live via `client.get_guild(...).get_member(...).voice`, not trusted from the
    pending record) — if so, auto-plays the original query there (plan's "auto-plays pending
    query"); if not, tells them to run `,play <track>` again.
- **`main.py`** — first real wiring for this feature: `,play` and `,spotify` added to the guild
  branch of `on_message`; the DM branch (`if message.guild is None:`) gets an
  `elif has_pending_spotify_link(message.author.id): await handle_spotify_pasteback(...)` before
  its `return`, per plan §9's instruction to route paste-back through the existing DM branch.
  Nothing else in the router changed.
- **`commands/help.py`** — added a `,help spotify` section and a one-line entry in the top-level
  `,help` output, matching the existing per-feature help convention (every other command has one).
  *Not* required by the plan, but cheap and consistent with the rest of the codebase.
- **`music/session_manager.py`** — added `cache_session(member_id, session)` and normalized all
  three cache functions (`get_session`/`cache_session`/`close_session`) to key on `str(member_id)`
  internally, so callers can pass a raw Discord ID (`int`) without remembering to `str()` it
  themselves — a real bug class avoided: `commands.py` and the smoke-test scripts were calling
  these with inconsistent types before this normalization.

### Deviation from the plan text worth flagging: no embeds
Plan §5.2 suggests a Spotify-green (`0x1DB954`) `discord.Embed` for the login-link message. This
codebase has **zero** existing uses of `discord.Embed` anywhere (checked) — every handler sends
plain text via `message.channel.send(content)`. Followed the codebase's actual convention instead
of the plan's aspirational one; all Phase 4 messages are plain text. Revisit only if the user
specifically asks for richer formatting.

### What was actually verified vs. not (Phase 4)
- ✅ **Verified, thoroughly, against a real Django DB (scratch copy) with the network/Discord/
  Spotify boundaries mocked out** — not just import-checked like earlier phases. Built a small
  test harness (fake `discord.Message`/`discord.Client`/voice objects, `unittest.mock.patch` on
  `session_manager.get_session`/`build_session` and `commands._join_and_play`) and exercised:
  - `handle_play`: empty query → usage; not in a VC → prompt; unlinked → auth link sent *and* the
    pending entry correctly records `pending_query`/`guild_id`/`voice_channel_id`; linked +
    free-text query → "not supported yet" notice; linked + valid URI + session-build failure →
    relink message; linked + valid URI + full success → correct "Now playing" message and
    `_join_and_play` called with the right arguments.
  - `handle_spotify`: `unlink` when linked → deletes and confirms (checked against the DB
    afterward — link is actually gone); `unlink` when not linked → correct message; bare
    `,spotify` → usage.
  - `handle_spotify_pasteback`: no pending link → correct message; link succeeds but user has
    left the original voice channel → linked message *without* auto-play, telling them to retry;
    link succeeds and user is still in the channel → auto-play fires with the exact guild/channel/
    track URI from the pending record.
  - `oauth_flow.start_link`/`has_pending`/`complete_link`/`parse_code` directly: real (non-mocked)
    `get_auth_url()` calls produced a URL containing the correct keymaster `client_id`;
    `complete_link` on a nonexistent/expired pending entry raises `KeyError` as documented; the
    10-minute TTL actually purges (verified by monkeypatching the TTL to 10ms and sleeping 50ms).
  - `search.resolve_track_uri`: canonical URI, `open.spotify.com` URL with a `?si=...` tracking
    param, a bare domain-less form, an unsupported free-text query, an unsupported `spotify:
    album:...` URI, and a too-short ID all produced the expected result.
- ❌ **NOT verified**: `oauth.request_token()` actually exchanging a real code for a real token
  (needs a live Spotify authorization), `session.username()` against a real account, or anything
  in Discord's own voice/gateway path. Same category of gap as every prior phase — no live
  Spotify/Discord access in this sandbox. **This is the piece the user said they'd verify
  manually.**

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

Per `SPOTIFY_CONNECT_PLAN.md` §13, **Phase 5 — Connect receiver (Mode A)** is next:
`music/connect_device.py` — `PutStateRequest`, dealer `MessageListener`/`RequestListener`,
capturing the dealer `connection_id`, translating dealer commands into playback actions, and
reporting state back via `put_connect_state` so the bot shows up as a real Spotify Connect device
controllable from the user's own Spotify app. This is a bigger lift than any phase so far — see
plan §2.3 for what librespot-python does *not* hand you (no finished SPIRC player loop). The plan
explicitly recommends running Phase 0's checklist for real before starting this phase, since it's
the one that most depends on dealer/connect-state actually behaving as the plan's research
(§2.2) predicted. Concretely, before/while starting Phase 5:

- **Nothing about dealer/connect-state has been touched yet** — `music/session_manager.py` only
  builds a `Session`, it doesn't do anything with `session.dealer()` or
  `session.api().put_connect_state(...)`. All of Phase 5 is new code.
- **Token refresh (plan §5.5) is still unresolved** — see "Consequence for reuse & refresh" under
  Phase 2. `session_manager.get_session()` currently just raises and tells the user to re-link if
  `expires_at` has passed. A Connect receiver plausibly stays "live" (registered device) for much
  longer than a single `,play` call, which makes token expiry more likely to actually bite during
  Phase 5 than it was in Phase 3/4 — worth deciding on a real refresh strategy before/during this
  phase rather than after.
- **Free-text search (plan §7 `music/search.py`, Phase 6) still isn't implemented** —
  `music/search.py` currently only resolves direct track URIs/URLs (see Phase 4 above). Doesn't
  block Phase 5, but a Connect receiver is arguably more useful once `,play <song name>` works
  too, so it may be worth sequencing Phase 6 before or alongside Phase 5 depending on what the
  user wants to use first — flagging as a sequencing question, not a blocker.
- **`,pause`/`,resume`/`,skip`/`,stop`/`,leave`/`,queue`/`,nowplaying` (plan §12) are still
  unimplemented.** Phase 4 only built `,play` and `,spotify unlink`, deliberately — those other
  commands need per-guild player *state* (currently-playing track, queue) that doesn't exist yet
  (`music/playback.py` has no `GuildPlayer`, just stateless `join`/`leave`/`play_track`). That's
  Phase 6 (`GuildPlayer` queue) and arguably needed before Phase 5's state-reporting can be
  fully correct either (dealer commands like pause/skip need something to act on).
- **Phase 0 (de-risk) was never run, and neither were Phases 2/3/4's own live acceptance
  criteria** (a real PCM file; an audible track in a real VC; a fresh user actually linking and
  hearing their track) — see each phase's "What was actually verified vs. not" above. All the
  same underlying gap: no live Spotify Premium account or running bot available in this sandbox.
  **The user has said they'll do a manual final pass to cover this.** `music/phase2_smoke_test.py`
  and `music/phase3_smoke_test.py` are ready for that; Phase 4's own logic was verified thoroughly
  with mocks (see above) but the live OAuth exchange and end-to-end Discord flow have not been
  run. This is worth closing out **before** Phase 5 in particular, per the plan's own gating —
  Phase 5 builds directly on the session/credential plumbing Phase 2/4 put in place, so if that
  plumbing has a live-environment surprise, better to find it before adding dealer/connect-state
  complexity on top.

## Decisions already made (don't relitigate)
- Base branch is `production`, not `librespot` (plan §0) — confirmed still true, this branch's
  parent is `production`.
- Data model stores librespot creds, not a Web-API token (plan §2.1, §6).
- Bot integration will be `,`-prefix branches in `main.py`'s existing `discord.Client`/
  `on_message` router (plan §9) — **not** `commands.Bot`/Cogs. Confirmed the router shape still
  matches: `client = discord.Client(...)`, `tree = app_commands.CommandTree(client)`,
  `if/elif message.content.startswith(",...")` in `on_message` (`main.py`). Now actually wired:
  `,play` and `,spotify` in the guild branch, paste-back in the DM branch.
- `music/session_manager.py` and `music/content_pipeline.py` functions are synchronous/blocking
  on purpose — callers run them via `run_in_executor`, they don't do their own async wrapping.
  `music/playback.py` and `music/oauth_flow.py`'s `complete_link` follow the same split (the
  network/blocking calls are plain sync functions; `music/commands.py` is the only place that
  wraps them in `run_in_executor`).
- `music/playback.play_track()` builds `discord.FFmpegPCMAudio` directly from the librespot
  stream object (plan §8 "approach 1") rather than writing PCM to a file first — don't replace
  this with `content_pipeline.fetch_pcm()` for the Discord path, that function is for the
  no-Discord Phase 2 file-output use case only.
- No `discord.Embed` usage — this codebase has none anywhere, so Phase 4 sent plain text to match,
  despite the plan suggesting embeds. Keep doing that unless the user asks for embeds specifically.
- `music/search.py` only handles direct Spotify track URIs/URLs, not free-text search — that's
  Phase 6 by the plan's own phase table, not an oversight.
- Session/credential caching (`session_manager._sessions`) is a plain in-process dict, not
  persisted — acceptable for now since `SpotifyLink.credentials` in the DB is the durable copy
  and a session gets rebuilt from it on demand; revisit only if Phase 5's dealer connections need
  to survive bot restarts more gracefully than "rebuild from stored creds."
