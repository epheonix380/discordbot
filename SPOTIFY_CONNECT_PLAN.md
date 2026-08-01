# SPOTIFY_CONNECT_PLAN.md — Spotify‑streaming music bot (spec + execution plan)

**Purpose:** a complete, executable specification for adding a Spotify music feature to
`discordbot`. A user runs a `,play` command; the bot replies with a Spotify login link; the
user authorizes; the bot then streams that user's Spotify audio into their Discord voice
channel using **librespot‑python**.

**Audience:** an implementing agent/model who has *not* seen the exploratory branches. Read
this top to bottom before writing code. Section 2 corrects a fundamental misconception that is
baked into the existing exploratory branches — do not skip it.

> This document is **not** the same as the repo's existing `PLAN.md`, which is about
> deployment/hosting reliability and is unrelated to this feature.

---

## 0. TL;DR for the implementer

- Target base branch: **`production`** (`be9c70a`, Docker, Python 3.9.13). Develop the feature
  on top of it. `requirements.txt` on `production` **already pins** librespot‑python
  (`git+https://github.com/kokarare1212/librespot-python@81ecec3…`).
- **A Spotify Web‑API OAuth token cannot be fed into librespot.** The old `librespot` branch
  does exactly this (`Session.Builder().user_pass(member_id, access_token)`) and it is wrong.
  See §2.
- librespot‑python's own OAuth is **PKCE‑based** and exposes `set_code()`, so the authorization
  code can be supplied out‑of‑band. That is what makes a Discord "click this link" flow
  viable **using librespot's keymaster client_id** (not your own app). See §2 and §5.
- The bot is a plain `discord.Client` with a `,`‑prefix router in `on_message` and an
  `app_commands` tree — **not** `commands.Bot`/Cogs. The exploratory `commands/music/player.py`
  is a `commands.Cog` and will not load as‑is. Integrate with the existing router. See §9.
- **What you can realistically ship:** a per‑user, command‑driven URI player (search a
  track/album/playlist, stream it into the VC using the user's Premium account credentials).
  A *true* Spotify‑Connect receiver (the bot showing up as a selectable device inside the
  Spotify app, controlled from that app) is **LAN‑only** in librespot‑python and is a
  stretch goal, not the MVP. See §2.4 and §14.
- Requires: **Spotify Premium** per streaming user, **ffmpeg** + **libopus** + **PyNaCl** in
  the image, and a public HTTPS endpoint is *not* required (paste‑back flow). See §10–§11.

---

## 1. Objective & user-facing behaviour

### 1.1 Happy path
1. User is in a voice channel and types `,play <song / artist / spotify URL>`.
2. If the user has **not** linked Spotify, the bot replies (ephemerally / in‑channel) with a
   **Spotify authorization link** and short instructions.
3. User clicks the link, logs into Spotify, approves the scopes. Their browser is redirected
   to `http://127.0.0.1:5588/login?code=…`, which **will not load** (there is no server on the
   user's machine). The instructions tell them to copy the whole URL (or just the `code=`
   value) and paste it back to the bot (DM, or a Discord modal — see §5.3).
4. The bot exchanges the code (PKCE), obtains **reusable librespot credentials**, and persists
   them for that user.
5. The bot joins the user's voice channel, resolves the query to a Spotify track URI, streams
   the audio through librespot → ffmpeg → Discord voice.
6. Subsequent `,play` calls skip straight to step 5 (credentials cached).

### 1.2 Supporting commands (MVP scope)
| Command | Behaviour |
|---|---|
| `,play <query|url>` | Link if needed, else join VC and play/queue the resolved track. |
| `,pause` / `,resume` | Pause/resume the current guild playback. |
| `,skip` | Skip to next queued item. |
| `,stop` / `,leave` | Stop playback, clear queue, disconnect from VC. |
| `,queue` | Show the current queue. |
| `,nowplaying` | Show the current track (title/artist/progress). |
| `,spotify unlink` | Delete the caller's stored credentials. |

Prefix `,` and DM/app‑command variants must match the existing style in `main.py` (§9).

---

## 2. Critical technical findings (read before designing anything)

### 2.1 There are two *different* Spotify "tokens" — they are not interchangeable
- **Web‑API OAuth token** (issued to *your* registered developer app, via the Authorization
  Code flow, scopes like `user-modify-playback-state`, `streaming`): lets you **call
  `api.spotify.com`** (search, read/skip playback on an *existing* device) and lets the
  **browser Web Playback SDK** create a device. It **cannot** be used to authenticate
  librespot to Spotify's access point (AP). It produces **no audio bytes** on its own.
- **librespot credentials**: librespot authenticates to Spotify's AP (`ap:4070`, proprietary
  TrIPE/login5 handshake) and can pull raw audio. These come from librespot's *own* OAuth
  (first‑party **keymaster** client_id), from Zeroconf, or from previously saved reusable
  credentials.

