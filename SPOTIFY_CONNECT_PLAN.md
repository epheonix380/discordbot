# SPOTIFY_CONNECT_PLAN.md — Spotify Connect music bot (spec + execution plan)

**Purpose:** a complete, executable specification for adding a Spotify feature to `discordbot`.
A user runs `,play`; the bot replies with a Spotify **login link**; the user authorizes via
OAuth; the bot uses the resulting credentials with **librespot‑python** to register a genuine
**Spotify Connect device** and stream the audio into the user's Discord voice channel — fully
remote, controllable from the user's own Spotify app and/or Discord commands.

**Audience:** an implementing agent/model who has *not* seen the exploratory branches. Read top
to bottom before writing code. §2 corrects a misconception that is baked into the exploratory
`librespot` branch — do not skip it.

> This is **not** the repo's existing `PLAN.md` (which is about deployment/hosting reliability).

---

## 0. TL;DR for the implementer

- **Base branch:** develop on top of **`production`** (`be9c70a`, Docker, Python 3.9.13).
- **Bump the librespot pin.** `production`'s `requirements.txt` pins an **old** commit
  (`81ecec3…`). Repin to a recent master —
  **`git+https://github.com/kokarare1212/librespot-python@18104622b3be02062f1f8abe8dafc396413e9784`**
  (v0.0.10). The recent commits add the pieces this feature needs: full OAuth user‑token
  manager, `set_scopes`/`set_listen_all`/`set_code`, and a working dealer/connect‑state path.
- **A Spotify Web‑API OAuth token is NOT a librespot credential** and cannot authenticate
  librespot to Spotify's access point. The old `librespot` branch does exactly this
  (`Session.Builder().user_pass(member_id, access_token)`) and it is wrong. You must use
  **librespot's own OAuth** (first‑party *keymaster* client_id). See §2.1.
- **A real, internet Spotify Connect receiver IS achievable** with librespot‑python: the
  library registers the device (`put_connect_state` → `/connect-state/v1/devices/{id}`) and
  opens the dealer websocket (`wss://…/?access_token=…`) with `MessageListener`/`RequestListener`
  dispatch. It works anywhere with a valid credential blob — **no LAN/Zeroconf requirement**.
  Zeroconf is merely one (LAN) way to *obtain* credentials; OAuth is the other. See §2.2.
- **Caveat — no turnkey player.** librespot‑python gives you the *plumbing* (Session, OAuth,
  dealer client + listeners, `put_connect_state`, the Connect/Player protobufs, the content
  feeder). It does **not** ship a finished SPIRC player state machine. The bot must implement
  the loop: register the device, react to dealer play/pause/seek/next commands, pull audio via
  `content_feeder`, pipe it to Discord voice, and report state back with `put_connect_state`.
  This is real work but clearly possible. See §2.3 and §7.
- The bot is a plain `discord.Client` with a `,`‑prefix router in `on_message` + an
  `app_commands` tree — **not** `commands.Bot`/Cogs. The exploratory Cog `player.py` won't load
  as‑is. Integrate with the existing router. See §9.
- Requires **Spotify Premium** per user, plus **ffmpeg** + **libopus** + **PyNaCl** in the
  image. See §10. A public HTTPS callback is *nice‑to‑have* (clean redirect) but not required
  (paste‑back / loopback fallback both work). See §5.

---

## 1. Objective & user-facing behaviour

### 1.1 Happy path
1. User is in a voice channel and types `,play <song / artist / spotify URL>`.
2. If the user has **not** linked Spotify, the bot replies with a **Spotify authorization link**
   + short instructions (§5). Warns: **Premium required**.
3. User authorizes. The bot completes OAuth and persists the user's **reusable librespot
   credentials** (§6).
4. The bot joins the user's voice channel and brings up a librespot **Session** from those
   credentials, connecting to the dealer and **registering a Connect device**
   (e.g. "Discord: #general"). The device now appears in the user's Spotify app.
5. Playback starts on that device — either the bot auto‑transfers/starts the resolved query via
   the Web API, or the user selects the device in their Spotify app. librespot pulls the audio;
   the bot pipes it into the VC.
