# YOUTUBE_CAST_RESEARCH.md — can we do for YouTube what we did for Spotify?

**Written:** 2026-08-24 · **Branch:** `claude/youtube-casting-discord-bot-q0o108`
**Question asked:** can we auth a user and have the bot appear in YouTube's cast menu as a
castable device — *without* reverse-engineering the YouTube TV APIs?

---

## 0. Verdict

**No.** Not under that constraint.

There are exactly two mechanisms that put a device in the YouTube app's cast menu. One is closed
to us (Google Cast requires certified hardware). The other **is** the YouTube TV API — the
undocumented Lounge/MDx protocol — so "do it without reverse-engineering the TV APIs" removes the
only remaining door.

And even if you accept the reverse-engineering, YouTube is a **materially worse** target than
Spotify was, for a reason that has nothing to do with the cast protocol: the Lounge API is a
*remote-control* protocol only. It hands you a video ID, not audio. Spotify's equivalent handed us
the actual stream. That gap is where this feature actually dies — see §4.

---

## 1. Premise check: the Spotify feature is *also* reverse-engineered

Worth stating plainly, because it reframes the question.

`music/spotify_auth.py` authenticates as **keymaster** (`65b708073fc0480ea92a077233ca87bd`) —
Spotify's own first-party client ID, not one we registered. The module docstring says why: login5
refuses third-party clients outright, so a dev-app credential cannot work. `music/librespot_process.py`
then drives the Rust **librespot**, a clean-room reimplementation of the Spotify Connect protocol.

None of that is a documented, sanctioned integration. Spotify publishes no "become a Connect
device" SDK for third parties either.

So the real question isn't *official vs. reverse-engineered*. It's:

> **Is there a librespot-equivalent for YouTube?**

Answer: something exists, it is much less mature, and it solves only half the problem.

---

## 2. The two doors into the cast menu

### Door 1 — Google Cast (Chromecast). Closed.

You can register a **Custom Web Receiver** in the Cast SDK Developer Console (there's a
registration fee), but the receiver app has to *run somewhere*, and that somewhere must be
Cast-certified hardware — a Chromecast dongle or a TV with Cast built in. There is no supported
way to turn an arbitrary Linux box into a Cast receiver; the CASTV2 receiver side is not published.

It's moot regardless: YouTube's cast receiver is Google's own first-party app. We could not host it
even with certified hardware.

### Door 2 — DIAL + the YouTube Lounge API. This *is* the TV API.

This is how every third-party YouTube receiver works (`yt-cast-receiver`, `ytcast`,
`youtube-lounge-rs`, `pyytlounge`).

- **DIAL** (DIscovery And Launch) *is* an open spec, and it's the part that makes the device show
  up in the cast menu by name — but only for **discovery and launch**, and only over **SSDP
  multicast on the same LAN**.
- Everything after that moment — the device registering as a screen, receiving the queue, getting
  play/pause/seek/volume — runs over `https://www.youtube.com/api/lounge/...`. Undocumented.
  Reverse-engineered. Explicitly so: pyytlounge's own docs call it "the unofficial and undocumented
  YouTube Lounge API… not public so code using it can break at any time," and `yt-cast-receiver`'s
  README says the project "may not be reliable enough for production use."

**LAN is fatal for us anyway.** This bot runs in a container on a VPS (`network_mode: host`,
host Postgres on loopback — see `CLAUDE.md` §1). It is not on the user's home network, so DIAL
discovery can never see it.

That leaves **"Link with TV code"** — the manual pairing flow, which *does* work across networks
and is therefore the only shape that fits a hosted bot. But the code comes from
`/api/lounge/pairing/get_pairing_code`, refreshed every five minutes. Lounge API again.

**Net:** the off-LAN path a hosted bot needs is 100% Lounge API. There is no partial-credit option
where DIAL alone gets us into the menu.

---

## 3. The official routes, and what they can't do