**Consequence:** you cannot register your own Spotify app, get a `streaming`‑scoped token, and
hand it to librespot. Spotify only issues AP/streaming entitlement to first‑party client_ids.
This is confirmed by librespot‑org/librespot issue #1501 ("oauth2 token → stored credentials"),
which remains unimplemented because the exchange happens inside the closed protocol.

**The existing `librespot` branch embodies exactly this mistake** in
`music/librespot_manager.py`:
```python
session = Session.Builder().user_pass(member_id, token_data['access_token']).create()
```
`user_pass` expects a Spotify *username + password*, not a Web‑API access token. This will
never work. Discard that approach.

### 2.2 librespot‑python's OAuth is PKCE and can be driven out‑of‑band
From `librespot/oauth.py` (pinned commit `81ecec3`):
- Authorize URL:
  `https://accounts.spotify.com/authorize?response_type=code&client_id=<keymaster>&redirect_uri=http://127.0.0.1:5588/login&code_challenge=<S256>&code_challenge_method=S256&scope=<25 scopes>`
- `flow()` = `get_auth_url()` → `run_callback_server()` → `request_token()` → `get_credentials()`.
- Crucially it exposes **`set_code(code)`**, so you can **skip the local callback server**:
  `get_auth_url()` (send to user) → user pastes code → `set_code(code)` → `request_token()`
  → `get_credentials()`.
- Because it uses **PKCE (S256, no client secret)**, and Spotify does not verify that a server
  actually received the loopback redirect, the paste‑back flow works from any machine.
- `get_credentials()` returns a `LoginCredentials` of type
  `AUTHENTICATION_SPOTIFY_TOKEN`; `save_creds()` persists client_id / access token / expiry /
  refresh token; the resulting **reusable credentials blob** can be reloaded later with
  `Session.Builder().stored_file(path)` (no re‑auth).

**This is the linchpin that makes the whole feature possible.** Verify it first (§13, Phase 0).

### 2.3 The redirect URI cannot be your own server
The redirect is `http://127.0.0.1:5588/login`, tied to the **keymaster** client_id (which you
do not own). You **cannot** substitute a public `https://yourbot/callback` — Spotify will
reject an unregistered redirect for that client_id, and you cannot use your own client_id
because its token would be rejected at the AP (§2.1). Therefore the login UX **must** be
paste‑back (copy the `code`), not an automatic web redirect. Design the UX around that (§5.3).
Do not spend time trying to host a callback that "just works"; it can't for keymaster.

### 2.4 "Connect speaker" — what is and isn't achievable
The user's phrasing is "stream as a connect speaker." Be precise about what that means:
- **True Spotify Connect receiver** (the bot appears as a device inside the user's Spotify app,
  and they press play *there*): librespot‑python only supports this via **Zeroconf/mDNS on the
  local network** (`ZeroconfServer`). A Discord bot on a VPS and a user on their phone are not
  on the same LAN, so this does **not** work remotely. Full internet Connect (dealer +
  SPIRC receiver) is only partially present in librespot‑python and is not a safe MVP target.
- **What the MVP actually is:** a **command‑driven URI player**. The bot holds the user's
  librespot credentials and streams specific tracks it resolves from `,play <query>`. It is
  *not* remotely controllable from the Spotify app. Frame the feature this way to the user;
  see Open Questions (§16). Keep true‑Connect as a documented stretch goal (§14).

### 2.5 Premium required
librespot streams full‑length tracks only for **Spotify Premium** accounts. Free accounts will
fail or be crippled. State this to users at link time.

---

## 3. Branch survey — what exists and what to reuse

All branches below diverge from `production`. Fetch and inspect, but treat them as prototypes.