6. The user can control playback **from their own Spotify app** (play/pause/skip/seek/queue)
   *and/or* with Discord commands. The bot mirrors state back to Spotify via `put_connect_state`.
7. Subsequent `,play` skips straight to playback (credentials cached).

### 1.2 Two shippable modes (build B first, then A)
- **Mode B — command‑driven URI player (MVP milestone).** No dealer/connect‑state. `,play`
  resolves a URI and streams it via `content_feeder`. Simplest; proves the audio path.
- **Mode A — real Connect receiver (target).** Adds device registration + dealer command loop,
  so the bot is a genuine Connect speaker controllable from the Spotify app.

### 1.3 Commands (MVP)
| Command | Behaviour |
|---|---|
| `,play <query|url>` | Link if needed; join VC; register device (Mode A) / stream (Mode B). |
| `,pause` / `,resume` | Pause/resume current guild playback. |
| `,skip` | Next track. |
| `,stop` / `,leave` | Stop, clear, disconnect, tear down the Connect device. |
| `,queue` | Show queue. |
| `,nowplaying` | Current track + progress. |
| `,spotify unlink` | Delete the caller's stored credentials. |

Match the existing `,`‑prefix style and handler signatures in `main.py` (§9).

---

## 2. Critical technical findings (read before designing)

### 2.1 Web‑API token ≠ librespot credential (still true)
- **Web‑API OAuth token** (issued to *your* registered app): lets you call `api.spotify.com`
  (search, transfer/skip on an existing device) and drive the browser Web Playback SDK. It
  **cannot** authenticate librespot to the access point and produces **no audio** by itself.
