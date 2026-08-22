# LIBRESPOT_RUST_PLAN.md — replacing librespot-python with the Rust librespot binary

**Written:** 2026-08-10, at the end of a live debugging session.
**Revised:** 2026-08-15 — §3.3, §3.4, §5.2, Step 0, Step 1, Step 2, Step 4 and Part 6 all changed
after reading the librespot v0.8.0 source and proving the token half of the flow live. §5.2's
old "Option A vs Option B" recommendation was **wrong** and is now replaced.
**Branch:** `claude/spotify-connect-bot-step-1-in130u` (based on `production`).
**Audience:** a fresh agent picking this up cold, plus the user.

## Status at last edit (2026-08-15)

| Step | State |
|---|---|
| 0 — spike | ✅ **PASSED 2026-08-15.** Device appeared in the user's Spotify app, was selectable, and played real audio at the correct rate |
| 1 — binary in the image | ✅ **DONE 2026-08-15.** `rust:slim-bullseye` build stage; `docker exec discordbot librespot --version` works and `--backend ?` lists `pipe`. Bot redeployed and healthy, 0 tracebacks |
| 2 — supervisor | ✅ **DONE 2026-08-15** (`music/librespot_process.py`). 10 spawn/teardown cycles: no orphans, no fd leak (4→4), registry clean, process cap enforced, restart-with-backoff exercised. Live spawn-to-registered-device not yet re-verified through this code — needs a fresh credential |
| 3 — audio bridge | ✅ **DONE 2026-08-15** (`music/pcm_source.py`). Starved source emits silence not `b''`; byte-exact frames; 50 frames no drift; partial tail never torn; bounded writer provably blocks (the backpressure that paces librespot) |
| 4 — link UX | ✅ **BUILT 2026-08-15** (`music/oauth_flow.py` + `music/spotify_auth.py` + `music/credentials.py`). DM paste-back; librespot-python gone. **Not yet exercised live** |
| 5 — wiring + deletion | ✅ **BUILT 2026-08-15** (`music/commands.py`, `music/playback.py`, `main.py`). Old stack deleted, `librespot` dropped from `requirements.txt`, image rebuilt, bot deployed healthy with 0 tracebacks. **End-to-end acceptance still unverified — needs the user** |
| 6 — regression + cleanup | not started |

**What is left before this feature can be called done:** one live pass by the user — `,play` →
link → paste back → pick the device in Spotify → hear audio in the voice channel. Everything up to
that point is verified; that specific chain has never been run through this code.

**Step 0 evidence (all live, real Premium account, 2026-08-15):**

- `successfully put connect state for 3d66146a… with connection-id YzU4NDQyYWU…` — the Connect
  device registers. librespot-python never once got here across nine bugs.
- The user confirmed **"Discord Bot" appears in their Spotify app and is selectable**, and that
  playback runs at normal speed through the paced pipeline.
- Audio measured at the end of the real chain (librespot → ffmpeg 44.1k→48k → 20ms-clocked
  reader): **98.4% non-silent, peak 32348/32767, RMS 5712**, 5.0s of audio per 5.0s wall clock,
  **zero short reads**.
- The refresh grant works with no user interaction (`expires_in=3600`, refresh token not rotated) —
  §5.2 decision 1, end to end.

**Four findings that change how we build it** (details in §5.2 and the Step notes):

1. The token must be minted with **keymaster**, not our dev app — login5's stored-credential login
   is first-party-only, proven by a three-way test in §5.2. A `--client-id` patch was built and
   does not rescue it.
2. Keymaster **rejects our hosted HTTPS redirect** (`redirect_uri: Not matching configuration`), and
   its whitelist is Spotify's. **The link UX therefore reverts to DM paste-back** — see §5.2.
3. Pass the token via **`LIBRESPOT_ACCESS_TOKEN`**, never `--access-token`: argv is world-readable
   through `/proc`, and librespot only redacts it in its own logs. Verified: with the env var set,
   `/proc/<pid>/cmdline` carries no token.
4. Use **`--volume-ctrl fixed --initial-volume 100`**. The default softvol `Log(60.0)` curve at the
   50% the app reports attenuates ~30 dB — measured peak 1037/32767 before, 32348 after.

## How to read this repo's docs (there are several, and they conflict)

| File | What it is | Trust it? |
|---|---|---|
| `CLAUDE.md` | How the bot is hosted/supervised day to day. Unrelated to this feature. | ✅ Yes |
| `CONTEXT.md` | Backstory of the *deployment* project. Unrelated to this feature. | ✅ Yes, but off-topic |
| `SPOTIFY_CONNECT_PLAN.md` | The original feature plan. Describes Mode A + Mode B. | ⚠️ Mode B was cut; the librespot-python architecture it assumes is being replaced by **this** document |
| `SPOTIFY_CONTEXT.md` | Session-by-session state of the librespot-python attempt. | ⚠️ Accurate history, **obsolete architecture** |
| **`LIBRESPOT_RUST_PLAN.md`** (this file) | The plan going forward. | ✅ **Start here** |

Read this file first. Read `SPOTIFY_CONTEXT.md` second, for history and for the list of things
already proven — but do not implement from it.

---

# Part 1 — How we got here

## 1.1 The goal (unchanged)

A Discord user runs `,play`, the bot joins their voice channel and appears in **their own Spotify
app** as a Connect device named "Discord Bot". They pick it as the playback target, and their music
plays into the Discord voice channel. Play/pause/skip are driven from the Spotify app, not from bot
commands.

