"""Spotify OAuth: PKCE, code exchange, and token refresh.

Replaces librespot-python's `librespot.oauth.OAuth`. See LIBRESPOT_RUST_PLAN.md
Part 5.2 for why the whole Python librespot dependency goes away.

Two things here are non-obvious and were established live on 2026-08-15:

1. **The client MUST be keymaster.** Spotify's login5 (which the Rust librespot
   needs for the spclient token behind every connect-state PUT) refuses
   third-party clients outright -- a dev-app credential is rejected with
   BAD_REQUEST even when librespot is patched to present that same client ID,
   while a first-party-but-mismatched client gets INVALID_CREDENTIALS. The
   access point authenticates a dev-app credential fine; only login5 refuses.

2. **Because keymaster's redirect whitelist is Spotify's**, the only usable
   redirect is loopback, which resolves on the *user's* machine. We therefore
   cannot receive the code ourselves -- hence the DM paste-back flow.

Everything here is synchronous/blocking by design; callers run it via
loop.run_in_executor, matching session_manager/content_pipeline convention.
"""
import base64
import hashlib
import json
import logging
import secrets
import time
import urllib.parse
import urllib.request

logger = logging.getLogger("music.spotify_auth")

# Spotify's own first-party "keymaster" client. Not ours, and not something we
# can register redirect URIs against -- see the module docstring.
KEYMASTER_CLIENT_ID = "65b708073fc0480ea92a077233ca87bd"

# The only redirect URI keymaster accepts that we can drive. Nothing listens on
# it (it is the *user's* localhost); the code is read out of their address bar.
# This exact value is what librespot itself uses.
REDIRECT_URI = "http://127.0.0.1:5588/login"

AUTHORIZE_ENDPOINT = "https://accounts.spotify.com/authorize"
TOKEN_ENDPOINT = "https://accounts.spotify.com/api/token"

# librespot's own scope list (src/main.rs). keymaster is first-party, so unlike
# our old dev app it is entitled to all of these.
SCOPES = [
    "app-remote-control", "playlist-modify", "playlist-modify-private",
    "playlist-modify-public", "playlist-read", "playlist-read-collaborative",
    "playlist-read-private", "streaming", "ugc-image-upload",
    "user-follow-modify", "user-follow-read", "user-library-modify",
    "user-library-read", "user-modify", "user-modify-playback-state",
    "user-modify-private", "user-personalized", "user-read-birthdate",
    "user-read-currently-playing", "user-read-email", "user-read-play-history",
    "user-read-playback-position", "user-read-playback-state",
    "user-read-private", "user-read-recently-played", "user-top-read",
]

HTTP_TIMEOUT_SECONDS = 30

# Refresh this far before the token actually expires, so a token minted for a
# spawn cannot go stale between minting and librespot's login.
EXPIRY_MARGIN_SECONDS = 60


class SpotifyAuthError(Exception):
    """Token exchange or refresh was rejected by Spotify."""


def generate_pkce():
    """Return (code_verifier, code_challenge) for a PKCE authorization."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_auth_url(code_challenge, state):
    """Build the authorize URL the user opens in their browser."""
    return AUTHORIZE_ENDPOINT + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": KEYMASTER_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": " ".join(SCOPES),
        "state": state,
    })


def _post_token(fields):
    body = urllib.parse.urlencode(fields).encode("ascii")
    request = urllib.request.Request(
        TOKEN_ENDPOINT, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Never log the response body verbatim -- on the exchange path it can
        # echo the code back.
        raise SpotifyAuthError(
            "Spotify rejected the token request (HTTP %s)" % exc.code) from exc
    except urllib.error.URLError as exc:
        raise SpotifyAuthError("could not reach Spotify: %s" % exc.reason) from exc


def _credentials_from_payload(payload, previous=None):
    """Normalise a token response into the blob stored in SpotifyLink.credentials."""
    refresh_token = payload.get("refresh_token")
    if not refresh_token and previous:
        # Spotify only returns a refresh token when it issues a new one; keep
        # the existing one when it doesn't rotate.
        refresh_token = previous.get("refresh_token")
    if not refresh_token:
        raise SpotifyAuthError("Spotify returned no refresh token")

    return {
        "client_id": KEYMASTER_CLIENT_ID,
        "access_token": payload["access_token"],
        "refresh_token": refresh_token,
        "expires_at": int(time.time()) + int(payload.get("expires_in", 3600)),
        "scope": payload.get("scope", ""),
    }


def exchange_code(code, code_verifier):
    """Exchange an authorization code for credentials. Blocking (network)."""
    payload = _post_token({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": KEYMASTER_CLIENT_ID,
        "code_verifier": code_verifier,
    })
    return _credentials_from_payload(payload)


def refresh_credentials(credentials):
    """Mint a fresh access token from a stored refresh token. Blocking.

    Returns (credentials, rotated) where `rotated` is True if the refresh token
    itself changed and the caller must persist the new blob. Spotify is entitled
    to rotate it even though it did not on 2026-08-15.
    """
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise SpotifyAuthError("stored credentials have no refresh token; user must re-link")

    payload = _post_token({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        # Always keymaster, even for blobs written by the old dev-app flow --
        # those are unusable with librespot anyway and the user re-links once.
        "client_id": KEYMASTER_CLIENT_ID,
    })

    updated = _credentials_from_payload(payload, previous=credentials)
    rotated = updated["refresh_token"] != refresh_token
    if rotated:
        logger.info("Spotify rotated a refresh token; persisting the new one")
    return updated, rotated


def is_expired(credentials):
    """True if the stored access token is at (or near) its expiry."""
    expires_at = credentials.get("expires_at")
    if expires_at is None:
        return True
    return time.time() >= (expires_at - EXPIRY_MARGIN_SECONDS)
