import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
from urllib.parse import unquote, urlencode

from librespot.mercury import MercuryRequests
from librespot.oauth import OAuth

logger = logging.getLogger("music.oauth_flow")

# Which Spotify OAuth client to authorize against.
#
# Default is Spotify's own first-party "keymaster" client, because
# session_manager logs into the Spotify access point with
# AUTHENTICATION_SPOTIFY_TOKEN, which is understood to only accept
# first-party tokens. A third-party dev-app token may be rejected at
# session build time even though the OAuth exchange itself succeeds.
#
# Override with SPOTIFY_CLIENT_ID to test a dev app. The trade-off:
#   - keymaster: session works, but its redirect-URI whitelist is Spotify's
#     and cannot be changed, so a hosted callback may be rejected.
#   - your dev app: you control the redirect whitelist, but the resulting
#     token may not authenticate librespot.
# See SPOTIFY_CONTEXT.md.
KEYMASTER_CLIENT_ID = MercuryRequests.keymaster_client_id
CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "").strip() or KEYMASTER_CLIENT_ID

# Public HTTPS callback this server hosts. Must exactly match a redirect URI
# registered on whichever client CLIENT_ID points at -- Spotify compares it
# byte-for-byte, including scheme, any port, and trailing slash.
REDIRECT_URL = os.environ.get(
    "SPOTIFY_REDIRECT_URL", "https://67.217.243.44.nip.io/").strip()

PENDING_TTL_SECONDS = 600

_AUTH_ENDPOINT = "https://accounts.spotify.com/authorize"

# Scopes needed to act as a Connect device and stream. Kept explicit rather
# than using librespot's full 26-scope default: the consent screen a user
# sees should list what we actually use.
SCOPES = [
    "streaming",
    "app-remote-control",
    "user-read-email",
    "user-read-private",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
]

_lock = threading.Lock()
# state token -> {"oauth", "user_id", "guild_id", "voice_channel_id", "created_at"}
#
# Keyed by a per-user random state, NOT by user id: the callback arrives as a
# plain HTTP request carrying no Discord identity, so the state is the only
# thing tying it back to a person. It must therefore be unguessable and
# single-use -- see _pending_by_state usage in callback_server.py.
_pending_by_state = {}
# user_id -> state, so a repeated ,play supersedes that user's older attempt
# instead of leaking pending entries.
_state_by_user = {}


def _purge_expired_locked():
    now = time.time()
    expired = [s for s, e in _pending_by_state.items() if now - e["created_at"] > PENDING_TTL_SECONDS]
    for state in expired:
        entry = _pending_by_state.pop(state, None)
        if entry is not None:
            _state_by_user.pop(str(entry["user_id"]), None)


def _drop_state_locked(state):
    entry = _pending_by_state.pop(state, None)
    if entry is not None:
        _state_by_user.pop(str(entry["user_id"]), None)
    return entry


def build_auth_url(oauth, state):
    """Build the authorize URL ourselves rather than using librespot's
    OAuth.get_auth_url().

    librespot's version hardcodes its own 26-scope list and, more importantly,
    has no way to attach a `state` parameter -- which is exactly what we need
    to tell one user's callback from another's. We still let the OAuth object
    generate the PKCE verifier/challenge, so the later request_token() call
    (which reads its own private __code_verifier) stays consistent.
    """
    # get_auth_url() is what generates and stores the PKCE code_verifier on
    # the OAuth instance, so it must be called even though we discard the URL.
    librespot_url = oauth.get_auth_url()
    match = re.search(r"code_challenge=([^&]+)", librespot_url)
    if not match:
        raise RuntimeError("could not extract PKCE code_challenge from librespot OAuth")
    code_challenge = match.group(1)

    return _AUTH_ENDPOINT + "?" + urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URL,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": " ".join(SCOPES),
        "state": state,
    })


def start_link(user_id, guild_id=None, voice_channel_id=None):
    """Begin a hosted-callback OAuth flow for a Discord user.

    Returns the auth URL to send them. Not blocking (PKCE math is local).
    The user authorizes in their browser, Spotify redirects to REDIRECT_URL
    with ?code=&state=, and callback_server finishes the link -- the user
    never copies anything.
    """
    oauth = OAuth(CLIENT_ID, REDIRECT_URL, None)
    # 32 bytes of urandom: this is the only credential tying an inbound
    # callback to a Discord account, so it must not be guessable.
    state = secrets.token_urlsafe(32)
    auth_url = build_auth_url(oauth, state)

    with _lock:
        _purge_expired_locked()
        # Supersede any earlier in-flight attempt by this same user.
        previous = _state_by_user.get(str(user_id))
        if previous is not None:
            _pending_by_state.pop(previous, None)
        _pending_by_state[state] = {
            "oauth": oauth,
            "user_id": int(user_id),
            "guild_id": guild_id,
            "voice_channel_id": voice_channel_id,
            "created_at": time.time(),
        }
        _state_by_user[str(user_id)] = state
    return auth_url


def has_pending(user_id):
    with _lock:
        _purge_expired_locked()
        return str(user_id) in _state_by_user


def peek_state(state):
    """Return the pending entry for a state without consuming it, or None."""
    with _lock:
        _purge_expired_locked()
        return _pending_by_state.get(state)


_CODE_RE = re.compile(r"[?&]code=([^&\s]+)")


def parse_code(raw_text):
    """Extract an OAuth code from either a bare code or a pasted redirect URL."""
    raw_text = raw_text.strip()
    match = _CODE_RE.search(raw_text)
    if match:
        return unquote(match.group(1))
    return raw_text


def complete_link_by_state(state, raw_code):
    """Exchange a callback's code for librespot credentials. Blocking (network).

    Consumes the state single-use: it is popped before the exchange, so a
    replayed callback URL cannot be redeemed twice.

    Returns (credentials_json: dict, pending: dict). Raises KeyError if the
    state is unknown or expired.
    """
    with _lock:
        _purge_expired_locked()
        entry = _drop_state_locked(state)
    if entry is None:
        raise KeyError("unknown or expired Spotify link state")

    oauth = entry["oauth"]
    oauth.set_code(parse_code(raw_code))
    oauth.request_token()

    fd, tmp_path = tempfile.mkstemp(prefix="spotify_creds_", suffix=".json")
    os.close(fd)
    try:
        oauth.save_creds(tmp_path)
        with open(tmp_path) as f:
            credentials_json = json.load(f)
    finally:
        # Credentials are full-account secrets; never leave them on disk.
        os.remove(tmp_path)

    return credentials_json, entry
