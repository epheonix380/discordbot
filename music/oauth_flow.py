"""The Spotify link flow: start a device authorization, poll until approved.

**Why there is no callback server here** (read before "fixing" it -- full
evidence in LIBRESPOT_RUST_PLAN.md 5.2 and music/spotify_auth.py's docstring):

librespot needs a token minted by Spotify's first-party keymaster client, and
keymaster's redirect whitelist is Spotify's own -- it rejects any callback we
host and accepts only `http://127.0.0.1:5588/login`, which resolves on the
*user's* machine. So under the authorization code grant no callback we run
could ever receive the code, which is what once forced a DM paste-back.

We use the device authorization grant instead. There is no redirect at all:
we hold the `device_code`, the user approves in their own browser, and we poll
outbound until Spotify hands us the credentials. The Discord-to-Spotify binding
is ours by construction -- we minted that `device_code` for that member and
DM'd its link only to them -- so unlike the callback design nothing inbound has
to be correlated back to an account.

This module is deliberately free of asyncio and discord imports: it is the
state machine only. music/commands.py owns the polling loop.
"""
import logging
import threading
import time

from music import spotify_auth

logger = logging.getLogger("music.oauth_flow")

# How long we will chase one authorization. Spotify's own device codes last an
# hour, but a link the user has walked away from should not hold a poller for
# that long -- 15 minutes is plenty and bounds the polling.
PENDING_TTL_SECONDS = 900

_lock = threading.Lock()
# str(user_id) -> pending record (see start_link)
_pending = {}
_generation = 0


def _purge_expired_locked():
    now = time.time()
    for user_id in [u for u, e in _pending.items() if now >= e["deadline"]]:
        _pending.pop(user_id, None)


def start_link(user_id, guild_id=None, voice_channel_id=None):
    """Begin a link. Blocking (network).

    Returns the record to drive the DM and the poller: `user_code` and
    `verification_uri_complete` to show the user, `interval` to wait between
    polls, `generation` to pass back to poll(), and `deadline`.

    The `device_code` is kept here and never returned -- it is the credential
    that redeems the authorization, and nothing outside this module needs it.
    """
    global _generation

    payload = spotify_auth.start_device_authorization()
    now = time.time()
    deadline = now + min(PENDING_TTL_SECONDS, int(payload.get("expires_in", PENDING_TTL_SECONDS)))

    with _lock:
        _purge_expired_locked()
        _generation += 1
        # A repeated ,play supersedes the user's older attempt rather than
        # leaving a stale entry behind. The generation makes that safe against
        # an in-flight poll of the attempt being replaced.
        entry = {
            "device_code": payload["device_code"],
            "user_code": payload["user_code"],
            "verification_uri_complete": payload.get(
                "verification_uri_complete", payload.get("verification_uri", "")),
            "interval": payload["interval"],
            "generation": _generation,
            "guild_id": guild_id,
            "voice_channel_id": voice_channel_id,
            "created_at": now,
            "deadline": deadline,
        }
        _pending[str(user_id)] = entry

    return {k: v for k, v in entry.items() if k != "device_code"}


def poll(user_id, generation):
    """One poll step for a pending link. Blocking (network).

    Returns (status, credentials, entry). On spotify_auth.GRANT_GRANTED the
    pending record is consumed and returned as `entry` (so the caller can see
    which voice channel the link started from); otherwise both are None and the
    caller should wait `poll_interval()` and call again.

    Raises KeyError if this attempt is gone -- cancelled, expired, or
    superseded by a newer one -- and spotify_auth.DeviceAuthorizationError once
    Spotify calls it over.
    """
    user_id = str(user_id)
    with _lock:
        _purge_expired_locked()
        entry = _pending.get(user_id)
        if entry is None:
            raise KeyError("no pending Spotify link for this user")
        if entry["generation"] != generation:
            raise KeyError("superseded by a newer Spotify link attempt")
        device_code = entry["device_code"]

    status, credentials = spotify_auth.poll_device_token(device_code)

    if status == spotify_auth.GRANT_SLOW_DOWN:
        with _lock:
            current = _pending.get(user_id)
            if current is not None and current["generation"] == generation:
                current["interval"] += spotify_auth.SLOW_DOWN_INCREMENT_SECONDS
                logger.info("Spotify asked us to slow down; interval now %ds",
                            current["interval"])
        return status, None, None

    if status != spotify_auth.GRANT_GRANTED:
        return status, None, None

    with _lock:
        # Re-check under the lock: the attempt could have been cancelled or
        # superseded while this poll was in flight, and a link nobody is
        # waiting on must not be redeemed.
        current = _pending.get(user_id)
        if current is None or current["generation"] != generation:
            raise KeyError("this Spotify link attempt is no longer current")
        _pending.pop(user_id, None)
    return status, credentials, current


def poll_interval(user_id, generation):
    """Seconds to wait before the next poll, or None if the attempt is over."""
    with _lock:
        entry = _pending.get(str(user_id))
        if entry is None or entry["generation"] != generation:
            return None
        if time.time() >= entry["deadline"]:
            return None
        return entry["interval"]


def has_pending(user_id):
    with _lock:
        _purge_expired_locked()
        return str(user_id) in _pending


def cancel(user_id):
    with _lock:
        _pending.pop(str(user_id), None)