| Route | Status | Why it doesn't solve this |
|---|---|---|
| **YouTube Data API v3** | Official, open | Metadata, search, playlists. Returns no media stream, and is not a playback API. |
| **IFrame Player API** | Official, open | Requires a real, visible browser player. Developer policies forbid headless/automated use, and there's no legitimate way to tap its audio into a voice channel. |
| **YouTube Living Room** (device certification) | Official, real | This is the genuine "be a YouTube TV device" program — and it's a **partner program for device manufacturers**, gated behind licensing agreements and a certification process. Not open to a Discord bot. |
| **Google Cast SDK** | Official, open (sender side) | Lets you *cast to* devices. Does not let you *be* one. |

The one officially-sanctioned way to be a YouTube cast target is to be a TV manufacturer with a
signed Google licensing agreement. That's the honest answer to "is there an official path."

---

## 4. The part that actually kills it: there is no audio

This is the difference that matters most, and it's easy to miss while focusing on the cast menu.

**Spotify:** librespot authenticates as the user's real Premium account and pulls encrypted Ogg
straight from Spotify's CDN, decrypting it in-process. `librespot_process.py` just resamples
44.1k→48k and pumps PCM into `PCMBuffer`. The media path lives *inside* the protocol. One
component, one credential, one stream.

**YouTube:** the Lounge protocol is a remote control. `yt-cast-receiver` makes you implement your
own `Player` class (`doPlay()`, `doPause()`, `doSeek()`, …) and hands it a **video ID plus context**.
Fetching the actual bytes is explicitly your problem. In practice that means yt-dlp or YouTube.js —
a second, entirely separate reverse-engineering effort, and the one Google actively fights.

Three concrete problems with that half:

1. **ToS.** YouTube's Terms prohibit accessing the Service "using any automated means (such as
   robots, botnets or scrapers)," and the developer policies specifically prohibit offering users
   the ability to **download or separate audio tracks** from a video. Separating the audio track is
   precisely and unavoidably what a voice-channel bot does. Spotify's ToS is not friendly either,
   but nothing in the librespot path maps this directly onto a named prohibition.

2. **Datacenter IPs are blocked.** YouTube's "Sign in to confirm you're not a bot" challenge is
   triggered aggressively on VPS/cloud egress ranges — the failure mode is *the code works on your
   laptop and fails on the server*. This bot is on a VPS. Workarounds are residential proxies or
   feeding real account cookies into the container, which puts that account at risk of being
   flagged. This is the single most common cause of death for self-hosted music bots right now.

3. **Breakage cadence.** librespot has ~10 years of maintenance behind it and Spotify's protocol
   moves slowly. YouTube's player internals change on the order of weeks, and both halves here
   (Lounge *and* stream extraction) break independently.

Recall from `LIBRESPOT_RUST_PLAN.md` that we burned a full session on **nine** distinct defects in
librespot-*python* before abandoning it for the Rust binary — and that was against the *good*
ecosystem. The YouTube equivalent has no Rust-librespot-grade fallback to retreat to.

---

## 5. What is actually buildable

Ranked by how much I'd recommend them.

### A. Discord's built-in "Watch Together" activity ⭐ recommended

First-party Discord, uses YouTube's own embedded player, syncs playback across everyone in the
voice channel, no ToS problem, and **no infrastructure on our side at all**.

The bot's entire job is to create the invite. We're on discord.py 2.7.1 (`requirements.txt:21`),
which supports embedded-application invites — a channel invite with `target_type = 2`
(`embedded_application`) and the Watch Together application ID `880218394199220334`.

That's roughly a 30-line command in `commands/`, no new dependency, no new model, no new process
to supervise. Compare against the ~1,300 lines and multi-session debugging saga in `music/`.

Trade-offs, stated honestly:
- It's video-in-the-client, not bot-streamed audio in the voice channel. Users watch inside
  Discord rather than "casting to the bot."