- **librespot credential:** obtained from librespot's **own** OAuth (first‑party *keymaster*
  client_id), Zeroconf, or a saved reusable‑credentials blob. This is what grants AP/stream
  access. `Session.Builder().oauth()` hardcodes the keymaster client_id — **use it; do not
  substitute your own app id**, whose token the AP rejects (librespot‑org/librespot #1501).
- Convenient bonus: once you have a librespot `Session`, you can get a Web‑API token from the
  *same* session via `session.tokens().get("<scope>")` — so search / `transfer_playback` need no
  separate app credentials.
- **The `librespot` branch's `Session.Builder().user_pass(member_id, access_token)` is wrong**
  twice over: `user_pass` wants a username/password, and an access token isn't a librespot
  credential. Discard it.

### 2.2 A real internet Connect receiver is supported (the earlier "LAN‑only" claim was wrong)
Confirmed in librespot‑python `@18104622` (`librespot/core.py`):
- `ApiClient.put_connect_state(connection_id, PutStateRequest)` → `PUT
  https://<spclient>/connect-state/v1/devices/{device_id}` — **registers/updates the device**
  with Spotify Connect.
- `DealerClient` opens `wss://<dealer>/?access_token=<token>` and dispatches `MESSAGE`/`REQUEST`
  frames to registered `MessageListener`/`RequestListener` objects (`add_message_listener`,
  `add_request_listener`, `handle_message`, `handle_request`), with ping/pong keepalive and
  auto‑reconnect (`ConnectionHolder`).
- Connect protobufs present: `Connect_pb2` (`PutStateRequest`, device/cluster state),
  `Player_pb2`, `TransferState_pb2`, `Queue_pb2`, `PlayOrigin_pb2`, `ContextPlayerOptions_pb2`.
- This is the **internet** Connect path (dealer + spclient), used by Spotify's own apps. It does
  **not** require the controller to be on the same network. **Zeroconf (`librespot/zeroconf.py`)
  is only a LAN credential‑handoff mechanism — not a limit on the receiver.**

### 2.3 What librespot‑python does *not* give you (the implementation gap)
There is no finished SPIRC "player" that automatically plays a track when Spotify transfers to
the device and keeps the reported state in sync. The bot must build that loop on top of the
primitives in §2.2:
1. Construct and PUT an initial `PutStateRequest` describing the device (name, capabilities —
   `can_play`, volume steps, supported types).
2. Register listeners; obtain the dealer `connection_id` (from the initial hello message) and
   include it in `put_connect_state`.
3. On incoming commands (transfer/play/pause/resume/seek/skip/set‑queue), drive playback via
   `content_feeder().load(...)` and update local player state.
4. Periodically / on change, `put_connect_state` to report position, track, and play/pause so
   the Spotify UI stays correct.

Budget time for this in Mode A (§13, Phase 5). Mode B avoids it entirely.

### 2.4 OAuth redirect options (login‑link UX)
librespot‑python's `OAuth` (in `librespot/oauth.py`) uses **PKCE (S256)** and now exposes:
- constructor `OAuth(client_id, redirect_url, oauth_url_callback)` — **redirect_url is
  configurable**;
- `get_auth_url()`, `set_scopes()`, `set_listen_all(True)` (callback server binds `0.0.0.0`),
  `set_code(code)` (supply the code out‑of‑band, skipping the local server), `request_token()`,
  `get_credentials()`, `save_creds(path)`.

So you have **three** ways to capture the code for a remote Discord user:
- **(a) Public callback (cleanest):** construct `OAuth` with `redirect_url =
  https://<yourbot>/spotify/callback` and run the callback server (or your own web handler);
  requires that redirect to be accepted for the keymaster client_id — **verify in Phase 0**; if
  rejected, fall back to (b)/(c).
- **(b) Paste‑back:** send `get_auth_url()`; user copies the `?code=…` from the (failing)
  redirect and pastes it back (Discord modal or DM); bot calls `set_code()` → `request_token()`.
- **(c) Loopback + listen‑all:** only helps when the browser can reach the bot host directly.

Default the design to **(b) paste‑back** (always works), and try to upgrade to **(a)** in
Phase 0 if keymaster accepts a hosted redirect. Keymaster/keymaster‑style clients historically
allow `http://127.0.0.1` redirects; a public HTTPS redirect must be validated empirically.

### 2.5 Premium required
Full‑track streaming via librespot needs **Spotify Premium**. State this at link time.

---

## 3. Branch survey — what exists and what to reuse

| Branch | Approach | Verdict |
|---|---|---|
| **`librespot`** | Python "microservice": `music/handler.py` (correct `Session.Builder().oauth(cb)`), `music/librespot_manager.py` (token scaffold + **broken** `user_pass(access_token)`, stub play/pause), `music/server.py` (OAuth callback server), Cog `player.py`, `SpotifyToken` model (migration 0047). | **Best conceptual match.** Reuse the model shape, refresh scaffolding, and the callback‑server idea. Fix §2.1. Playback is all stubs — write it. |
| **`headless-spotify`** | Node service using the **Web Playback SDK** in headless Chrome (`puppeteer-stream`) → ffmpeg; Web‑API OAuth; `Member.spotify` field (migration 0048). | Alternative that also yields a real Connect device but is heavy (a browser per stream, Widevine). Keep as fallback only if librespot proves unstable. |
| **`dyspotify`** | Vendored **Rust** librespot + `helpers/spotify.py` shelling `librespot --username/--password … -B pipe \| ffmpeg`. | Deprecated password login; heavy. Reference for the ffmpeg pipe only. |
| **`librespot-raw`** | `helpers/pyaudio.py`: `librespot` binary → `FFmpegPCMAudio(pipe=True)` → `vc.play`. | Reference for the **discord voice pipe** wiring. |
| **`music` / `maturin`** | `commands/music/player.py` VC‑join stub. | Reference for VC join. |
| **`youtube-dial`** | YouTube DIAL casting. | Unrelated — ignore. |

**Concretely reusable:** `SpotifyToken` model shape (adapt, §6); ffmpeg‑pipe→discord voice
pattern (`librespot-raw`/`dyspotify`); the async ORM helper style in
`headless-spotify:helpers/spotifyStore.py`.

---

## 4. Recommended architecture

### RECOMMENDED — librespot‑python, per‑user OAuth, real Connect receiver
```
Discord user ──,play──▶ bot (discord.Client router in main.py)
   │ (unlinked)          ├─ build librespot OAuth URL (keymaster + PKCE)  ── reply login link
   │◀── login link ──────┘
   │  authorize @ Spotify → capture code via (a) public callback / (b) paste-back
   ├── code ─▶ OAuth.set_code()→request_token()→get_credentials()→save_creds()  ──► persist blob (§6)
   │
   └─ Session.Builder().stored_file(blob).create()
         ├─ DealerClient → wss dealer  ──────────────┐  remote control from user's Spotify app
         ├─ put_connect_state → device "Discord:#ch" │  (transfer/play/pause/skip/seek/queue)
         ├─ on command → content_feeder().load(uri, VorbisOnlyAudioQuality(VERY_HIGH), …)
         │        → Ogg/Vorbis stream → ffmpeg (s16le 48k stereo) → discord voice (PCMAudio) ─▶ VC
         └─ put_connect_state (report position/track/state)  ◀─ keep Spotify UI in sync
   search / auto-transfer via Web API using session.tokens().get(<scope>)
```
- Ship **Mode B** (command‑driven URI player: OAuth → creds → `content_feeder` → VC) first as a
  milestone, then layer **Mode A** (dealer + `put_connect_state` receiver loop) on top.

### Rejected / fallback
- **Web‑API token → librespot:** impossible (§2.1). *(the `librespot` branch's core mistake)*
- **Own client_id in librespot OAuth:** AP rejects non‑first‑party tokens (§2.1).
- **Headless Web Playback SDK (`headless-spotify`):** viable fallback for a real Connect device
  if librespot‑python proves too unstable, but much heavier (browser per stream). Not first.

---

## 5. OAuth flow specification

### 5.1 Per‑user OAuth object
Construct `librespot.oauth.OAuth(keymaster_client_id, redirect_url, callback)` per linking user.
Keep the instance (it holds the PKCE `code_verifier`) or persist `{code_verifier, redirect_url,
created_at}` keyed by Discord user id with a short TTL (≈10 min) for restart durability. Use
`set_scopes(...)` if you need to trim/extend the default scope set (the default already includes
`streaming`).

### 5.2 Send the link
`oauth.get_auth_url()` → reply as an embed (Spotify green `0x1DB954`) with instructions and a
**Premium‑required** warning.

### 5.3 Capture the code
Primary: **paste‑back** — a `discord.ui.Modal` "Paste code" button (interaction path) or a DM
handled by the existing `if message.guild is None:` branch in `main.py`. Accept **either** the
full `…/callback?code=…` URL or the bare code; parse defensively. If Phase 0 proves a hosted
public redirect works with keymaster, add the **public‑callback** path for a seamless redirect.

### 5.4 Complete & persist
```
oauth.set_code(code); oauth.request_token()
creds = oauth.get_credentials()          # LoginCredentials
oauth.save_creds(<tmp path>)             # reusable-credentials blob
```
Persist the blob to the per‑user store (§6). Never log tokens/URLs with PKCE challenges at INFO.
Then proceed to bring up the session and play the pending query.

### 5.5 Reuse & refresh
Later plays: `Session.Builder().stored_file(<blob path>).create()`. librespot refreshes the
underlying token itself. On an auth failure, mark the user "needs re‑link" and re‑issue the link.

---

## 6. Data model
Add a Django model on `production` (there is no `SpotifyToken` there; the `librespot` branch's
0047 is a template). Store the **librespot reusable credentials**, not a Web‑API token.
```python
# storage/models.py
class SpotifyLink(models.Model):
    member = models.OneToOneField('storage.Member', on_delete=models.CASCADE)
    credentials = models.TextField()      # base64 reusable-creds blob (from save_creds)
    spotify_username = models.TextField(default='')
    scope = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```
- Store the **blob in postgres** (survives container rebuilds — see repo `CONTEXT.md`); at play
  time write it to a temp file for `stored_file(path)`.
- **Encrypt at rest** if feasible — these credentials grant full account access. Keep out of
  logs and any backup that leaves the host. Provide `,spotify unlink` to delete.
- Add a `storage` migration following `production`'s numbering. Provide async CRUD
  (`@sync_to_async`) in `helpers/spotifyStore.py`: `get_link`, `set_link`, `delete_link`.

---

## 7. Module / file layout
Create a `music/` package (mirrors the `librespot` branch, minus its mistakes):

| File | Responsibility |
|---|---|
| `music/oauth_flow.py` | Per‑user `OAuth` build, `get_auth_url`, `set_code`/`request_token`/`get_credentials`/`save_creds`; pending‑auth store + TTL; code/URL parsing. |
| `music/session_manager.py` | Creds → `Session` (built in an executor); cache by member id; expose `session.tokens()` for Web‑API calls; teardown. |
| `music/connect_device.py` | **Mode A:** build/refresh `PutStateRequest`, register `MessageListener`/`RequestListener`, capture the dealer `connection_id`, `put_connect_state`, translate dealer commands → `GuildPlayer` actions, and report state back. |
| `music/search.py` | Resolve `,play` query/URL → `spotify:track|album|playlist:…` via Web API (token from `session.tokens().get("user-read-private")` or client‑credentials). |
| `music/playback.py` | Per‑guild `GuildPlayer`: VC connect/disconnect, queue, `content_feeder` → ffmpeg → `discord.PCMAudio`/`FFmpegPCMAudio`, pause/resume/skip/stop, progress. |
| `music/commands.py` | `handle_play`, `handle_pause`, … wired into `main.py`'s router (§9). **Not a Cog.** |
| `helpers/spotifyStore.py` | Async ORM CRUD for `SpotifyLink` (§6). |

Delete/ignore `commands/music/player.py` (Cog); do not `add_cog`.

---

## 8. Playback pipeline
- `content_feeder().load(TrackId.from_uri(uri), VorbisOnlyAudioQuality(AudioQuality.VERY_HIGH),
  False, None)` → object whose `.input_stream.stream()` yields **Ogg/Vorbis** bytes.
- Bridge to ffmpeg (pick one; prototype both in Phase 2):
  1. Feed the Vorbis stream to `discord.FFmpegPCMAudio(pipe=True, ...)` (decode → 48 kHz/stereo/
     s16le). Cleanest; mirrors `librespot-raw/helpers/pyaudio.py`.
  2. Pump `stream()` chunks into a `subprocess` ffmpeg (`-i pipe:0 -f s16le -ar 48000 -ac 2
     pipe:1`) from a thread; wrap stdout in `discord.PCMAudio`. Mirrors `headless-spotify/
     helpers/audio.py`.
- **All blocking work** (session build, `content_feeder().load`, stream reads, dealer callbacks)
  runs in a **thread executor** — never inline on the asyncio loop, or `main.py`'s `heartbeat()`
  stalls and the watchdog restarts the bot.
- `vc.play(source, after=<advance queue>)`; the `after` callback runs off‑loop, so schedule
  queue advancement with `asyncio.run_coroutine_threadsafe(...)`.
- One `GuildPlayer` per guild; queue rather than run concurrent streams. Clean up ffmpeg +
  librespot stream + Connect device on stop/disconnect/error.

---

## 9. Integration with the existing bot (important)
`main.py` uses **`discord.Client`** (not `commands.Bot`) with a `,`‑prefix `if/elif` router in
`on_message` (guild + a DM branch) and an `app_commands.CommandTree`, on a single asyncio loop
(`loop.create_task(client.start(TOKEN))` + `heartbeat()`).
- **Do not** use `commands.Cog`/`add_cog`/`load_extension`. The `librespot` branch's Cog won't
  load. Add `elif message.content.startswith(",play"): await music.commands.handle_play(message,
  client)` branches matching existing `async def handler(message, client)` signatures; register
  any slash variants on `tree`.
- Route paste‑back through the DM branch (`if message.guild is None:`).
- Voice: add `discord.py[voice]` + PyNaCl + libopus; call `discord.opus.load_opus(...)` if not
  auto‑loaded. Default intents already include voice states; `message_content` is already on.

---

## 10. Dependencies & infrastructure
`requirements.txt` (on top of `production`):
- **Repin librespot** to `@18104622b3be02062f1f8abe8dafc396413e9784` (§0).
- Add **`PyNaCl==1.5.0`** (voice) — currently missing.
- `websocket-client` (dealer) is already present (`websocket-client==1.7.0`); `protobuf==3.20.1`
  and `pycryptodomex` are present. Verify they satisfy the new librespot commit; bump if needed.

`Dockerfile` (`python:3.9.13-slim`): add **`ffmpeg`** and **`libopus0`** to the `apt-get install`
line. Keep `git` (needed for the librespot git install).

Env / config (`.env`, via `python-dotenv`):
- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` — only needed if you use client‑credentials for
  search; can be avoided by using `session.tokens()`.
- `SPOTIFY_DEVICE_NAME` (optional; device label prefix).
- `SPOTIFY_REDIRECT_URI` (optional; only for the Phase‑0 public‑callback experiment, §2.4a).

---

## 11. Secrets handling
- Never commit `.env` (single source of truth — `CONTEXT.md`). Treat stored librespot
  credentials as full‑account secrets: encrypt at rest if possible, exclude from exported
  backups, never log. `,spotify unlink` deletes them.
- Do not log auth URLs (PKCE) or tokens at INFO.

---

## 12. Command spec (acceptance)
| Command | Precondition | Success | Failure messaging |
|---|---|---|---|
| `,play <q>` | user in VC | link if needed; join; register device (A)/stream (B); nowplaying | not linked → login link; not in VC → prompt; no Premium → explain; no results → say so |
| `,pause`/`,resume` | active player | toggles | "nothing playing" |
| `,skip` | queue non‑empty | advances | "nothing to skip" |
| `,stop`/`,leave` | in VC | stop/clear/disconnect/teardown device | "not connected" |
| `,queue` | — | lists | "queue empty" |
| `,nowplaying` | active | title/artist/progress | "nothing playing" |
| `,spotify unlink` | linked | deletes creds | "not linked" |

Match the embed style (Spotify green) in the exploratory `player.py`.

---

## 13. Execution plan (phased, each independently verifiable)

**Phase 0 — De‑risk (do first).** In the container (Python 3.9.13, new librespot pin): (i) run
librespot OAuth end‑to‑end via **paste‑back** (`get_auth_url`→`set_code`→`request_token`→
`get_credentials`→`save_creds`) with a **Premium** account; (ii) `stored_file` → `Session` →
`content_feeder().load(<known uri>)` and read a few KB; (iii) bring up `DealerClient`, call
`put_connect_state`, and confirm the device appears in the Spotify app and that transferring to
it delivers dealer command frames; (iv) test whether a **public** `redirect_url` is accepted by
keymaster (§2.4a). **Acceptance:** creds via paste‑back, audio bytes pulled, device visible in
the Spotify app, dealer commands observed. If (iii) fails, ship Mode B only and reconsider the
`headless-spotify` fallback for true Connect.

**Phase 1 — Data model & store.** `SpotifyLink` + migration + async CRUD. *Acceptance:* CRUD works.

**Phase 2 — Audio pipeline (no Discord).** creds → session → `content_feeder` → ffmpeg → PCM to
file. *Acceptance:* correct 10 s PCM of a known track, off the event loop.

**Phase 3 — Discord voice.** PyNaCl + ffmpeg/libopus in image; `vc.play`; join/leave.
*Acceptance:* audible hard‑coded track in a real VC; clean disconnect.

**Phase 4 — OAuth link UX.** `oauth_flow.py` + pending store; `,play` issues link when unlinked;
modal/DM paste‑back persists creds; auto‑plays pending query. *Acceptance:* a fresh user links in
Discord and hears their track (**Mode B shippable here**).

**Phase 5 — Connect receiver (Mode A).** `connect_device.py`: `PutStateRequest`, listeners,
`connection_id`, command loop, state reporting. *Acceptance:* device shows in the Spotify app;
play/pause/skip/seek from the app control the VC audio; the app UI reflects position/track.

**Phase 6 — Search & queue.** `search.py` (via `session.tokens()`), `GuildPlayer` queue, the
control commands. *Acceptance:* `,play never gonna give you up` + queue/skip work.

**Phase 7 — Hardening.** Session refresh/re‑link on auth failure; per‑guild concurrency guards;
dealer reconnect handling; resource cleanup; secret‑safe logging; heartbeat stays fresh under
skip‑spam/disconnects/expired creds.

**Phase 8 — Docs & rollout.** Update `README.md`/help (note Premium + ToS §14); commit & push to
the designated feature branch. **Do not open a PR unless asked.**

---

## 14. Risks, limitations, ToS
- **Spotify ToS:** librespot is unofficial; automated streaming can get accounts flagged.
  Per‑user credentials limit blast radius to the consenting user. Surface this to users/operator.
- **Premium required** (§2.5).
- **No turnkey player** — the receiver loop is yours to build (§2.3); budget Phase 5 accordingly.
- **librespot‑python is unofficial & moving** — it can break on Spotify protocol changes; pin a
  known‑good commit and watch rebuilds.
- **Blocking calls on the event loop** are the top failure mode — enforce executor usage (§8).
- **Resource use** — one ffmpeg + one session (+ dealer ws) per active guild stream; cap it.
- **Credential theft impact** is high — treat the store as sensitive (§11).

## 15. Testing
- Unit: query→URI parsing, code/URL extraction, queue logic, `PutStateRequest` construction.
- Integration: keep the Phase 0 script as a smoke test; manual checklist for the Discord + app
  control flow.
- Regression: existing features and `heartbeat()` unaffected (no blocking).

## 16. Open questions for the user
1. **Mode A vs B first?** Recommend shipping Mode B (command player) as an early milestone, then
   Mode A (full Connect receiver). Confirm this ordering.
2. **Login UX:** paste‑back is guaranteed; a seamless hosted redirect depends on Phase 0 (2.4a).
   Confirm a public HTTPS callback host is available if we want the smooth flow.
3. **Per‑user vs shared account:** per‑user (login link) is assumed. A single shared account is
   simpler but one ToS liability for everyone. Confirm the intent behind the login link.
4. **Premium:** confirm target users have Premium.

---

## Appendix A — Exploratory‑branch code references
- `origin/librespot:music/handler.py` — correct `Session.Builder().oauth(cb)` entry.
- `origin/librespot:music/server.py` — OAuth callback‑server pattern (for §2.4a).
- `origin/librespot:music/librespot_manager.py` — token scaffold; **contains the
  `user_pass(access_token)` mistake — do not copy that line.**
- `origin/librespot:storage/migrations/0047_…spotifytoken.py` — model template.
- `origin/librespot-raw:helpers/pyaudio.py` — `librespot` → `FFmpegPCMAudio(pipe=True)` → `vc.play`.
- `origin/dyspotify:helpers/spotify.py` — `librespot -B pipe … | ffmpeg …` subprocess pattern.
- `origin/headless-spotify:spotify/*` + `helpers/audio.py` — full fallback (Web Playback SDK).

## Appendix B — Canonical librespot‑python snippets (verified against `@18104622`, v0.0.10)
```python
# Reuse stored credentials and stream a track (run blocking parts off the event loop)
from librespot.core import Session
from librespot.metadata import TrackId
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality

session = Session.Builder().stored_file("creds.json").create()
stream = session.content_feeder().load(
    TrackId.from_uri("spotify:track:xxxxxxxxxxxxxxxxxxxxxx"),
    VorbisOnlyAudioQuality(AudioQuality.VERY_HIGH), False, None)
# stream.input_stream.stream() -> Ogg/Vorbis file-like; pipe to ffmpeg -> discord voice

# A Web-API token off the same session (search, transfer_playback, etc.)
api_token = session.tokens().get("user-read-private")

# Out-of-band OAuth (paste-back): build URL, take the pasted code, exchange it
from librespot.oauth import OAuth
oauth = OAuth(client_id, redirect_url, oauth_url_callback=None)   # keymaster id; redirect configurable
url = oauth.get_auth_url()          # send to the user in Discord
oauth.set_code(pasted_code)         # skips the local callback server
oauth.request_token()
creds = oauth.get_credentials()
oauth.save_creds("creds.json")      # persist reusable credentials

# Connect device registration (Mode A) uses:
#   session.api().put_connect_state(connection_id, PutStateRequest(...))   # register/update device
#   session.dealer().add_message_listener(...) / add_request_listener(...) # receive remote commands
#   librespot.proto.Connect_pb2 / Player_pb2 / TransferState_pb2 / Queue_pb2
```
