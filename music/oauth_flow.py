"""The Spotify link flow: issue an auth URL, take the code back via DM.

**Why paste-back and not the hosted callback** (this reverses commit a299b94,
so read before "fixing" it -- full evidence in LIBRESPOT_RUST_PLAN.md 5.2):

The Rust librespot needs Spotify's login5 service, and login5 refuses
third-party OAuth clients outright -- our own dev app's credential is rejected
with BAD_REQUEST even when librespot is patched to present that same client ID.
Only first-party clients work, so we must authorize against keymaster. Keymaster
is Spotify's own client; its redirect whitelist is Spotify's and we cannot add
to it. The only redirect it accepts is `http://127.0.0.1:5588/login`, which
resolves on the *user's* machine, not ours -- so no callback we host can ever
receive the code. The user has to carry it back.

`music/callback_server.py` and the nginx `spotify-callback` vhost are dead code
for this feature as a result.
"""
import logging
import re
import secrets
import threading
import time
import urllib.parse

from music import spotify_auth

logger = logging.getLogger("music.oauth_flow")

PENDING_TTL_SECONDS = 900

_lock = threading.Lock()
# str(user_id) -> {"code_verifier", "state", "guild_id", "voice_channel_id", "created_at"}
_pending = {}


def _purge_expired_locked():
    now = time.time()
    for user_id in [u for u, e in _pending.items() if now - e["created_at"] > PENDING_TTL_SECONDS]:
        _pending.pop(user_id, None)


def start_link(user_id, guild_id=None, voice_channel_id=None):
    """Begin a link. Returns the auth URL to send the user. Not blocking."""
    verifier, challenge = spotify_auth.generate_pkce()
    state = secrets.token_urlsafe(16)
    auth_url = spotify_auth.build_auth_url(challenge, state)

    with _lock:
        _purge_expired_locked()
        # A repeated ,play supersedes the user's older attempt rather than
        # leaving a stale entry behind.
        _pending[str(user_id)] = {
            "code_verifier": verifier,
            "state": state,
            "guild_id": guild_id,
            "voice_channel_id": voice_channel_id,
            "created_at": time.time(),
        }
    return auth_url


def has_pending(user_id):
    with _lock:
        _purge_expired_locked()
        return str(user_id) in _pending


def cancel(user_id):
    with _lock:
        _pending.pop(str(user_id), None)


_CODE_RE = re.compile(r"[?&]code=([^&\s]+)")
_STATE_RE = re.compile(r"[?&]state=([^&\s]+)")


def parse_code(raw_text):
    """Pull the code out of a pasted redirect URL, or accept a bare code."""
    raw_text = raw_text.strip()
    match = _CODE_RE.search(raw_text)
    if match:
        return urllib.parse.unquote(match.group(1))
    # Some browsers copy only the query string, which can start at the code.
    if raw_text.startswith("code="):
        return urllib.parse.unquote(raw_text[len("code="):].split("&", 1)[0])
    return raw_text.split("&", 1)[0]


def looks_like_paste_back(raw_text):
    """Cheap guard so ordinary DMs aren't mistaken for a pasted redirect."""
    text = raw_text.strip()
    if _CODE_RE.search(text) or text.startswith("code="):
        return True
    # A bare code: long, opaque, no whitespace.
    return len(text) > 60 and " " not in text and "\n" not in text


def complete_link(user_id, raw_text):
    """Exchange a pasted code for credentials. Blocking (network).

    Returns (credentials: dict, pending: dict). Raises KeyError if there is no
    pending link, and spotify_auth.SpotifyAuthError if Spotify rejects it.
    The pending entry is consumed only on success, so a typo can be retried.
    """
    user_id = str(user_id)
    with _lock:
        _purge_expired_locked()
        entry = _pending.get(user_id)
    if entry is None:
        raise KeyError("no pending Spotify link for this user")

    pasted_state = _STATE_RE.search(raw_text.strip())
    if pasted_state and urllib.parse.unquote(pasted_state.group(1)) != entry["state"]:
        raise KeyError("that link belongs to a different authorization attempt")

    credentials = spotify_auth.exchange_code(parse_code(raw_text), entry["code_verifier"])

    with _lock:
        _pending.pop(user_id, None)
    return credentials, entry
