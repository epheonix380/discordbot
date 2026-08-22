# SPOTIFY_CONTEXT.md — session state for the Spotify Connect feature

> ## ⛔ SUPERSEDED — read `LIBRESPOT_RUST_PLAN.md` first
>
> As of **2026-08-10** the librespot-python approach documented below has been **abandoned**. Nine
> distinct defects were found in that library's Connect/dealer half and the device never once
> appeared in a real Spotify app. The feature is being rebuilt on the **Rust `librespot` binary**
> run as a subprocess.
>
> This file remains valuable as **history** and, above all, for its record of what was
> **verified live** — Discord voice on discord.py 2.7.1 + davey, the OAuth link flow, the
> `load_opus` requirement. Do not implement the architecture described here.

**Purpose:** onboard a fresh agent fast on the *feature* work (Spotify Connect bot). Read
`SPOTIFY_CONNECT_PLAN.md` first, then this file.

> This is **not** the repo's `CONTEXT.md` (that one documents the completed, live hosting/
> deployment project — containerization, systemd, watchdog — and must not be overwritten or
> reused for this feature's notes).

---

# ⚠️ SESSION 2026-08-09/10 — LIVE DEBUGGING. READ THIS FIRST.

This session ran the feature against a **real Spotify Premium account and the live bot** for the
first time — the "manual pass" every phase below was waiting on. It invalidates several
assumptions in the older sections and found **three real bugs, all now fixed**. Everything below
this section predates it.

## TL;DR

| Layer | Status |
|---|---|
| OAuth link → librespot `Session` → `content_feeder` → ffmpeg → PCM | ✅ **VERIFIED WORKING** against a real Premium account |
| librespot dealer websocket (Connect device registration) | ✅ **BUG FOUND + FIXED** — device now registers |
| Discord **voice** connection | ✅ **FIXED + VERIFIED LIVE** — `discord.py` 2.3.2 → 2.7.1 + `davey`; audible audio in a real VC, clean disconnect |
| Spotify Connect end-to-end (device appears in app, transfer plays audio) | ⛔ Still unverified — this is now the next thing to test |

## 1. ✅ The audio pipeline genuinely works (no longer an assumption)

Ran the whole flow by hand, outside the bot, with a **real Premium account**: generated the auth
URL, the user authorized it, the hosted callback caught the code, and the script exchanged it and
piped audio to a file. Results:

- Token exchange succeeded; `save_creds()` blob is as documented in Phase 2.
- `Session.Builder().create()` authenticated — `session.username()` returned a real username
  (`31gfmisimhdtf6sqd4627uhmmtq4`).
- `content_feeder().load()` streamed **real** Ogg/Vorbis from Spotify.
- ffmpeg decoded to PCM: **1,918,924 bytes** vs 1,920,000 expected for 10s @48kHz/stereo/s16le
  (~0.03s short — stream-boundary rounding, not a bug). **89.8% non-silent samples**, peak
  amplitude ±~28k, i.e. actual music, not silence.

**Consequence:** `oauth_flow.py`, `session_manager.py`, `content_pipeline.py` and librespot's
core streaming are **cleared**. Do not go hunting there for playback bugs. Phase 2's and Phase 4's
"NOT verified — needs a real account" gaps are now **closed**.

## 2. ✅ Real bug in librespot-python: the dealer websocket never connected (FIXED)

`DealerClient.connect()` in the pinned commit builds a `ConnectionHolder` wrapping
`websocket.WebSocketApp(url)` but **never assigns `on_open`/`on_message`/`on_error` onto that
WebSocketApp, and never calls `run_forever()`** (confirmed: `run_forever` appears nowhere in
`core.py`). The socket is structurally incapable of ever opening.

This is fatal for Mode A specifically: the Connect receiver is driven *entirely* by frames on that
socket — the pusher `connection_id` arrives there, and that is what triggers
`put_state(NEW_DEVICE)`, which is what makes the device appear in the user's Spotify app. Dead
socket ⇒ **device can never appear**, no matter what this bot does.

**Fixed** in `music/connect_device.py` via `_patch_dealer_connect()` (idempotent, applied at import
time): wires the callbacks and runs `ws.run_forever()` on a daemon thread. **Verified live** — the
log now shows `Connect device 'Discord Bot' got a connection_id, registering as NEW_DEVICE`, which
had never happened before.

This is a *third* librespot bug, on top of the shared-listener-dict and bare-import bugs already
documented in Phase 5. Note the pattern: **this library's Connect/dealer half is largely untested
upstream — read its source before trusting any of it.**

> A `NameError: threading is not defined` slipped into the first version of this patch (missing
> import) and briefly made *every* session build fail with "couldn't start a session / make sure
> it's Premium". Fixed. Flagging because that error message is misleading — it is not a Premium
> problem.

## 2b. Two MORE librespot dealer bugs (#4 and #5) — found 2026-08-10, both fixed

Fixing the dead socket (§2) only exposed the next two. Both are in `music/connect_device.py` as
idempotent import-time monkeypatches, next to the existing ones.

### Bug #4 — `DealerClient.wait_for_listener()` has its condition inverted (deadlock)