| Branch | Approach | Verdict |
|---|---|---|
| **`librespot`** | Python "microservice": `music/handler.py` (correct `Session.Builder().oauth(cb)`), `music/librespot_manager.py` (token mgmt + **broken** `user_pass(access_token)` + stub play/pause), `music/server.py` (localhost OAuth callback server), Cog `player.py`, `SpotifyToken` model (migration 0047). | **Best conceptual match.** Reuse the model, the token‑refresh scaffolding, and the OAuth‑callback idea. Fix the auth mistake (§2.1). Playback is all stubs — must be written. |
| **`headless-spotify`** | JS service (`spotify/`) using **Spotify Web Playback SDK** in a headless browser (`puppeteer` + `puppeteer-stream`), audio → webm → ffmpeg → PCM (`helpers/audio.py`); real Web‑API OAuth (`streaming` scope); `Member.spotify` TextField (migration 0048). Adapted from IiroP/spotify-headless-client. | **The only approach whose "click a link" OAuth works with your own app**, and it *does* create a real Connect device. But heavy (a browser per stream), needs Widevine/EME, one token = one browser. Keep as the **alternative architecture** (§4, Option B). |
| **`dyspotify`** | Vendored **Rust** librespot source + `helpers/spotify.py` shelling out to a `librespot` **binary** with `--username/--password ... -B pipe` \| ffmpeg. | Username/password login is deprecated by Spotify; vendoring Rust is heavy. Useful only as reference for the ffmpeg pipe pattern. |
| **`librespot-raw`** | `helpers/pyaudio.py`: `librespot` binary → `FFmpegPCMAudio(pipe=True)` into `vc.play`. | Reference for the **discord voice pipe** wiring only. |
| **`music` / `maturin`** | Minimal `commands/music/player.py` (just joins VC). | Reference for VC‑join only. |
| **`youtube-dial`** | YouTube "lounge"/DIAL casting (`session.py`), unrelated to Spotify. | Ignore for this feature. |

**Reusable, concretely:**
- `SpotifyToken` model shape from `librespot` migration 0047 (adapt — see §6).
- The ffmpeg‑pipe → `discord.FFmpegPCMAudio`/`PCMAudio` pattern from `librespot-raw`/`dyspotify`.
- The token refresh logic in `librespot_manager.py` (but keyed to librespot creds, not Web API).

---

## 4. Recommended architecture

### Option A (RECOMMENDED, MVP) — Per‑user librespot + paste‑back PKCE OAuth + URI streaming
```
Discord user ──,play──▶ bot (discord.Client, main.py router)
   │                        │
   │  (if unlinked)         ├─ build librespot OAuth URL (keymaster + PKCE)  ── reply link
   │◀── login link ────────┘
   │  authorize @ Spotify → redirect 127.0.0.1:5588 (fails) → user copies code
   ├── paste code (DM/modal) ─▶ bot: OAuth.set_code() → request_token() → get_credentials()
   │                                     └─ persist reusable creds (DB/file) per user
   └─ bot: Session.Builder().stored_file(creds) → content_feeder().load(track_id, Vorbis…)
             → Ogg/Vorbis stream → ffmpeg (→ s16le 48k stereo) → discord voice (PCMAudio) ─▶ VC
   track resolution (query → spotify:track:…) via Web API search (client‑credentials app token)
```
- **Pros:** honours "librespot + login link"; no headless browser; light; per‑user account.
- **Cons:** paste‑back UX (§2.3); not a real remotely‑controllable Connect device (§2.4);
  one active stream per guild; blocking I/O must be offloaded (§8); ToS grey area (§14).

### Option B (ALTERNATIVE) — Headless Web Playback SDK (the `headless-spotify` branch)
Use *your own* registered app, real Web‑API OAuth (`streaming` scope), a public HTTPS
callback (clean redirect, no paste‑back), and a headless Chrome running the Web Playback SDK;
capture audio via `puppeteer-stream` → ffmpeg → VC. This is the **only** way to get a genuine
Connect device with a smooth login link.
- **Pros:** real Connect device; clean OAuth redirect; uses your app.
- **Cons:** a full browser per active stream (heavy RAM/CPU), Widevine/EME setup, brittle,
  Node service alongside the Python bot. Not recommended as the first deliverable.