This is "Mode A", a **Connect receiver**. Free-text search and `,play <track>` ("Mode B") were
explicitly cut by the user and must not be reintroduced:

> "that is not required... I want you to remove search functionality. Just have the receiver flow."

Spotify **Premium is required**. `,play` takes no arguments.

## 1.2 What was built, and why it's being thrown away

Phases 1–5 implemented the whole thing in Python against
[`librespot-python`](https://github.com/kokarare1212/librespot-python) pinned at commit
`18104622b3be02062f1f8abe8dafc396413e9784` (v0.0.10). The audio half works. **The Spotify Connect
half never has, not once.**

Nine distinct defects were found in that library's Connect/dealer code during live debugging:

| # | Defect | Resolution |
|---|---|---|
| 1 | `librespot/proto/*_pb2.py` use bare Python-2 style imports; `from librespot.proto import TransferState_pb2` raises `ModuleNotFoundError` | `sys.path` hack |
| 2 | `DealerClient.__message_listeners`/`__request_listeners` declared at **class** scope, never assigned in `__init__` — every instance shares one dict, so one user's Connect commands reach another user's handler | monkeypatch (`_isolate_dealer_listener_state`) |
| 3 | `DealerClient.connect()` builds a `WebSocketApp` but never assigns `on_open`/`on_message`/`on_error` and never calls `run_forever()` — the socket **cannot** open | monkeypatch |
| 4 | `wait_for_listener()` has its condition **inverted** — it blocks when listeners exist and proceeds when they don't, deadlocking the websocket reader thread on the first frame | monkeypatch |
| 5 | `handle_message()` calls `base64.b64decode(payloads)` but Spotify sends `payloads` as a JSON **array** of base64 chunks → `TypeError`, swallowed by the websocket lib | monkeypatch |
| 6 | `__get_headers()` is annotated `-> CaseInsensitiveDict` but returns the raw JSON dict; lowercase `content-type`/`transfer-encoding` miss their branches | monkeypatch |
| 7 | `ApiClient.put_connect_state` only **logs a warning** on a non-200 — a malformed state PUT fails silently | unfixed |
| 8 | No token refresh: `Session` takes a point-in-time access token, so the user must re-link **every hour** | unfixed |
| 9 | `Session.reconnect()` re-rolls a random access point and dies on a bad one, killing the packet-receiver thread | unfixed |

Bugs 3, 4 and 5 were each discovered by fixing the previous one — a chain with no visible end. This
is the signature of code that was never executed upstream.

Two of these deserve special mention because they will mislead you if you read the older docs:

- **Bug 4 made the whole thing a race.** With a *fresh* session, the dealer connects during
  `Session.authenticate()`, the pusher frame arrives while the reader is parked in `wait()`, then
  `ConnectDevice` registering its listeners calls `notify_all()`, which wakes the reader and the
  frame dispatches — the device appears. With a *cached* session, registration finishes first
  (~0.01s), the socket opens a second later, and the frame hits an already-blocked reader that
  nothing will ever wake — the device never appears. **Same code, opposite outcome.** An earlier
  session's note claiming "device now registers ✅" was that race landing favourably once.
- **The access points are a coin flip.** `apresolve.spotify.com` returns a pool and librespot picks
  one at random with no retry. Measured from this host, 2 of 6 actively refuse TCP
  (`ap-guc3:443`, `ap-gew4:80`), so ~1 in 3 logins died with `ConnectionRefusedError`. Do not
  mistake this for a firewall or an outage. (Worked around in `build_session`, but librespot's
  internal `reconnect()` has the same bug and is not reachable from there.)

## 1.3 What IS proven — do not re-litigate any of this

This is the most valuable part of this document. All of it was verified **live**, against a real
Spotify Premium account and the real bot, on 2026-08-09/10.

1. **Discord voice works.** This was the hard blocker for a long time and it is now solved.
   - `discord.py==2.3.2` offered only retired encryption modes (`xsalsa20_poly1305*`), so Discord
     closed every voice IDENTIFY with **4006**, 5 retries deep, ~27s, every time.
   - Fixed by `discord.py` **2.3.2 → 2.7.1** plus **`davey==0.1.6`** (discord.py ≥2.7 hard-requires
     it for voice; the check is unconditional in `VoiceClient.__init__`). The legacy `discord==2.3.2`
     shim pin was deleted. cp39 manylinux wheels exist for davey, so **no Rust toolchain is needed
     for it** and the `Dockerfile` needed no change.
   - Verified in-container: `davey 0.1.6`, `DAVE_PROTOCOL_VERSION 1`, `has_nacl True has_dave True`,
     `supported_modes` leading with `aead_xchacha20_poly1305_rtpsize`.
   - Verified live: **one** handshake attempt, 0.51s, audible audio in a real voice channel, clean
     disconnect. Phase 3's acceptance criterion is met.
2. **The OAuth link flow works.** Auth URL → user authorizes → hosted HTTPS callback catches the
   code → token exchange succeeds. `music/callback_server.py` and `music/oauth_flow.py` are sound.
3. **librespot-python's *audio* path works.** `Session` authenticates against a real account
   (`Authenticated as 31gfmisimhdtf6sqd4627uhmmtq4!`), `content_feeder().load()` streams real
   Ogg/Vorbis, ffmpeg decodes it to correct PCM (1,918,924 bytes vs 1,920,000 expected for 10s;
   89.8% non-silent). **This is what we are replacing anyway** — noted so you know the *concept* is
   sound and any new failure is in the new plumbing, not in the idea.
4. **`ensure_opus_loaded()` is required.** discord.py's `ctypes.util.find_library('opus')` returns
   `None` on this slim image even with `libopus0` installed; `discord.opus.load_opus("libopus.so.0")`
   fixes it. Keep this. Without it, voice silently produces nothing.
5. **The entrypoint ignores `docker run` commands.** `entrypoint.sh` always execs `main.py`. To run
   a script in the image you **must** pass `--entrypoint python`. Getting this wrong silently
   starts a **second bot instance** — it has already happened once. Discord bots must be singletons.

## 1.4 One bug in *our* code, still unfixed

`music/commands.py:176`, `_ensure_connect_device()`:

```python
device = _connect_devices.get(member_id)
if device is not None:
    return device          # keyed by member only — never checks session identity
```

After a re-link the user has a **new** `Session` with a **new** dealer, but this returns the
`ConnectDevice` bound to the **old** one, so the new dealer never gets listeners registered. Only
cleared by `,spotify unlink`. This is *our* bug, not librespot's.

It becomes moot under the new architecture (the whole module goes away), but it is recorded here
because it explains the final observed failure at 05:55:13 on 2026-08-10: the `connection_id` frame
arrived correctly and was logged, but nothing was listening on that dealer.

---

# Part 2 — Where we are right now

## 2.1 Tree state (all uncommitted, on `claude/spotify-connect-bot-step-1-in130u`)

```
 M SPOTIFY_CONTEXT.md      history + the new bug findings
 M music/commands.py       debug detour added then fully reverted (net: -24 lines vs HEAD)
 M music/connect_device.py + _patch_dealer_wait_for_listener, _patch_dealer_handle_message,
                             _patch_dealer_handle_request  (bugs 4/5/6)
 M music/session_manager.py AP_CONNECT_ATTEMPTS retry loop (bug: random AP)
 M requirements.txt        discord.py 2.7.1, davey 0.1.6, legacy `discord` pin removed  ← KEEP
 D test.mp3                debug fixture, deleted
```

**`requirements.txt` is the one change that must survive the rewrite.** Everything else in
`music/` is a candidate for deletion.

Nothing is committed. Decide with the user whether to commit this as a "here's what we learned"
checkpoint before starting, or to branch fresh from it.

## 2.2 Runtime state

- Container `discordbot` is **up and healthy** on discord.py 2.7.1 + davey.
- ⚠️ **`/run/discordbot.maintenance` IS STILL SET.** The watchdog is standing down, so a wedged bot
  will not be auto-restarted. Clearing it needs root and the agent has no passwordless sudo —
  **ask the user to run `sudo rm /run/discordbot.maintenance`.** It self-clears on reboot.
- The user's Spotify token has expired again (they expire hourly — bug 8). Expect to re-link.

## 2.3 Non-negotiable operational rules

- **Rebuild after every code change.** Code is baked into the image (`COPY . .`); there is no bind
  mount and no hot reload. `docker compose build && docker compose up -d`.
- **One instance only.** Check `docker ps` before starting anything.
- **DB helpers import `sync_to_async` from `helpers.db`**, never `asgiref.sync`. See `CLAUDE.md` §3.
- Logs: `tail -f /root/discordbot/logs/bot.log` or `docker logs -f discordbot`.
- Anything needing port 8888 (the OAuth callback) requires stopping the production container first;
  nginx → `127.0.0.1:8888` is the only path in from the internet.

---

# Part 3 — Target architecture

## 3.1 The core idea

Stop implementing the Spotify Connect protocol. Run the **reference implementation** as a child
process and consume its PCM output. librespot (Rust) is what spotifyd and Raspotify are built on;
"appear as a Spotify speaker" is precisely its job, exercised by large numbers of users daily.

**One `librespot` process per linked Discord user.** Each registers its own Connect device against
that user's account.

## 3.2 The data path — it is *shorter* than what we have today

Today, Python is the byte-pump. `FFmpegPCMAudio(source, pipe=True)` spawns a `_pipe_writer` daemon
thread (`discord/player.py:195`) that reads from librespot-python's stream object and writes into
ffmpeg's stdin:

```
Spotify CDN → librespot-python (decrypt, in-process)
            → Python object .read()
            → discord.py _pipe_writer THREAD          ← Python touches every byte
            → ffmpeg (Ogg/Vorbis → PCM)
            → Python .read() 3840-byte frames         ← Python again
            → opus → UDP
```

Target:

```
Spotify CDN → librespot process (decrypt AND decode → raw PCM)
            → OS pipe                                  ← kernel; Python NOT involved
            → ffmpeg (resample 44.1kHz → 48kHz)
            → Python .read() 3840-byte frames
            → opus → UDP
```

The trick is handing ffmpeg a real file descriptor:

```python
librespot = subprocess.Popen(
    [LIBRESPOT_BIN, "--backend", "pipe", "--format", "S16", ...],
    stdout=subprocess.PIPE)

ffmpeg = subprocess.Popen(
    ["ffmpeg", "-loglevel", "warning",
     "-f", "s16le", "-ar", "44100", "-ac", "2", "-i", "pipe:0",
     "-f", "s16le", "-ar", "48000", "-ac", "2", "pipe:1"],
    stdin=librespot.stdout,        # kernel wires them together
    stdout=subprocess.PIPE)
librespot.stdout.close()           # ffmpeg owns the read end; librespot gets SIGPIPE on exit

vc.play(SomeAudioSource(ffmpeg.stdout))
```

ffmpeg exists **only** to resample: Spotify decodes at 44.1kHz, Discord requires 48kHz stereo
s16le. librespot has no `--sample-rate` option (confirmed against its `main.rs`).

## 3.3 Verified librespot CLI facts

Checked against librespot's actual `src/main.rs` on the `dev` branch and its CHANGELOG, 2026-08-10.
Latest release **v0.8.0 (2025-11-10)**.

| Flag | Meaning | Note |
|---|---|---|
| `--backend pipe` / `-B` | write raw PCM instead of using a sound card | added v0.4.0; `stop` implemented in v0.4.2 |
| `--device` / `-d` | pipe backend target | **verify with `--device ?`** whether omitting it means stdout |
| `--format S16` / `-f` | `{F64\|F32\|S32\|S24\|S24_3\|S16}`, default `S16` | S16 is what we want |
| `--bitrate 320` / `-b` | `{96\|160\|320}`, default 160 | Premium → use 320 |
| `--name "Discord Bot"` / `-n` | device name shown in the Spotify app | |
| `--device-type speaker` / `-F` | displayed device type, default already `speaker` | |
| `--enable-oauth` / `-j` | "Perform interactive OAuth sign in." | see §5.2 — **we do not use this** |
| `--access-token` / `-k` | "Spotify access token to sign in with." | **this is the one we use** — see §5.2 |
| `--oauth-port` / `-K` | oauth redirect server port, default **5588** | v0.7.0 removed the loopback-only restriction on `redirect_uri` |
| `--system-cache` / `-C` | "Path to a directory where system files (**credentials**, volume) will be cached" | **this is the per-user credential store** |
| `--cache` / `-c` | audio file cache | |
| `--disable-audio-cache` / `-G` | don't cache audio | probably want this — disk hygiene |
| `--cache-size-limit` / `-M` | cap audio cache (`16G` etc.) | if audio cache is kept |
| `--disable-discovery` / `-O` | disable zeroconf discovery | **want this** — the user's phone is not on this LAN |
| `--onevent PROGRAM` / `-o` | run PROGRAM on a playback event | how we learn play/pause/track changes |
| `--emit-sink-events` / `-Q` | also fire `--onevent` around sink open/close | useful for start/stop detection |

**Auth situation (rewritten 2026-08-15 after reading the v0.8.0 source — supersedes the original
paragraph here):** password auth is gone (`main.rs` exits with "Password authentication no longer
supported, use OAuth"). But `--enable-oauth` is **not** the only way in: `--access-token` accepts a
token obtained any way you like, and librespot's own OAuth path does nothing more than fetch a
token and call the same `Credentials::with_access_token()` (`main.rs:1964-1968`). We already have a
working web OAuth flow that produces exactly such a token, so we use `--access-token` and never
touch `--enable-oauth`. See §5.2.

Sources: [librespot CHANGELOG](https://github.com/librespot-org/librespot/blob/dev/CHANGELOG.md),
[librespot `src/main.rs`](https://github.com/librespot-org/librespot/blob/dev/src/main.rs),
[librespot on crates.io](https://crates.io/crates/librespot),
[librespot-oauth](https://lib.rs/crates/librespot-oauth)

## 3.4 What survives, what dies

**Survives:**
- `requirements.txt` (discord.py 2.7.1 + davey) — the voice fix
- `storage/models.py` `SpotifyLink` + migration `0047` — **unchanged and now more important**:
  `credentials` keeps holding the OAuth JSON, and its `refresh_token` is what every spawn mints
  from (§5.2). No migration needed; we just define the blob's shape ourselves instead of inheriting
  `OAuth.save_creds()`'s.
- `helpers/spotifyStore.py`
- `music/playback.py`'s `ensure_opus_loaded()` and `join()`/`leave()`
- `main.py` routing, `commands/help.py`
- `music/callback_server.py` — **yes, definitely** (§5.2 keeps our own OAuth flow)
- `music/oauth_flow.py` — survives in shape, but every `librespot.*` import goes. Roughly 40 lines
  to replace: PKCE verifier/challenge (`secrets` + `hashlib`), the code→token exchange, and the
  refresh call. All plain `requests` POSTs to `accounts.spotify.com/api/token`; `requests` is
  already a dependency. `build_auth_url()` already hand-builds the authorize URL — it currently
  only borrows the PKCE challenge from librespot. **Persist a rotated `refresh_token`** when the
  response carries one (it didn't on 2026-08-15, but Spotify is entitled to rotate).

**Dies:**
- `music/connect_device.py` (all 6 monkeypatches with it)
- `music/content_pipeline.py`
- most of `music/session_manager.py`
- `ConnectCommandHandler` and the dealer-thread↔asyncio bridge in `music/commands.py`
- `music/phase2_smoke_test.py`, `music/phase3_smoke_test.py`
- the `librespot` Python dependency and its transitive pins

---

# Part 4 — Steps

Each step has an acceptance criterion. **Do not proceed past a failing one.**

## Step 0 — Spike: does the device even appear? (do this first, write no bot code)

The single highest-value experiment. librespot-python failed this nine bugs running; find out in
minutes whether Rust librespot succeeds.

**Revised 2026-08-15.** The OAuth dance this step originally described is gone — we mint a token
from the stored refresh token instead (§5.2), so Step 0 needs the user only for the final "is it
in your Spotify app?" check.

1. Get a `librespot` binary. **There are no prebuilt binaries** — the v0.8.0 GitHub release ships
   zero assets, so it must be cargo-built. The exact invocation that works (all three flags are
   load-bearing, see below):
   ```
   cargo install librespot --version 0.8.0 --locked \
         --no-default-features --features rustls-tls-webpki-roots --root /out
   ```
   - `--locked` — without it, `librespot-core`'s build script fails to compile: `vergen-gitcl`
     floats to 1.0.8 and no longer satisfies `vergen_lib::entries::Add`.
   - `--features rustls-tls-webpki-roots` — `--no-default-features` alone also drops TLS, and
     `librespot-oauth` has a compile-time check demanding one of the three TLS features. rustls
     additionally avoids OpenSSL, which matters in Step 1.
   - The `pipe` backend is **not** feature-gated (it isn't in `Cargo.toml`'s `[features]` at all),
     so `--no-default-features` keeps it while dropping rodio/ALSA. Confirm with `--backend ?`.
2. Mint a fresh access token from the stored refresh token (no user interaction — POST
   `grant_type=refresh_token` to `accounts.spotify.com/api/token`).
3. Run it by hand against the user's account:
   ```
   librespot --name "Discord Bot" --device-type speaker \
             --backend pipe --format S16 --bitrate 320 \
             --disable-discovery --disable-audio-cache \
             --access-token "$(cat access_token.txt)" > /tmp/out.pcm
   ```
   No `--system-cache` — decision 1 in §5.2 means we always supply a fresh token.

**Acceptance: MET 2026-08-15.** See the status block at the top of this file for the evidence.

⚠️ **Do not redirect librespot's stdout to a plain file and judge playback by it.** The pipe
backend has no clock; pacing comes entirely from backpressure at the read end. Writing to a file
never blocks, so librespot decodes flat out and races through the queue — 392 MB (~37 min of
audio) in 6.5 min of wall clock, every track "finishing" in under a second. From the user's Spotify
app this looks exactly like "it is skipping through songs at a very fast rate", and it is *not* a
librespot bug. Test with a consumer that reads on a real-time clock (`paced_reader.py` in the
spike scratchpad reproduces discord.py's 3840-bytes-per-20ms cadence).

## Step 1 — Get the binary into the image reproducibly

Multi-stage build in `Dockerfile`:

```dockerfile
FROM rust:slim AS librespot-build
RUN apt-get update && apt-get install -y --no-install-recommends pkg-config build-essential
RUN cargo install librespot --version 0.8.0 --locked \
        --no-default-features --features rustls-tls-webpki-roots --root /out

FROM python:3.9.13-slim
...
COPY --from=librespot-build /out/bin/librespot /usr/local/bin/librespot
```

Pin the version, and keep `--locked` and the rustls feature — see Step 0 for why each is required.
The `pipe` backend is not feature-gated, so it survives `--no-default-features`.

⚠️ **glibc mismatch — RESOLVED, but the stanza above is what NOT to do.** `rust:slim` is Debian
**bookworm** (glibc 2.36); `python:3.9.13-slim` is Debian **bullseye** (glibc 2.31). Verified
2026-08-15 by running the bookworm-built binary inside the real runtime image:

```
/x/librespot: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.32' not found
                                               version `GLIBC_2.33' not found
                                               version `GLIBC_2.34' not found
```

**Fix applied: build stage is `rust:slim-bullseye`.** That tag is Rust 1.97, comfortably above
librespot 0.8.0's MSRV of 1.85 (`rust-version = "1.85"`, `edition = "2024"`), so matching the
runtime's Debian release is simpler than the musl-static alternative and needs no extra toolchain.
A musl build stays available as a fallback if the runtime image ever moves.

Resource note: this host is 2 cores / 3 GB RAM. Build with `CARGO_BUILD_JOBS=1` and a `--memory`
cap, or the OOM killer will pick the fattest process on the box — which is the bot itself (it
carries the ML imports from `automod/nsfw.py`).

**Acceptance:** `docker exec discordbot librespot --version` works and `--backend ?` lists `pipe`.
Note the build stage adds several minutes to a cold build; it is cached thereafter.

## Step 2 — Process supervisor (`music/librespot_process.py`)

One class owning one user's librespot process: spawn, health, restart, teardown. Keyed by
`member_id`. Must never leak processes — a leaked one keeps a Connect device alive in the user's app
and holds their credentials open.

Requirements:
- **Mint a fresh access token immediately before every spawn** (§5.2 decision 1), including every
  restart. This is not optional hardening — it is load-bearing, see the next bullet.
- **Restart on exit, with backoff.** `main.rs:2042-2052` reconnects a dropped spirc using the
  *original* `last_credentials` — i.e. the access token it was started with — and nothing ever
  refreshes that in-memory value. So a process alive longer than the token's hour re-authenticates
  with a dead token on the first network blip and `exit(1)`s. That exit is our respawn signal, and
  respawning mints a new token, which is why the cycle is self-healing. librespot also `exit(1)`s
  when its own reconnects exceed `RECONNECT_RATE_LIMIT`, so **our supervisor needs its own backoff**
  or this becomes the fork bomb §5.3 warns about.
- **No `--system-cache`.** Nothing needs it under this design (device identity comes from
  `device_id(&connect_config.name)`, `main.rs:1540`, not the cache), and a populated cache is a
  full-account credential sitting on disk for no benefit. If it is ever reintroduced: mode 700.
- capture stdout as the PCM stream, **stderr to the bot log** (this is your only visibility)
- `terminate()` → wait → `kill()` on teardown; reap on `,spotify unlink` and on idle
- do not run the spawn on the asyncio loop; `subprocess.Popen` is fast but the surrounding waits are
  not — reuse `session_manager.SPOTIFY_EXECUTOR` or an equivalent

**Acceptance:** spawn/teardown 10 times in a row, `ps` shows no orphans, no fd leaks.

### Architecture change to Steps 2+3 (decided 2026-08-15, from spike measurements)

The plan originally had the `AudioSource` read straight from ffmpeg's stdout. **Don't** — it makes a
librespot restart (which Step 2 *requires*, see the mint-per-spawn bullet) tear the fd out from
under a live `vc.play()`. Instead:

- **Step 2 owns a bounded PCM buffer and a pump thread.** The pump reads ffmpeg's stdout and writes
  into the buffer. When librespot dies it rebuilds the whole chain, with backoff, and keeps filling
  the *same* buffer — so a restart is invisible to Discord.
- **Step 3 reads only from that buffer**, never from an fd.

**The buffer MUST be bounded and its writer MUST block when full.** That is not a memory
optimisation — it is what preserves the backpressure that paces playback. An unbounded (or
non-blocking) buffer removes the backpressure and librespot races through the queue at decode speed,
which is precisely the "skipping through songs very fast" failure observed in the spike.

## Step 3 — Audio bridge (`music/pcm_source.py`) — the one genuinely new piece

A `discord.AudioSource` that reads 3840-byte frames from ffmpeg's stdout. **This needs real care.**

**Confirmed empirically 2026-08-15**, not just predicted: across 272s of a registered-but-idle
device, librespot emitted **3840 bytes total** — i.e. nothing. Once playing, the same reader saw
5.0s of audio per 5.0s of wall clock with **zero short reads**, so the backpressure pacing in §3.2
is real and the buffer only has to cover the idle/transition case.

`discord.PCMAudio.read()` returns `b''` on a short read, and discord.py treats `b''` as
end-of-track and stops playback. With `--backend pipe`, librespot writes **nothing** while paused
or idle, so:
- a blocking pipe read → the AudioPlayer thread stalls
- a non-blocking short read → discord.py thinks the track ended and disconnects

Neither is acceptable. Implement instead: a reader thread filling a bounded buffer, and a `read()`
that returns a full frame from the buffer, or **3840 bytes of silence** on underrun. That keeps the
voice connection alive across pauses and track changes. Roughly 30–40 lines.

Also decide the end condition: silence forever means `vc.play()` never finishes, which is
*correct* for a Connect receiver (the session lasts as long as the user wants the device), but the
bot must still disconnect on idle timeout / empty channel / `,spotify unlink`.

**Acceptance:** unit-test the source against a fake pipe — starve it and confirm it emits silence
rather than `b''`; feed it a burst and confirm frame alignment (multiples of 3840) with no drift.

## Step 4 — OAuth / linking UX

The design is settled — see §5.2. What's left to build: rewrite `music/oauth_flow.py` without
`librespot.*` (PKCE, exchange, refresh), widen `SCOPES` to librespot's list ∩ valid-third-party,
and mint-on-spawn in the Step 2 supervisor. Existing linked users re-link once, because the scope
set changes.

**Acceptance:** a fresh Discord user runs `,play`, gets a link, authorizes, and librespot spawns
with a token minted from their brand-new refresh token. A **second** `,play` an hour later spawns
with no interaction at all, from a token minted at that moment. That last part is the proof bug 8
is dead.

## Step 5 — Wire into `,play` and delete the old stack

`,play` becomes: caller in a VC? → linked (cache dir exists)? if not, issue link → join voice →
ensure librespot running for this member → attach the PCM source → reply "Ready! Open Spotify and
select **Discord Bot**...".

Then delete everything in §3.4's "dies" list, and drop `librespot` from `requirements.txt`.

**Acceptance:** end-to-end — `,play` → device appears in the Spotify app → transfer → **audible in
the VC** → pause/resume/skip from the app all work. This is the acceptance criterion the entire
feature has never once met.

## Step 6 — Regression + cleanup

- The rest of the bot has **not** been regression-tested on discord.py 2.7.1. Do that: `,help`,
  automod, NSFW checks, the scheduler jobs.
- Confirm `cleanup_job` isn't deleting librespot's cache dirs (`IMAGE_DIR`/`FILE_MAX_AGE_MIN` — put
  the cache outside `/app`).
- Clear `/run/discordbot.maintenance` (ask the user; needs root).
- Update `SPOTIFY_CONTEXT.md` to point at this file, and mark `SPOTIFY_CONNECT_PLAN.md` superseded.

---

# Part 5 — Potential issues

## 5.1 Sample rate and clock drift (likely, manageable)

Spotify is 44.1kHz, Discord needs 48kHz. ffmpeg resamples. Two processes each with their own clock
means slow drift is possible; the buffer in Step 3 absorbs it. If you hear periodic glitches, tune
the buffer size before doing anything cleverer.

## 5.2 OAuth — DECIDED 2026-08-15 (this section replaces the old Option A/B choice)

Both original options are dead. Option A (librespot owns auth via `--enable-oauth`) can't work for
remote users at all: librespot's redirect server listens on **this host's** `127.0.0.1:5588`, but
the user authorizes in **their own** browser, so the redirect lands on *their* localhost and never
reaches us. Option B's fatal objection — reverse-engineering librespot's on-disk credential format
— turns out to be unnecessary.

**What we actually do:** keep our existing web OAuth flow (`music/callback_server.py` + nginx +
the `nip.io` HTTPS callback, all already proven working), and hand librespot the resulting access
token with `--access-token`. Per-user decisions, agreed with the user:

1. **Mint a fresh access token from the stored refresh token on every spawn.** No per-user
   "is the credential cache populated yet" bookkeeping; the DB row is the only state.
2. **Our own link generator**, requesting the librespot scopes we're actually allowed to request
   (see the scope caveat below). librespot-python goes away entirely.

Verified against the v0.8.0 source on 2026-08-15:

- `--access-token` exists (`main.rs:517-519`) and is checked **before** cached credentials in the
  credential-selection block (`main.rs:1199-1230`). Consequence: **never pass a stale token when
  you intend the cache to be used** — the token wins and the login fails.
- librespot's own OAuth path is not privileged in any way; it fetches a token and calls the same
  `Credentials::with_access_token()` (`main.rs:1964-1968`).
- `spirc.rs:217` calls `session.connect(credentials, true)`, and `session.rs:250-256` saves the
  reusable credentials to `--system-cache` on success. So a cache *would* work — we simply don't
  need it, per decision 1.
- **The refresh grant works with no user interaction** — verified live on 2026-08-15 against the
  stored refresh token for member 1 (client `9111a325…`): HTTP 200, `expires_in=3600`, refresh
  token **not** rotated. Scopes granted back: `app-remote-control streaming
  user-modify-playback-state user-read-playback-state user-read-currently-playing user-read-email
  user-read-private`.

### The scope caveat (still unresolved)

librespot requests **27** scopes (`main.rs:176-203`), but that list is what *keymaster*, a
first-party client, is allowed to ask for. Several are not valid third-party Web API scopes at all
— `playlist-modify`, `playlist-read`, `user-modify`, `user-modify-private`, `user-personalized`,
`user-read-birthdate`, `user-read-play-history`. Request them from our dev app and Spotify will
reject the request or silently drop them. Ask for librespot's list ∩ valid-third-party.

### ANSWERED 2026-08-15: the token must come from **keymaster**, not our dev app

Ran live. A token minted by our dev app (`9111a325…`) **authenticates at the access point fine** —
`Authenticated as '31gfmisimhdtf6sqd4627uhmmtq4' !`, `Country: "CA"`, `"catalogue": "premium"`.
Then librespot fails at a *separate* step:

```
Requesting https://login5.spotify.com/v3/login
ERROR librespot] could not initialize spirc:
      Invalid state { Login request was denied: INVALID_CREDENTIALS }
```

Cause, from source: on Linux `SessionConfig::client_id` defaults to `KEYMASTER_CLIENT_ID`
(`core/config.rs:37-42`), and `login5_request` uses `self.session().client_id()` for
stored-credential logins (`core/login5.rs:82`). librespot therefore presents our dev-app-derived
stored credential to login5 **as keymaster**, and Spotify rejects the mismatch. There is **no
`--client-id` CLI flag** in v0.8.0 to override this.

⇒ **Mint with `65b708073fc0480ea92a077233ca87bd` (keymaster).** Upside: keymaster is first-party,
so it can request all 27 librespot scopes, and the §5.2 scope caveat above evaporates.

### ANSWERED 2026-08-15: keymaster REJECTS our hosted redirect URI

Authorizing with keymaster + `https://67.217.243.44.nip.io/` fails after login with
**`redirect_uri: Not matching configuration`**. Keymaster's whitelist is Spotify's and we cannot
add to it. `http://127.0.0.1:5588/login` works (it is what librespot itself uses) and yielded a
token granting **all 26 scopes plus a refresh token**.

Don't try to probe this unauthenticated — a deliberately bogus `redirect_uri` gets the same
`303 → /login` as a real one, because Spotify defers redirect validation until after login. Tested
and discarded 2026-08-15.

### DECIDED 2026-08-15: keymaster + DM paste-back. Third-party clients are not usable.

The obvious escape — patch librespot to use *our* dev app's client ID, so our own redirect
whitelist applies and the hosted callback keeps working — **was built and tested, and it does not
work.** The patch itself is fine; Spotify is the one refusing.

A 9-line patch adding `--client-id` (wiring the already-existing `SessionConfig::client_id` to a
CLI flag) produced this matrix, all against the real account:

| credential minted by | `--client-id` | AP auth | login5 verdict |
|---|---|---|---|
| keymaster | keymaster | ok | ✅ **SUCCESS — device registered** |
| keymaster | android (first-party, mismatched) | ok | ❌ `INVALID_CREDENTIALS` |
| our dev app | our dev app (matched!) | ok | ❌ `BAD_REQUEST` |

Row 1 proves the patch works. Row 2 is the discriminator: a **known first-party** client with the
wrong credential is told `INVALID_CREDENTIALS` — a well-formed request, bad credential. Our dev app
with a perfectly *matched* credential gets `BAD_REQUEST`, i.e. the request is rejected outright.
login5 is not objecting to the credential; it is refusing the client.

⇒ **login5's stored-credential login is first-party-only.** A third-party dev app cannot be used no
matter what we pass. Note the access point authenticates a dev-app credential fine — it is only
login5 (which spirc needs, for the spclient token behind every connect-state PUT) that refuses.

**Consequences, all forced:**

1. The OAuth authorization must use **keymaster**, whose redirect whitelist is Spotify's.
2. The only usable redirect is `http://127.0.0.1:5588/login`, which resolves on the **user's own**
   machine. We cannot receive the code, so linking cannot be automatic.
3. **The link UX is DM paste-back**: bot sends the auth link → user authorizes → their browser
   fails to load `127.0.0.1:5588` → user copies the URL from the address bar → DMs it to the bot.
   This is what the code did before commit `a299b94`; restore that path from git history.
4. `music/callback_server.py`, the nginx `spotify-callback` vhost, and the `SPOTIFY_CLIENT_ID` /
   `SPOTIFY_REDIRECT_URL` env vars become **dead code** for this feature.
5. **No fork needed.** Production runs stock librespot on its keymaster default, so Step 1 keeps a
   clean crates.io pin. The `--client-id` patch survives only as a diagnostic in the spike
   scratchpad; do not ship it.

**The one thing that could still overturn this** (~15% odds, not tested): the dev-app token carried
7 scopes vs keymaster's 26, so `BAD_REQUEST` *might* be about scopes rather than client eligibility.
Testing it costs one user click — re-authorize the dev app with the full valid-third-party scope set
through the existing hosted callback and rerun row 3. The user chose to proceed with paste-back
rather than run it.

### ⚠️ Keymaster ROTATES the refresh token on every refresh (found 2026-08-15)

A keymaster refresh grant returns a **new** refresh token and **immediately revokes the old one**.
Reusing the previous value gets:

```
HTTP 400 {"error":"invalid_grant","error_description":"Refresh token revoked"}
```

Found the hard way: a spike script minted a token, ignored the rotated refresh token in the
response, and the stored credential was dead on the next use. Note the old **dev app did not
rotate** — its refresh token survived repeated refreshes unchanged — so do not generalise from the
pre-2026-08-15 behaviour.

Consequences for Steps 2/4/5, all mandatory:

- **Persist the rotated refresh token immediately**, in the same operation that mints. Minting
  without persisting locks the user out of their own link and forces a re-link.
- **Persist before spawning.** If the DB write fails after a successful mint, the stored token is
  already revoked; better to fail loudly before librespot starts than to leave a working process on
  top of a dead credential.
- **Serialise mints per member.** Two concurrent refreshes for one user revoke each other. A
  per-member lock around mint+persist is required, not optional.

### Rejected alternative: bypass login5

Patching librespot to reuse the CLI-supplied access token for spclient instead of calling login5.
Rejected: that token dies in an hour and librespot has no way to refresh it, so the device would
drop mid-session — and it is exactly the bespoke-protocol work that produced this rewrite.

## 5.3 Per-user processes (moderate)

Each is a real process with a TCP connection and a few tens of MB RSS. Bound the number, reap
aggressively on unlink/idle/empty-channel, and make sure a crash-loop can't fork-bomb the host. The
bot is `network_mode: host`, so any port librespot binds is a **host** port — collisions are real,
especially with `--oauth-port` defaulting to 5588 for every user.

## 5.4 The bot is a singleton and the watchdog is armed (operational)

The healthcheck watches a heartbeat file that `main.py` rewrites every 30s. If librespot subprocess
management blocks the event loop, the heartbeat goes stale and the watchdog restarts the container
mid-debug. Keep all blocking work in an executor. During long manual sessions, `touch
/run/discordbot.maintenance` — **and remember to clear it afterwards.**

## 5.5 Disk (minor)

`--system-cache` per user is small (credentials + volume). The audio cache is not — use
`--disable-audio-cache`, or `--cache-size-limit`. Keep both **outside `/app`**, or `cleanup_job`
will eat them.

## 5.6 The device might still not appear (the real risk)

Everything here assumes Step 0 succeeds. If Rust librespot also fails to register a device from this
host, the problem is environmental (egress, IP reputation, account state) rather than library
quality, and **the entire premise of this plan is wrong**. That is precisely why Step 0 costs ten
minutes and comes first.

## 5.7 Things that are NOT the problem — don't go hunting

Ruled out by direct testing; re-testing these is wasted time:
- Discord voice / encryption / intents / firewall / UDP — **fixed and proven**, see §1.3
- Event-loop starvation from blocking librespot calls — timing logs showed `_ensure_connect_device`
  at 0.00s; the old ~27s stall was entirely inside discord.py's own retry loop
- Bot architecture, threading, GIL — discord.py's own official voice example failed identically in a
  clean process before the version fix
- Network/DNS to Spotify — `apresolve` resolves, 4 of 6 APs connect fine; the failures are Spotify's
  own dead endpoints

---

# Part 6 — Open questions for the user

1. **Commit the current work first?** All findings and the discord.py/davey fix are uncommitted.
   Recommend committing as a checkpoint before deleting the librespot-python stack. **Still open.**
2. ~~**OAuth Option A or B**~~ — **RESOLVED 2026-08-15**, and neither: our web OAuth mints a token
   per spawn via `--access-token`. See §5.2.
3. **Idle policy.** How long should the bot sit in a voice channel with a registered device and no
   audio before disconnecting and reaping the process? **Still open** — needed by Step 5.
4. **Multi-user scale.** How many simultaneous linked users should this support? Drives the process
   cap and whether per-user processes are viable at all. **Still open** — needed by Step 2.
