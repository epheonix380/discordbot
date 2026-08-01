import json
import os
import re
import tempfile
import threading
import time
from urllib.parse import unquote

from librespot.mercury import MercuryRequests
from librespot.oauth import OAuth

KEYMASTER_CLIENT_ID = MercuryRequests.keymaster_client_id
# Same default librespot's own Session.Builder().oauth() flow uses -- known
# accepted by the keymaster client. We never run a listener on it; the user
# authorizes, the browser fails to load the redirect, and they paste the
# `code=` from the address bar back to us (SPOTIFY_CONNECT_PLAN.md §2.4b).
DEFAULT_REDIRECT_URL = "http://127.0.0.1:5588/login"
PENDING_TTL_SECONDS = 600

_lock = threading.Lock()
_pending = {}  # str(user_id) -> {"oauth", "guild_id", "voice_channel_id", "created_at"}


def _purge_expired_locked():
    now = time.time()
    expired = [uid for uid, entry in _pending.items() if now - entry["created_at"] > PENDING_TTL_SECONDS]
    for uid in expired:
        del _pending[uid]


def start_link(user_id, guild_id=None, voice_channel_id=None):
    """Begin a paste-back OAuth flow for a Discord user. Returns the auth URL to send them.

    Not blocking on the network -- get_auth_url() only does local PKCE math.
    """
    oauth = OAuth(KEYMASTER_CLIENT_ID, DEFAULT_REDIRECT_URL, None)
    auth_url = oauth.get_auth_url()
    with _lock:
        _purge_expired_locked()
        _pending[str(user_id)] = {
            "oauth": oauth,
            "guild_id": guild_id,
            "voice_channel_id": voice_channel_id,
            "created_at": time.time(),
        }
    return auth_url


def has_pending(user_id):
    with _lock:
        _purge_expired_locked()
        return str(user_id) in _pending


_CODE_RE = re.compile(r"[?&]code=([^&\s]+)")


def parse_code(raw_text):
    """Extract an OAuth code from either a bare code or a pasted redirect URL."""
    raw_text = raw_text.strip()
    match = _CODE_RE.search(raw_text)
    if match:
        return unquote(match.group(1))
    return raw_text


def complete_link(user_id, raw_code_or_url):
    """Exchange a pasted code for librespot credentials. Blocking (network call).

    Returns (credentials_json: dict, pending: dict) with pending containing
    whatever start_link() was given (guild_id/voice_channel_id). Raises
    KeyError if there's no pending link for this user (expired or never
    started).
    """
    with _lock:
        _purge_expired_locked()
        entry = _pending.pop(str(user_id), None)
    if entry is None:
        raise KeyError("no pending Spotify link for this user (expired or not started)")

    oauth = entry["oauth"]
    code = parse_code(raw_code_or_url)
    oauth.set_code(code)
    oauth.request_token()

    fd, tmp_path = tempfile.mkstemp(prefix="spotify_creds_", suffix=".json")
    os.close(fd)
    try:
        oauth.save_creds(tmp_path)
        with open(tmp_path) as f:
            credentials_json = json.load(f)
    finally:
        os.remove(tmp_path)

    return credentials_json, entry