### Rejected
- **Web‑API token → librespot** (the `librespot` branch's core idea): impossible (§2.1).
- **Zeroconf Connect over the internet:** LAN‑only (§2.4).
- **Your own client_id in librespot OAuth:** AP rejects non‑first‑party tokens (§2.1/§2.3).

**Implement Option A.** Keep Option B documented for the user's decision (§16).

---

## 5. OAuth flow specification (Option A)

### 5.1 Per‑user OAuth object
For each linking user, construct librespot‑python's `OAuth` (from `librespot.oauth`) so that:
- `client_id` = librespot **keymaster** id (the library's default — do **not** override with
  your own app id).
- `redirect_uri` = `http://127.0.0.1:5588/login` (library default; it only needs to *match* at
  token exchange, no server runs).
- PKCE verifier/challenge are generated by the library; **store the verifier** with the pending
  request (it is needed by `request_token()`).
- Scopes: use the library default set (it already requests a broad set incl. `streaming`).

Persist a **pending‑auth** record keyed by Discord user id: `{oauth_state, code_verifier,
created_at}` with a short TTL (e.g. 10 min). (If you construct one `OAuth` instance and keep it
in memory per user, it already holds the verifier; then you only need to survive restarts —
store the verifier if you want durability.)

### 5.2 Building & sending the link
- Call `oauth.get_auth_url()` and send it in the `,play` reply (embed, Spotify‑green `0x1DB954`).
- Include copy‑paste instructions and the DM/modal follow‑up (§5.3). Warn: **Premium required**.

### 5.3 Receiving the code (two acceptable UX options)
1. **Discord modal (preferred):** the reply has a "Paste code" button → opens a `discord.ui.Modal`
   with a text field; on submit, extract the code. (App‑command/interaction path.)
2. **DM paste:** instruct the user to DM the bot the redirected URL or the raw `code`. The
   existing `on_message` DM branch (`main.py` lines ~52–62) is where you'd parse it. Extract
   `code` from a pasted `http://127.0.0.1:5588/login?code=…` or accept the bare code.

Accept **either** the full URL or the bare code; strip/parse defensively.

### 5.4 Completing the exchange & persisting
```
oauth.set_code(code)          # bypasses the local server
oauth.request_token()         # PKCE exchange @ accounts.spotify.com/api/token
creds = oauth.get_credentials()   # LoginCredentials (AUTHENTICATION_SPOTIFY_TOKEN)
oauth.save_creds(<path>)      # persist reusable creds blob for this user
```
Persist to a **per‑user credentials store** (§6). Never log tokens. Confirm success to the user
and proceed to play the pending query.

### 5.5 Reuse & refresh
- On later plays: `Session.Builder().stored_file(<user creds path>).create()`. librespot
  refreshes the underlying token itself; if a session build fails with an auth error, mark the
  user as needing re‑link and re‑issue the login link.

---

## 6. Data model

Add a Django model on top of `production` (there is no `SpotifyToken` there; the `librespot`
branch's 0047 is a good template). Store the **librespot reusable credentials**, not a Web‑API
token.

```python
# storage/models.py
class SpotifyLink(models.Model):
    member = models.OneToOneField('storage.Member', on_delete=models.CASCADE)
    credentials = models.TextField()      # base64 reusable-creds blob from librespot save_creds
    spotify_username = models.TextField(default='')
    scope = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```
- Prefer storing the credentials **blob in the DB** over a file, so it survives container
  rebuilds (the DB is host‑postgres; see repo `CONTEXT.md`). At play time, write the blob to a
  temp file for `stored_file(path)`, or extend the loader to accept an in‑memory blob.
- **Encrypt at rest** if feasible (these credentials grant full account access). At minimum,
  restrict access and keep them out of logs/backups that leave the host.
- Add a `storage` migration. Follow the existing migration numbering on `production`.
- Reuse the existing async ORM helper pattern (`@sync_to_async`, e.g. `helpers/spotifyStore.py`
  on the `headless-spotify` branch) for `get_link(uid)`, `set_link(uid, blob, …)`,
  `delete_link(uid)`.

---

## 7. Module / file layout (Option A)

Create a `music/` package (mirrors the `librespot` branch, minus its mistakes):

| File | Responsibility |
|---|---|
| `music/oauth_flow.py` | Build per‑user librespot `OAuth`, `get_auth_url`, complete via `set_code`/`request_token`/`get_credentials`/`save_creds`. Pending‑auth store with TTL. |
| `music/librespot_manager.py` | Load user creds → build `Session` (in executor); `load_track_stream(session, track_uri)` → Ogg/Vorbis byte stream via `content_feeder().load(TrackId.from_uri(uri), VorbisOnlyAudioQuality(AudioQuality.VERY_HIGH), False, None)`. Session cache keyed by member id. |
| `music/search.py` | Web‑API **client‑credentials** token (bot's own app id/secret) → `search`/resolve `spotify:track|album|playlist:…` → list of track URIs + metadata. Pure Web‑API; no streaming entitlement needed for search. |
| `music/playback.py` | Per‑guild `GuildPlayer`: VC connect/disconnect, queue, `play_next`, ffmpeg pipe → `discord.PCMAudio`/`FFmpegPCMAudio`, pause/resume/skip/stop, nowplaying/progress. |
| `music/commands.py` | Command handlers (`handle_play`, `handle_pause`, …) wired into `main.py`'s router (§9). Not a Cog. |
| `helpers/spotifyStore.py` | Async ORM CRUD for `SpotifyLink` (§6). |

Delete/ignore the `commands/music/player.py` Cog; do not `add_cog`.

---

## 8. Playback pipeline specification

- `content_feeder().load(...)` returns an object whose `.input_stream.stream()` yields
  **Ogg/Vorbis** bytes. Do **not** call `.read()` byte‑by‑byte on the event loop.
- Bridge to ffmpeg. Two viable wirings (pick one, prototype both in Phase 2):
  1. **Feed the Vorbis stream to ffmpeg via stdin** and let `discord.FFmpegPCMAudio(pipe=True,
     ...)` decode → 48 kHz/stereo/s16le. (Cleanest; mirrors `librespot-raw/helpers/pyaudio.py`.)
  2. Pump `stream()` chunks into a `subprocess` ffmpeg (`-i pipe:0 -f s16le -ar 48000 -ac 2
     pipe:1`) from a background thread, wrap stdout in `discord.PCMAudio`. (Mirrors
     `dyspotify`/`headless-spotify` `helpers/audio.py`.)
- All **blocking** work (session build, `content_feeder().load`, reading the stream) runs in a
  **thread executor** (`loop.run_in_executor`) or a dedicated thread — never inline in the
  asyncio loop, or the gateway heartbeat (see `main.py heartbeat()`) will stall.
- `vc.play(source, after=<cleanup/advance queue>)`; the `after` callback runs off‑loop, so
  schedule queue advancement with `asyncio.run_coroutine_threadsafe(...)`.
- One `GuildPlayer` per guild; refuse concurrent streams in the same guild (queue instead).
- Clean up ffmpeg subprocess + close librespot stream on stop/disconnect/error.

---

## 9. Integration with the existing bot (important)

`main.py` uses **`discord.Client`** (not `commands.Bot`) with:
- a `,`‑prefix `if/elif` router inside `on_message` (guild) and a separate DM branch,
- an `app_commands.CommandTree` for slash commands,
- a single asyncio loop started via `loop.create_task(client.start(TOKEN))` + `heartbeat()`.

Therefore:
- **Do not** use `commands.Cog`/`add_cog`/`load_extension` (that requires `commands.Bot`). The
  `librespot` branch's Cog `player.py` is incompatible.
- Add `,play` etc. as new `elif message.content.startswith(",play")` branches calling
  `music.commands.handle_play(message, client)`, matching the existing handler signatures
  (`async def handler(message, client)`), and register any slash variants on `tree`.
- Route the DM **paste‑back** through the existing DM branch (`if message.guild is None:`).
- Voice requires `discord.py[voice]` + PyNaCl + libopus loaded (`discord.opus.load_opus`
  if not auto‑loaded). Confirm `intents` — `message_content` is already enabled; voice needs
  the voice state intent (default intents include voice states).

---

## 10. Dependencies & infrastructure

Add to `requirements.txt` (on top of `production`):
- `PyNaCl==1.5.0` (Discord voice encryption) — **currently missing**.
- (librespot‑python is already pinned; keep the pin.)
- Confirm `pycryptodomex` (present) and `protobuf==3.20.1` (present) satisfy librespot‑python.
- If using ffmpeg via python wrapper, none needed — call the **ffmpeg binary**.

Add to `Dockerfile` (`python:3.9.13-slim`, currently installs only build/gl libs):
- `ffmpeg` (binary) and `libopus0` (Opus for discord voice). Add to the `apt-get install` line.
- Keep `git` (already present) — needed to pip‑install librespot from the git URL.

Env / config (`.env`, read via `python-dotenv` as elsewhere):
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` — **only** for Web‑API **search** (client‑
  credentials). *Not* used for librespot auth. (The bot's existing `.env` already carries a
  Spotify client secret per repo `PLAN.md`.)
- `SPOTIFY_DEVICE_NAME` (optional, cosmetic).
- No public redirect URL / callback host is required for Option A.

---

## 11. Configuration & secrets handling
- Never commit `.env`; it is the single source of truth (repo `CONTEXT.md`).
- Treat stored librespot credentials as **full‑account secrets**: encrypt at rest if possible,
  exclude from any exported backup, never log. Provide `,spotify unlink` to delete them.
- Do not print auth URLs containing PKCE challenges to shared logs at INFO level.

---

## 12. Command specification (signatures & acceptance)

| Command | Precondition | Success | Failure messaging |
|---|---|---|---|
| `,play <q>` | user in a VC | joins VC, resolves query, streams/queues; posts nowplaying | not linked → login link; not in VC → prompt; no Premium → explain; no results → say so |
| `,pause`/`,resume` | active guild player | toggles | "nothing playing" |
| `,skip` | queue non‑empty | advances | "nothing to skip" |
| `,stop`/`,leave` | in VC | stops, clears, disconnects | "not connected" |
| `,queue` | — | lists items | "queue empty" |
| `,nowplaying` | active | title/artist/progress | "nothing playing" |
| `,spotify unlink` | linked | deletes creds | "not linked" |

Match the reply style in the existing exploratory `player.py` (embeds, Spotify green).

---

## 13. Execution plan (phased, each phase independently verifiable)

**Phase 0 — De‑risk the linchpin (do this first, ~half a day).**
- In a throwaway script inside the container image (Python 3.9.13, librespot pinned commit):
  build `OAuth`, print `get_auth_url()`, authorize manually, `set_code(<pasted code>)`,
  `request_token()`, `get_credentials()`, `save_creds()`. Then `Session.Builder().stored_file(...)
  .create()` and `content_feeder().load(<a known track uri>, VorbisOnlyAudioQuality(VERY_HIGH),
  False, None)` and read a few KB.
- **Acceptance:** you obtain reusable creds via paste‑back **and** pull audio bytes for a track
  using a **Premium** account. If this fails, stop and revisit Option B before building UX.

**Phase 1 — Data model & store.**
- Add `SpotifyLink` model + migration; async CRUD in `helpers/spotifyStore.py`.
- **Acceptance:** create/read/delete a link row via the async helpers.

**Phase 2 — Playback pipeline (single track, no Discord).**
- `music/librespot_manager.py` + `music/playback.py`: load creds → session → stream → ffmpeg
  → write `s16le` to a file/`aplay`. Prove the pipe end‑to‑end off the event loop.
- **Acceptance:** a 10‑second correct PCM capture of a known track.

**Phase 3 — Discord voice.**
- Add PyNaCl + ffmpeg/libopus to image; wire `vc.play(PCMAudio/FFmpegPCMAudio)`; join/leave.
- **Acceptance:** audible playback of a hard‑coded track URI in a real VC, clean disconnect.

**Phase 4 — OAuth link UX.**
- `music/oauth_flow.py` + pending‑auth store; `,play` issues link when unlinked; modal/DM
  paste‑back completes and persists; then auto‑plays the pending query.
- **Acceptance:** a fresh user links via the Discord flow and hears their track.

**Phase 5 — Search & queue.**
- `music/search.py` (Web‑API client‑credentials) resolves free‑text and URLs; `GuildPlayer`
  queue; `,pause/,resume/,skip/,stop/,queue/,nowplaying`.
- **Acceptance:** `,play never gonna give you up` works; queueing/skip works.

**Phase 6 — Hardening.**
- Token/session refresh & re‑link on auth failure; per‑guild concurrency guards; error
  messaging; resource cleanup; structured logging without secrets.
- **Acceptance:** survives skip‑spam, disconnects, expired creds, and a bad query without
  wedging the event loop (heartbeat stays fresh — see `main.py`).

**Phase 7 — Docs & rollout.**
- Update `README.md`/help command; note Premium requirement and ToS caveat (§14); commit &
  push to the designated feature branch. Do **not** open a PR unless asked.

---

## 14. Risks, limitations, ToS
- **Spotify ToS:** using librespot and/or streaming one account into a shared channel is a grey
  area and can get accounts flagged/banned. Per‑user credentials (Option A) limit blast radius
  to the consenting user. Surface this to users and the operator.
- **Premium required** to stream full tracks (§2.5).
- **Not a real Connect device** in the MVP (§2.4). Manage expectations in the UI/help text.
- **librespot‑python is unofficial & can break** when Spotify changes protocols; the pin at
  `81ecec3` is a moving target — watch for breakage on rebuilds.
- **Resource use:** one ffmpeg + one librespot session per active guild stream; cap concurrency.
- **Blocking calls** on the event loop are the top failure mode — enforce executor usage (§8).
- **Credential theft impact** is high — treat the store as sensitive (§11).

## 15. Testing
- Unit: query→URI parsing (`music/search.py`), code/URL extraction in paste‑back, queue logic.
- Integration: Phase 0 script kept as a smoke test; a manual checklist for the Discord flow.
- Regression: confirm the bot's existing features and `heartbeat()` are unaffected (no blocking).

## 16. Open questions for the user (resolve before/while building)
1. **Per‑user vs shared account?** Option A links each user's own Premium account (recommended).
   A single shared bot account is simpler but is one ToS violation for everyone and needs no
   login link. Confirm the intent behind "login link" is genuinely per‑user.
2. **Paste‑back UX acceptable?** The keymaster redirect can't hit our server (§2.3), so linking
   requires copying a code (modal or DM). If a *seamless* web redirect is a hard requirement,
   we must switch to **Option B** (headless Web Playback SDK, your own app) — heavier but a real
   Connect device with a clean redirect.
3. **True Connect control** (press play from the Spotify app) — is that required? If yes, only
   Option B delivers it remotely; librespot Zeroconf is LAN‑only.
4. **Premium** — confirm target users have Premium.

---

## Appendix A — Key code references (exploratory branches)
- `origin/librespot:music/handler.py` — correct librespot OAuth entry (`Session.Builder().oauth(cb)`).
- `origin/librespot:music/server.py` — localhost OAuth callback server (pattern; not needed with paste‑back).
- `origin/librespot:music/librespot_manager.py` — token mgmt scaffold; **contains the `user_pass(access_token)` mistake — do not copy that line**.
- `origin/librespot:storage/migrations/0047_…spotifytoken.py` — `SpotifyToken` model template.
- `origin/librespot-raw:helpers/pyaudio.py` — `librespot` → `FFmpegPCMAudio(pipe=True)` → `vc.play`.
- `origin/dyspotify:helpers/spotify.py` — `librespot -B pipe … | ffmpeg …` subprocess pattern.
- `origin/headless-spotify:spotify/*` + `helpers/audio.py` — full Option B reference implementation.

## Appendix B — Canonical librespot‑python snippets
```python
# Streaming a track (after credentials exist)
from librespot.core import Session
from librespot.metadata import TrackId
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality

session = Session.Builder().stored_file("creds.json").create()          # reuse creds
track_id = TrackId.from_uri("spotify:track:xxxxxxxxxxxxxxxxxxxxxx")
stream = session.content_feeder().load(
    track_id, VorbisOnlyAudioQuality(AudioQuality.VERY_HIGH), False, None)
# stream.input_stream.stream() -> file-like Ogg/Vorbis; pipe to ffmpeg (run off the event loop)

# Out-of-band OAuth (paste-back), instead of the blocking flow():
from librespot.oauth import OAuth
oauth = OAuth(...)                 # keymaster client_id + 127.0.0.1:5588 defaults
url = oauth.get_auth_url()         # send to the user in Discord
# ... user authorizes, copies ?code=... back to the bot ...
oauth.set_code(pasted_code)
oauth.request_token()
creds = oauth.get_credentials()
oauth.save_creds("creds.json")     # persist reusable credentials
```