```python
def wait_for_listener(self):
    with self.__message_listeners_lock:
        if self.__message_listeners == {}:
            return                              # no listeners -> proceed
        self.__message_listeners_lock.wait()    # listeners exist -> BLOCK FOREVER
```

`ConnectionHolder.on_message()` calls this before dispatching **every** inbound frame, so once our
listeners are registered the websocket's reader thread parks in `wait()` and nothing is ever
delivered — no `connection_id`, no transfer, no pause/resume. Fixed by
`_patch_dealer_wait_for_listener()` to the evidently-intended semantics (return if a listener
exists; otherwise wait, *bounded*, for one).

**This is why §2 appeared to work and then "regressed" with no code change — it was always a
race**, and worth internalising before trusting any future "it worked once" result here:

- *Session built fresh*: dealer connects inside `Session.authenticate()`, the pusher frame arrives
  while the reader is parked, then `ConnectDevice` registers listeners → `add_message_listener()`
  calls `notify_all()` → reader wakes → frame dispatches → **device appears.**
- *Session already cached*: registration finishes first (~0.01s), socket opens a second later, the
  frame hits an already-blocked reader and no further `add_*` call is coming → **device never
  appears.**

Verified directly against the real class (not mocked): with zero listeners it returns immediately,
with one registered it never returns, and a second `add_message_listener()` releases it.

### Bug #5 — `handle_message()` b64-decodes a list

`payloads` arrives as a JSON **array** of base64 chunks; librespot passes it straight to
`base64.b64decode()`, raising `TypeError: argument should be a bytes-like object or ASCII string,
not 'list'`. The websocket library swallows this into an `error from callback` log, so the frame is
silently dropped. Observed live at 04:51:39 the moment the deadlock fix let real traffic through.

Fixed by `_patch_dealer_handle_message()`, which joins the chunks **before** decoding (correct for
a payload split mid-base64-quantum — verified with a deliberately mid-quantum split) and hands the
frame to librespot's own unmodified logic.

### Also fixed: header case-sensitivity (latent, would have broken transfer)

`__get_headers()` is annotated `-> CaseInsensitiveDict` but returns the raw JSON dict. Header names
are case-insensitive on the wire, so a lowercase `content-type`/`transfer-encoding` would miss
`handle_message`'s and `handle_request`'s branches — sending a JSON body through `b64decode`, or
leaving a gzipped request payload uncompressed so `payload.get("message_id")` yields `None` and a
transfer from the app quietly does nothing. Both patches now wrap headers in a real
`CaseInsensitiveDict`; verified that `connect_device.py:196`'s `headers.get("Spotify-Connection-Id")`
resolves a lowercase `spotify-connection-id` off the wire.

Both patches log the raw frame (pusher frames and all requests at INFO) — the Connect wire shape is
still the biggest unverified assumption in this feature, and this is where it can be observed.

## 2c. Spotify access-point selection is a coin flip (fixed in `session_manager`)

`apresolve.spotify.com` returns a pool of access points and librespot picks **one at random**
(`ApResolver.get_random_of` → `random.choice`) with no retry. Measured from this host:

```
ap-guc3.spotify.com:4070  OK        ap-gae2.spotify.com:4070  OK
ap-guc3.spotify.com:443   REFUSED   ap-gue1.spotify.com:443   OK
ap-guc3.spotify.com:80    OK        ap-gew4.spotify.com:80    REFUSED
```

2 of 6 actively refuse TCP, so **~1 in 3 logins died on a coin flip** — that is what produced the
`ConnectionRefusedError` at `core.py:1910` that killed a `,play` and a re-link on 2026-08-10. Not a
firewall or an outage; don't go hunting for one.

`session_manager.build_session()` now retries up to `AP_CONNECT_ATTEMPTS` (5) times, rebuilding the
`Session.Builder` each time so the AP is re-rolled. ~33% failure → ~0.4%. Only connection-level
errors retry; an auth failure is not going to fix itself on the next AP.

## 3. ✅ RESOLVED: Discord voice rejected `discord.py==2.3.2` (close code 4006)

**Symptom:** `,play` joins voice, then drops ~10s later; nothing ever plays.

**What the logs actually show:** `voice_channel.connect()` internally retries **5 times**, and
*every* attempt — including the first, on a gateway session seconds old — is closed by Discord
with **4006 ("session no longer valid")**. That burns ~27s, after which `vc.play()` raises
`ClientException: Not connected to voice`. The `Shard ID None has stopped responding to the
gateway` spam is a **downstream symptom** of the failed handshakes, **not** the cause.

**Root cause:** `discord.py==2.3.2` offers only the legacy voice encryption modes
(`VoiceClient.supported_modes` == `xsalsa20_poly1305{,_lite,_suffix}`). Discord has since removed
those. discord.py's own changelog for **v2.5.0** says it added AEAD XChaCha20-Poly1305
*"to allow voice to continue working when the older encryption modes eventually get removed."*
Our client offers only retired modes ⇒ rejected on every voice IDENTIFY.

### Proven by elimination — do NOT re-litigate these

Each of these was tested and produced the **identical** 5×4006 failure:

1. Full `,play` path (Spotify session + Connect device).
2. `,play` reduced to **local `test.mp3` only** — zero Spotify/librespot code involved.
3. **discord.py's own official voice example, verbatim, in a separate clean process** with no
   imports from this repo, same token/guild/channel. Also 4006. ← most conclusive.

Therefore **ruled out**: our architecture/complexity, Spotify/librespot, threading/GIL/event-loop
starvation, gateway intents (`Intents.default()` already includes `voice_states`), and
network/firewall/ports (DNS resolves the voice endpoint, TCP:443 to it connects, outbound UDP
works — and a firewall block cannot produce a *graceful protocol-level close code* anyway).

Earlier suspicion that blocking librespot calls were starving the event loop was **wrong**;
timing logs proved `_ensure_connect_device` takes 0.00s and the entire ~27s is inside discord.py's
own retry loop.

### The fix (complete, verified live 2026-08-10)

- `requirements.txt`: `discord.py` **2.3.2 → 2.7.1**, and the separate legacy `discord==2.3.2`
  pin **deleted** (that shim package was never published past 2.3.2; `discord.py` provides the
  `discord` module itself).
- **2.7.1 then raised `RuntimeError: davey library needed in order to use voice`.** discord.py
  ≥2.7 hard-requires the `davey` package (Rust/OpenMLS impl of Discord's DAVE protocol) for voice
  — the check is unconditional in `VoiceClient.__init__` (`voice_client.py`), right next to the
  PyNaCl one, so there is no way to opt out. It ships in the `discord.py[voice]` extra.
- `davey==0.1.6` added to `requirements.txt`. cp39 `manylinux_2_17_x86_64` wheels exist (verified
  against PyPI's file listing), so it installs from a wheel on `python:3.9.13-slim` — **no Rust
  toolchain needed in the image**, and no `Dockerfile` change was required.

**Verified in the rebuilt container:** `davey 0.1.6`, `DAVE_PROTOCOL_VERSION 1`,
`has_nacl True has_dave True`, and
`VoiceClient.supported_modes == ('aead_xchacha20_poly1305_rtpsize', 'xsalsa20_poly1305_lite',
'xsalsa20_poly1305_suffix', 'xsalsa20_poly1305')`.

**Verified live in a real voice channel** — the first proof Discord voice works here at all:

```
Starting voice handshake... (connection attempt 1)
Voice handshake complete. Endpoint found: c-sea01-3ae6ea8a.discord.media:8443
Voice connection complete.
debug play: connected to General in 0.51s
```

**One** attempt, 0.51s, zero 4006s — against 5 attempts × 4006 burning ~27s before. The user
confirmed the audio was **audible** in the channel and the bot disconnected cleanly afterwards.
That clears Phase 3's outstanding acceptance criterion ("audible hard-coded track in a real VC;
clean disconnect") and, with it, the whole Discord-voice half of the stack: gateway voice
handshake, DAVE/encryption, UDP, `load_opus("libopus.so.0")`, and `FFmpegPCMAudio` piping.

Upgrade-risk note: 2.3.2 → 2.7.1 is a 4-minor jump. Changelog skim surfaced a voice rewrite in
2.4.0 and `abc.Messageable.pins()` becoming an async iterator in 2.6.0 (old `await` form still
works, now deprecated). Nothing found that breaks this bot's usage (`discord.Client`,
`app_commands.CommandTree`, `on_message`, `FFmpegPCMAudio`, `load_opus`), but the rest of the bot
has **not** been regression-tested on 2.7.1 — do that.

## 4. ✅ The debug state has been reverted

Was: `handle_play()` gutted down to a local-`test.mp3` detour, with the real Spotify flow below it
unreachable. **Now reverted** — `music/commands.py`'s `handle_play` is back to the real flow
(link check → `get_session` → `join_and_register_device` → "Ready! Open Spotify and select
**Discord Bot**..."), the `_debug_play_local_file` helper and every `Debug:N` message are gone, and
`test.mp3` is deleted from the repo and the image. Rebuilt and restarted on the reverted code.

⚠️ **`/run/discordbot.maintenance` IS STILL SET.** The watchdog is standing down, so a wedged bot
will **not** be auto-restarted. **This must be cleared:** `sudo rm /run/discordbot.maintenance`
(needs root; the agent has no passwordless sudo — ask the user). It self-clears on reboot.

## 5. Smaller findings

- **`main.py` intents bug:** `intents.all()` is called and its **return value discarded**
  (`Intents.all()` returns a *new* object; it does not mutate in place). That line is dead. It is
  **not** the voice bug — `Intents.default()` already enables `voice_states` — but it clearly
  does not do what it was written to do. Worth fixing.
- The image's `ENTRYPOINT` (`entrypoint.sh`) **ignores any command passed to `docker run`** and
  always execs `main.py`. To run a script in the image you **must** pass
  `--entrypoint python`. Getting this wrong silently starts a *second bot instance* — it happened
  once this session and was killed immediately.
- Running anything that needs port 8888 (the OAuth callback) requires stopping the production
  container first; nginx→127.0.0.1:8888 is the only path in from the internet.
- `py-spy` could not attach inside the container (needs `CAP_SYS_PTRACE`, not granted). Would
  require adding `cap_add` to `docker-compose.yml` if thread-level profiling is ever wanted.

## 6. Next steps, in order

Steps 1–3 of the original list (rebuild for `davey`, prove voice with `test.mp3`, revert the
debug detour) are **done** — see §3 and §4. What's left:

1. **Test the real Connect flow end to end** — this is now the only thing blocking the feature:
   `,play` → device appears in the Spotify app → transfer from the app → audio in the VC →
   pause/resume. With the dealer fix (§2) and the voice fix (§3) both in place this is finally
   reachable for the first time. **Watch the log for `Unhandled Connect endpoint` warnings** —
   that is the still-unverified assumption about Connect's JSON command shape (see Phase 5), and
   `on_request` logs every raw command unconditionally so this pass self-documents whether the
   assumed shape is right.
2. Clear `/run/discordbot.maintenance` (needs root — see §4).
3. Regression-check the non-Spotify parts of the bot on discord.py 2.7.1.
4. Commit. Everything from this session is still **uncommitted** on
   `claude/spotify-connect-bot-step-1-in130u`: `requirements.txt` (the discord.py/davey fix),
   `music/commands.py` (debug detour added then reverted — should end up a no-op vs `e29f31c`
   apart from that file's own committed debug block being removed), and this file.

Still-open items from earlier phases that this session did **not** touch: token refresh
(plan §5.5), the natural-end-of-track stale-state gap, and `put_connect_state` failing silently on
non-200.

---

## Where this stands

Branch: `claude/spotify-connect-bot-step-1-in130u`, based directly on `production`
(`d91273a`, the containerized/watchdog-supervised state — already includes the hosting work).

**Phases 1–5 of `SPOTIFY_CONNECT_PLAN.md` §13 were built:** data model & store, the audio pipeline
(creds → `Session` → `content_feeder` → ffmpeg → PCM), Discord voice (join/leave, `vc.play`),
OAuth link UX, and the Connect receiver (Mode A): the bot registers as a real Spotify Connect
device, and transfer/play/pause/resume from the user's own Spotify app are wired to actually
control the Discord voice playback. **Mode B (command-driven URI play, `,play <track>`,
`music/search.py`) has since been explicitly removed at the user's request — see "Scope change"
right below, read it before touching `,play` or anything URI/search-related.** Phase 0 (de-risk
experiments against a live Spotify Premium account) was explicitly **skipped** across all
sessions — it needs interactive/live credentials and a real running bot this sandbox doesn't
have — and is still open; see "Still open" below. **The user has said they'll do a manual final
pass covering everything that needs a real Spotify Premium account and a live bot** — what *was*
verified without one is detailed under each phase below. For Phase 5 specifically, that
verification is unusually deep given the stakes (see below — it caught and fixed two real bugs,
one in this bot's own new code and one in the librespot-python library itself) but it is still
not a substitute for actually watching a device appear in a real Spotify app and controlling it.

## Scope change: Mode B removed, Connect receiver (Mode A) only

**The user explicitly asked for search/Mode-B to be removed: "that is not required... I want you
to remove search functionality. Just have the receiver flow."** This is a deliberate, permanent
scope decision, not a temporary skip — don't reintroduce free-text search, direct-URI `,play
<track>`, or a "pending query" concept without the user asking again.

What changed, on top of everything Phase 1–5 built:
- **`music/search.py` deleted entirely** (it only ever resolved direct `spotify:track:...`
  URIs/URLs anyway — no free-text Web-API search was ever implemented, see the old Phase 4 notes
  below for why).
- **`,play` no longer takes any argument.** It now just: checks the caller is in a voice channel,
  links Spotify if needed (same OAuth paste-back flow as before, just without a query attached to
  the pending link), then joins the caller's voice channel and registers/reuses their
  `ConnectDevice` (`music/commands.py`'s `_join_and_register_device`, replacing the old
  `_join_and_play`-based flow for this command). **Nothing plays as a result of `,play` itself.**
  The reply now reads "Ready! Open Spotify and select **Discord Bot** as your playback device..."
  instead of "Now playing...".
- **Playback only ever starts via a Connect "transfer" command** from the user's own Spotify app
  (`ConnectCommandHandler._do_transfer`, unchanged from Phase 5) — i.e. the *only* remaining way
  to play a track is: user does `,play` to get the bot into their voice channel and registered as
  a device, then opens Spotify and picks that device, which sends the track URI to us via the
  dealer. This is exactly Mode A as specced, with Mode B's command-surface removed rather than
  just left unused.
- **`music/oauth_flow.py`**: dropped the `pending_query` field from `start_link()`/the pending-
  link dict entirely (was always `None` in practice once Mode B's argument went away). Pending
  entries now only carry `guild_id`/`voice_channel_id`, used purely to auto-join the right voice
  channel once linking completes via DM paste-back.
- **`music/commands.py`**: removed `note_manual_play` (existed only to seed
  `ConnectCommandHandler` state for a manually-chosen track, which no longer happens) and the old
  `_join_and_play`-based success path in `handle_play`/`handle_spotify_pasteback`. Added
  `_join_and_register_device`, shared by both. `_join_and_play` itself **stays** — it's still
  exactly what `_do_transfer` needs (join + immediately play a *known* track URI once Spotify
  tells us one via transfer), just no longer called from the manual `,play` path.
- **Nothing about `music/connect_device.py` or `ConnectCommandHandler`'s Connect-protocol
  internals changed** — the crosstalk-bug fix, transfer/pause/resume dispatch, thread↔asyncio
  bridge, and periodic state reporting are all exactly as Phase 5 left them and were re-verified
  (unit tests, including the real-`DealerClient` crosstalk check and the real-background-thread
  bridge test) after this change to confirm nothing regressed.
- **`music/playback.py` and `music/content_pipeline.py` are unaffected** — still needed (the
  Connect receiver's `_do_transfer` path uses `playback.play_track`, which uses the same
  ffmpeg-piping approach either way). `music/phase2_smoke_test.py`/`phase3_smoke_test.py` didn't
  reference search and needed no changes.
- **`commands/help.py`** updated to describe the new flow (no more "play a track" framing).
- **`SPOTIFY_CONNECT_PLAN.md` itself was not edited** — it's the original planning doc and still
  describes both Mode A and Mode B (Mode B as the earlier milestone, Mode A as the target); this
  file (`SPOTIFY_CONTEXT.md`) is where the "actually, just Mode A" decision lives. If a future
  session reads the plan first without reading this section, they'll get the wrong idea that
  Mode B should exist — **that's exactly why this section is first**, right after the summary.

Consequence for what's "next": **Phase 6 (Search & queue) as originally scoped is now largely
moot** — there's no `,play <query>` to search for, and "queue" only makes sense if something
enqueues tracks, which nothing does anymore (the Spotify app itself manages the user's queue;
transfer commands just tell us what's currently playing). If a real per-guild `GuildPlayer`
becomes useful later, it'd be to fix the "stale state after natural track end" gap (still present,
see Phase 5's "Known limitations" below) or to support skip/seek from the app — not for a
bot-side queue. Don't resurrect Phase 6 as originally scoped without checking with the user first.

## What was built (Phase 5)

Goal per plan §13: "`connect_device.py`: `PutStateRequest`, listeners, `connection_id`, command
loop, state reporting. Acceptance: device shows in the Spotify app; play/pause/skip/seek from the
app control the VC audio; the app UI reflects position/track."

### Critical finding: a real cross-user bug in librespot-python itself
Reading `librespot/core.py`'s `DealerClient` directly (not assumed): `__message_listeners`,
`__request_listeners`, and their locks are declared at **class-body scope**, and `__init__` never
assigns them on `self`. Every `DealerClient` instance therefore shares the exact same dict
objects. This bot creates one `Session`/`DealerClient` per linked Discord user — with the bug
left alone, a Connect command delivered on user A's dealer websocket would fan out to **every**
listener ever registered by **any** user's `DealerClient`, including user B's, since
`on_message`/`on_request` never receive anything identifying which session's socket the frame
arrived on. Left unfixed, this would have meant one user's Spotify Connect commands could reach
and control another user's Discord playback. **Verified the bug exists** with two real
(unmocked) `DealerClient` instances before writing any fix (`d1.__message_listeners['marker']`
was visible from `d2`). `music/connect_device.py`'s `_isolate_dealer_listener_state()` fixes it
by giving each dealer instance fresh dicts, called once per `ConnectDevice` construction; made
idempotent (only replaces a dict that's still the shared class-level object) after a test caught
that constructing a second `ConnectDevice` against an already-isolated dealer would otherwise
silently wipe out the first one's registrations. Both the bug and the fix are covered by
dedicated tests (see below) — this isn't a "should be fine" claim, it's demonstrated.

### Another packaging bug found (and worked around)
`librespot/proto/TransferState_pb2.py` (needed to parse Spotify's "transfer" command, i.e. what
fires when a user picks this device from their Spotify app) does `import ContextPlayerOptions_pb2`
— an old-style **bare** import left over from the generated-code's original Python 2 layout —
instead of a relative/package import. `from librespot.proto import TransferState_pb2` raises
`ModuleNotFoundError` outright. Same bug affects `Playback_pb2`, `Queue_pb2`, `Session_pb2`,
`Context_pb2`, `ContextPage_pb2`, `Canvaz_pb2` (checked: none of the others Phase 5 needs).
Worked around in `music/connect_device.py` by adding `librespot/proto`'s own directory to
`sys.path` once at import time (verified this makes the import succeed) — contained to this one
module, doesn't touch the installed package.

### `music/connect_device.py`
- `ConnectDevice(MessageListener, RequestListener)` — one per linked-and-playing member, wraps
  their `Session`:
  - Builds the initial `Connect.DeviceInfo`/`Capabilities` (fields verified against the actual
    installed `Connect_pb2` — `can_play`, `can_be_player`, `is_controllable`, `is_observable`,
    `supports_transfer_command`, `volume_steps`, etc. — cross-checked against the **reference
    field-filling pattern** in librespot-python's own `librespot_player/__init__.py`, a sketch
    that ships in the same GitHub repo but is dead code — never imported by the installed
    package, and its own listener classes never override `on_message`/`on_request` at all, just
    inherit the no-op base stubs. It's a useful reference for *what fields to fill*, not a working
    implementation to call into — confirms the plan's §2.3 claim that there's no finished
    receiver here.
  - Registers as a message listener on `hm://pusher/v1/connections/` (delivers the dealer
    `connection_id`, via the `Spotify-Connection-Id` header — needed for every `put_connect_state`
    call), `hm://connect-state/v1/connect/volume`, `hm://connect-state/v1/cluster`; and as a
    request listener on `hm://connect-state/v1/` (URIs taken from the same
    `librespot_player` reference).
  - On receiving the connection_id, immediately PUTs an initial `NEW_DEVICE` state — this is what
    makes the device appear in the user's Spotify app.
  - `on_request` dispatches by `command["endpoint"]`: `"transfer"` → parses a `TransferState`
    protobuf out of the command's base64 `data` field and calls `handler.on_transfer(track_uri,
    position_ms, is_paused)`; `"play"`/`"resume"` → `handler.on_resume()`; `"pause"` →
    `handler.on_pause()`; `"skip_next"`/`"skip_prev"`/`"seek_to"` → logged and reported as
    `DEVICE_DOES_NOT_SUPPORT_COMMAND` (no queue or seek support yet — Phase 6); anything else is
    logged in full and also reported as unsupported, **on purpose**, so real dealer traffic that
    doesn't match my assumptions about Spotify's Connect command shapes shows up clearly in logs
    instead of silently doing nothing.
  - Exceptions from `handler` methods are caught and reported as `UPSTREAM_ERROR` — a bad command
    can't crash librespot's dealer worker thread.
  - `put_state(reason, is_playing, is_paused, track_uri, position_ms)` builds and sends a
    `PutStateRequest`; safely no-ops (with a log) if called before a `connection_id` is known.
- **The Spotify Connect wire protocol for commands (the exact JSON shape behind
  `command["endpoint"]` and its args) is based on general community knowledge of the Connect/SpConn
  protocol (as implemented in projects like go-librespot), not on anything verified from source
  in this session** — librespot-python itself ships no working example of it (see above). This is
  the single biggest unverified assumption in Phase 5. `on_request` logs every raw command
  unconditionally before dispatch specifically so the first real session against a live account
  self-documents whether the assumed shape (`endpoint`, `data` for transfer) is actually right.

### `music/commands.py` — wiring Connect into the existing `,play` flow
- `ConnectCommandHandler` — implements the `on_transfer`/`on_resume`/`on_pause` interface
  `ConnectDevice` calls. These run on **librespot's dealer worker thread**, never the asyncio
  loop, so every Discord-facing action is scheduled via
  `asyncio.run_coroutine_threadsafe(coro, self.loop)` and waited on synchronously with
  `.result()` — safe because the calling thread isn't the loop thread, and it lets a real
  `SUCCESS`/`UPSTREAM_ERROR` propagate back to `ConnectDevice.on_request` (and from there, back
  to Spotify) instead of firing-and-forgetting.
  - `on_transfer`: looks up which voice channel the member is currently in by scanning **every
    guild the bot shares with them** (`_find_member_voice_channel` — a transfer command carries
    no Discord context at all, just a track URI, so this is the only way to find where to play
    it), joins/plays there, and starts a periodic state-report loop.
  - `on_resume`/`on_pause`: act on the voice client for whatever guild this member's session was
    last active in (`self.guild_id`, updated by both `on_transfer` and normal `,play`), then
    report state.
  - A background `_report_loop()` task calls `put_state(PLAYER_STATE_CHANGED, ...)` every 5s
    while a track is "current" for this member, computing position from a `time.monotonic()`
    baseline set whenever playback starts/resumes/pauses. This is what's meant to satisfy "the
    app UI reflects position/track" — it's a plain timer-based estimate (assumes real-time
    playback with no drift/buffering compensation), not something driven by actual audio-frame
    progress.
- `handle_play`'s existing success path (normal `,play`, no Connect command involved) now also
  calls `_ensure_connect_device(...)` and `handler.note_manual_play(guild_id, track_uri)` after
  starting playback, so a device registers and the app's UI/controls work even if the user never
  transfers to it — and so a pause/resume sent from the app *right after* a manual `,play` has
  somewhere to act (`guild_id`/`current_track_uri` would otherwise stay `None` until a transfer
  happened). **Wrapped in its own try/except** — a Connect-registration failure is logged but
  never blocks the "Now playing" reply; audio already started, that's the part that matters most.
  Same wiring added to `handle_spotify_pasteback`'s auto-play-after-linking path.
- `,spotify unlink` now also calls `_close_connect_device(member_id)`, which cancels the report
  task and unregisters the dealer listeners, alongside the existing session close.
- `session_manager.build_session()` now sets `device_name="Discord Bot"` and
  `device_type=Connect.DeviceType.SPEAKER` (previously left at librespot's own defaults,
  `"librespot-python"`/`COMPUTER`) — cosmetic, but it's what actually shows up in the user's
  Spotify app once a device is registered, so worth getting right. Also exported as
  `session_manager.DEFAULT_DEVICE_NAME` for `commands.py` to reuse.

### What was actually verified vs. not (Phase 5)
This phase had the highest risk of "looks plausible, is subtly wrong" of any phase so far — real
protocol code with real concurrency, and I can't run it against Spotify's actual dealer. So
verification went further than previous phases, specifically to catch the class of bug that
*would* be catchable without a live account:
- ✅ **Verified the actual library bug**: two unmocked `librespot.core.DealerClient` instances
  demonstrably share listener state before any fix; after
  `_isolate_dealer_listener_state()`, they don't (checked both message and request listener
  dicts). Also verified the fix is idempotent (a second isolate call on an already-isolated
  dealer doesn't wipe existing registrations) — this specific idempotency bug was caught by an
  earlier version of the test itself (it used one shared fake dealer across multiple
  `ConnectDevice`s and hit a real `KeyError` in `close()`), then fixed and re-verified.
- ✅ **Verified `ConnectDevice`'s protocol logic** end-to-end with a fake session/dealer: initial
  `NEW_DEVICE` `put_state` fires correctly once a `connection_id` arrives via the pusher message
  (with the right `device_info` fields); a **real** `TransferState` protobuf, constructed and
  base64-encoded exactly like a real "transfer" command's `data` field, correctly decodes and
  reaches `handler.on_transfer` with the right track URI/position/paused state; pause/resume
  dispatch correctly; unknown/unimplemented endpoints correctly return
  `DEVICE_DOES_NOT_SUPPORT_COMMAND`; a handler exception is caught and returns `UPSTREAM_ERROR`
  without crashing; `put_state` before a `connection_id` is known safely no-ops; `close()` removes
  listeners cleanly.
- ✅ **Verified the thread↔asyncio bridge for real**, not mocked: ran an actual `asyncio` event
  loop on its own background thread, called `ConnectCommandHandler.on_transfer`/`on_pause`/
  `on_resume` from a **different** thread (standing in for librespot's dealer worker thread), and
  confirmed the Discord-facing coroutine actually executed on the loop's thread (compared thread
  identities), that exceptions raised inside the coroutine propagate back across the thread
  boundary to the calling thread synchronously, and that position math advances correctly with
  real elapsed wall-clock time. **This caught a real bug**: `ConnectCommandHandler.close()`
  originally called `self._report_task.cancel()` directly — `asyncio.Task.cancel()` isn't
  documented as thread-safe, and the test (calling `close()` from a non-loop thread) exposed that
  the cancellation didn't reliably take effect. Fixed by routing it through
  `self.loop.call_soon_threadsafe(task.cancel)`; re-verified the task actually gets cancelled.
- ✅ **Verified the `,play` integration doesn't regress Phase 4**: re-ran (an expanded version of)
  Phase 4's mocked test suite against the Phase-5-modified `commands.py` — empty query, not-in-VC,
  unlinked, unsupported query, and session-build-failure paths all still behave identically.
  Additionally verified the new integration points: `_ensure_connect_device` is idempotent per
  member (doesn't rebuild `ConnectDevice` on every `,play`), `_close_connect_device` actually
  closes and removes both the handler and device, and — importantly — **a Connect-device
  registration failure never blocks the "Now playing" reply or the audio itself**, since it's
  wrapped in its own try/except separate from the playback try/except.
- ❌ **NOT verified, and can't be from this sandbox**: the actual JSON shape of real Spotify
  Connect commands (the biggest open risk, flagged above), whether the device genuinely appears
  in a real Spotify app, whether `put_connect_state` calls are accepted (any number of subtle
  protobuf-field mistakes would only surface as an HTTP error from Spotify's backend, which
  `ApiClient.put_connect_state` currently only logs a warning for — see "Known limitations"),
  and whether transfer/play/pause/resume from a real app actually drives the VC audio end to end.
  This is exactly what the user's manual pass needs to cover, and now that a device actually gets
  registered, it's also the first phase where that pass can meaningfully happen.

### Known limitations (not bugs, deliberate scope decisions)
- **No skip/seek/queue.** Explicitly deferred to Phase 6 (`GuildPlayer` queue) — `on_request`
  reports these as unsupported rather than pretending to handle them.
- **State reporting doesn't know when a track ends naturally.** `playback.py`'s `after` callback
  (fired when `content_pipeline`'s audio source runs out) doesn't currently notify
  `ConnectCommandHandler`, so if a track finishes without `,spotify unlink` or another Connect
  command happening, the periodic report loop keeps reporting the **last known** (now stale)
  playing state indefinitely. Wiring `playback.play_track`'s `after` into the handler is
  straightforward but is genuinely Phase 6 territory (queue/"what plays next" logic lives there)
  — flagging as a known gap rather than fixing it here.
- **`ApiClient.put_connect_state` only logs a warning on non-200 responses** (checked in
  `librespot/core.py`) rather than raising — so a malformed `PutStateRequest` (e.g. a protobuf
  field I got wrong, like `track.provider = "context"`, a value chosen from general Connect
  protocol familiarity rather than verified against source) would currently fail *silently* from
  this bot's perspective. Nothing to fix without live traffic to observe what actually gets
  rejected; noting it so it's not mistaken for "it worked" if the device never appears.
- **One `ConnectDevice`/one Spotify Connect device per linked member, not per guild/channel.**
  A member's librespot `Session` (and thus their Connect device identity) is created once and
  reused across guilds (see Phase 2/4 decisions) — the device shows as one persistent "Discord
  Bot" entry in their Spotify app regardless of which server they're using it from, not a
  per-channel device as plan §1.1 step 4's example ("Discord: #general") suggests. Simpler and
  consistent with the existing per-member session cache; revisit only if the user specifically
  wants per-channel device identities.

## What was built (Phase 4)

> **Superseded in part** — see "Scope change" above. This section is left as-is for history; the
> `pending_query`/track-auto-play/search pieces described below **no longer exist** in the
> codebase. What's still true: the OAuth paste-back mechanics (`start_link`/`parse_code`/
> `complete_link`, the keymaster client ID, the redirect URL choice, the credential-format
> finding). What's gone: `music/search.py`, auto-playing a query after linking, and `,play` taking
> any argument at all.

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

**Per the user's explicit direction (see "Scope change" above), Phase 6 — Search & queue as
originally scoped in `SPOTIFY_CONNECT_PLAN.md` §13 is not planned work anymore.** There's no
`,play <query>` to search for and no bot-side queue concept — the Spotify app itself is the
queue/search UI now; this bot is purely the receiver. Don't pick Phase 6 back up without checking
with the user first. What's actually still open:

- **The live verification gap is now the main thing left**, and it's more meaningful than before:
  with `,play` actually registering a Connect device, the user's manual pass can now test the
  real thing end-to-end (link → device appears in Spotify app → transfer → audio in VC →
  pause/resume from the app). `music/phase2_smoke_test.py` and `music/phase3_smoke_test.py` are
  still available for the lower-level pipeline checks. `ConnectDevice.on_request`'s unconditional
  raw-command logging means that pass will also surface whether the assumed Connect command
  shape (`endpoint`/`data` for transfer) is right — check the logs for any `"Unhandled Connect
  endpoint"` warnings.
- **The natural-end-of-track gap flagged under Phase 5** ("Known limitations" above) is still
  present: `playback.play_track`'s `after` callback doesn't notify `ConnectCommandHandler`, so if
  a track finishes without `,spotify unlink` or another Connect command happening, the periodic
  state-report loop keeps reporting stale "still playing" state. Worth fixing on its own terms now
  (small, contained — wire `after` to call something like `handler.on_track_ended()`), not as part
  of a queue system that no longer exists.
- **Token refresh (plan §5.5) is still unresolved** — see "Consequence for reuse & refresh" under
  Phase 2. A live Connect device plausibly stays registered far longer than a single `,play`
  call, so this is more likely to actually bite now than in earlier phases. Still no auto-refresh;
  `session_manager.get_session()` just raises and tells the user to re-link on an expired token.
- **Phase 0 (de-risk) was never run, and neither were Phases 2/3/4/5's own live acceptance
  criteria** (a real PCM file; an audible track in a real VC; a fresh user actually linking and
  hearing their track; a device appearing in a real Spotify app and responding to app controls) —
  see each phase's "What was actually verified vs. not" above. All the same underlying gap: no
  live Spotify Premium account or running bot available in this sandbox. **The user has said
  they'll do a manual final pass to cover this.** Phase 4/5's own logic was verified unusually
  thoroughly with mocks and, for Phase 5, real (unmocked) library objects where it mattered most
  (see above) — including catching and fixing two real bugs (one in librespot-python itself, one
  in this bot's own thread-safety) that only surfaced *because* of that testing, and this was
  re-verified after the Mode-B removal to confirm nothing regressed. None of that substitutes for
  watching a real device show up in a real Spotify app.

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
- `music/search.py` was removed entirely and `,play` takes no argument — the user explicitly
  asked for search/Mode-B to go, see "Scope change" near the top of this file. Don't reintroduce
  it without the user asking again.
- Session/credential caching (`session_manager._sessions`) is a plain in-process dict, not
  persisted — acceptable for now since `SpotifyLink.credentials` in the DB is the durable copy
  and a session gets rebuilt from it on demand; revisit only if Phase 5's dealer connections need
  to survive bot restarts more gracefully than "rebuild from stored creds."
- `music/connect_device.py` always calls `_isolate_dealer_listener_state()` on a session's dealer
  before registering listeners — **required**, not optional hardening; without it, multi-user
  Connect state is actively broken (see Phase 5's "critical finding"). Don't remove it as
  "unnecessary defensiveness" without re-reading why it's there.
- One `ConnectDevice` per linked member (not per guild/channel), cached alongside their session
  in `music/commands.py`'s `_connect_devices`/`_connect_handlers`, torn down together on
  `,spotify unlink`. A member's Spotify Connect device identity is stable across guilds, matching
  the existing per-member session cache — don't build per-channel device identities without a
  specific reason to.
- `ConnectDevice`/`ConnectCommandHandler` are deliberately split: `connect_device.py` stays
  Discord-free (mirrors `session_manager.py`/`content_pipeline.py`'s separation), and all
  Discord-specific state (which guild, which voice client, bridging librespot's worker thread to
  the asyncio loop) lives in `commands.py`'s `ConnectCommandHandler`. Keep new Connect-driven
  actions on that side of the boundary.