- No cast-menu entry — the flow starts in Discord, not in the YouTube app.
- Users can't sign into their YouTube account inside the activity, so no private playlists,
  no Premium, ads as normal.

If the underlying goal is "watch/listen to YouTube together in a voice channel," this delivers it
today. If the goal is specifically the *cast-menu gesture*, it doesn't.

### B. Invert it — bot as **sender**, not receiver

Instead of the bot being a cast target, the bot **controls a screen the user already owns** (their
TV, their console, their YouTube tab). This is the mature, well-trodden use of `pyytlounge` —
actively maintained, last release 2026-07-22, pip-installable, pure Python, fits this codebase.

Still the Lounge API, so still reverse-engineered — but it **completely sidesteps §4**. No stream
extraction, no ToS audio-separation clause, no datacenter IP blocking, because YouTube's own
first-party client does the playing. The user links once (pairing code), and we store it in a
`YouTubeLink` model alongside `SpotifyLink`.

Different feature — "queue this to my TV from Discord" rather than "cast to the bot" — but it's
the version of this idea that would actually stay working.

### C. Full receiver via `yt-cast-receiver` — not recommended

Architecturally it would slot in cleanly, which is the seductive part: `yt-cast-receiver` is
Node.js, and `music/librespot_process.py` is *already* a supervisor for a foreign-language
subprocess that pipes PCM through ffmpeg into a `PCMBuffer`. The same pattern applies almost
directly, with a `Player` implementation shelling out to yt-dlp + ffmpeg.

The architecture is not the blocker. §4 is. You'd be building on an upstream that self-describes as
not production-ready, layering yt-dlp on top, and running the whole thing from a datacenter IP that
YouTube is actively challenging.

---

## 6. Recommendation

- If the goal is **YouTube in the voice channel**: build **(A)**, Watch Together. Cheap, official,
  works, and it's a day's work rather than a month's.
- If the goal is **the cast gesture specifically**: build **(B)**, the sender direction. The user
  casts to their own TV, from Discord.
- **(C)** only if you specifically want the receiver experience and accept that it will break
  repeatedly and violates YouTube's ToS in a way the Spotify feature does not.

There is no version of this that satisfies "appears in YouTube's cast menu" *and* "no reverse
engineering." Those two requirements are mutually exclusive today.

---

## 7. Sources

- Google Cast — [Overview](https://developers.google.com/cast/docs/overview),
  [Custom Web Receiver](https://developers.google.com/cast/docs/web_receiver/basic)
- [YouTube Living Room device partner program](https://developers.google.com/youtube/devices/living-room)
- [YouTube API Services — Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
  and [Terms of Service](https://www.youtube.com/t/terms) (automated access; audio separation)
- [`yt-cast-receiver`](https://github.com/patrickkfkan/yt-cast-receiver) — Node.js receiver framework
- [`pyytlounge`](https://github.com/FabioGNR/pyytlounge) / [docs](https://pyytlounge.readthedocs.io/en/latest/) — Python Lounge client
- [`ytcast`](https://github.com/MarcoLucidi01/ytcast) — Go CLI sender
- [`youtube-lounge-rs`](https://github.com/bertybuttface/youtube-lounge-rs) — Rust Lounge client
- ["I Built a TV That Plays All of Your Private YouTube Videos"](https://bugs.xdavidhu.me/google/2021/04/05/i-built-a-tv-that-plays-all-of-your-private-youtube-videos/) — Lounge pairing internals
- [Discord — Invite resource](https://discord.com/developers/docs/resources/invite) (`target_type: 2`)
- [Discord — Watch Together FAQ](https://support-apps.discord.com/hc/en-us/articles/26502500234519-Watch-Together-FAQ)
- yt-dlp datacenter-IP blocking: [yt-dlp#13067](https://github.com/yt-dlp/yt-dlp/issues/13067)
