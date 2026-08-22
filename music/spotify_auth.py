"""Spotify OAuth: the device authorization grant, and token refresh.

Replaces librespot-python's `librespot.oauth.OAuth`. See LIBRESPOT_RUST_PLAN.md
Part 5.2 for why the whole Python librespot dependency goes away.

Two things here are non-obvious. Both were established live.

1. **The client MUST be keymaster.** Spotify's login5 (which the Rust librespot
   needs for the spclient token behind every connect-state PUT) refuses
   third-party clients outright -- a dev-app credential is rejected with
   BAD_REQUEST even when librespot is patched to present that same client ID,
   while a first-party-but-mismatched client gets INVALID_CREDENTIALS. The
   access point authenticates a dev-app credential fine; only login5 refuses.

2. **We use the device authorization grant (RFC 8628), not the authorization
   code grant** -- so there is no redirect URI and no callback server anywhere
   in this flow. That is not a stylistic choice. Keymaster's redirect whitelist
   is Spotify's own: it rejects any callback we host (`redirect_uri: Not
   matching configuration`) and accepts only `http://127.0.0.1:5588/login`,
   which resolves on the *user's* machine. Under the code grant we could
   therefore never receive the code, which is what forced the old DM
   paste-back. The device grant sidesteps the whole problem: we hold the
   `device_code` and poll outbound, so nothing has to come back to us.

   Verified live 2026-08-22 against keymaster: authorization returns a
   `device_code` immediately, polling returns `authorization_pending` until the
   user approves, and approval yields an access token, a refresh token, and all
   26 requested scopes. librespot started with that token authenticated,
   resolved spclient, and registered a Connect device that accepted real
   playback -- i.e. login5 accepts a device-grant token.

Everything here is synchronous/blocking by design; callers run it via
loop.run_in_executor, matching the convention in music/credentials.py.
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("music.spotify_auth")

# Spotify's own first-party "keymaster" client. Not ours, and not something we
# can register redirect URIs against -- see the module docstring.
KEYMASTER_CLIENT_ID = "65b708073fc0480ea92a077233ca87bd"

DEVICE_AUTHORIZATION_ENDPOINT = "https://accounts.spotify.com/oauth2/device/authorize"
TOKEN_ENDPOINT = "https://accounts.spotify.com/api/token"
DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

# librespot's own scope list (src/main.rs). keymaster is first-party, so unlike
# our old dev app it is entitled to all of these -- all 26 come back granted.
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

# Spotify sends `interval` (5s); this floors it in case it ever sends nonsense.
MIN_POLL_INTERVAL_SECONDS = 5
# What a `slow_down` response adds to the interval, per RFC 8628.
SLOW_DOWN_INCREMENT_SECONDS = 5

# poll_device_token outcomes.
GRANT_PENDING = "pending"
GRANT_SLOW_DOWN = "slow_down"
GRANT_GRANTED = "granted"


class SpotifyAuthError(Exception):
    """Token exchange or refresh was rejected by Spotify."""


class DeviceAuthorizationError(SpotifyAuthError):
    """A device authorization ended without credentials.

    `reason` is Spotify's own error code -- `access_denied` when the user
    declines, `expired_token` when they never finish -- so callers can phrase
    those two very differently for the user.
    """

    def __init__(self, reason, message=None):
        super().__init__(message or reason)
        self.reason = reason


def _post_form(url, fields):
    """POST a form. Returns (status, parsed_body). Never raises on 4xx.

    The body is returned rather than logged: on the token endpoint it can carry
    credentials, and callers only ever need to branch on `error`.
    """
    body = urllib.parse.urlencode(fields).encode("ascii")
    request = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8", "replace"))
        except ValueError:
            return exc.code, {}
    except urllib.error.URLError as exc:
        raise SpotifyAuthError("could not reach Spotify: %s" % exc.reason) from exc


def _post_token(fields):
    status, payload = _post_form(TOKEN_ENDPOINT, fields)
    if status != 200:
        # Never echo the body -- it can quote the credential back at us.
        raise SpotifyAuthError("Spotify rejected the token request (HTTP %s)" % status)
    return payload


def start_device_authorization():
    """Begin a device authorization. Blocking (network).

    Returns the raw Spotify payload: `device_code` (the secret we poll with and
    must never show anyone), `user_code` (the six characters the user sees),
    `verification_uri_complete` (that code pre-filled into the pairing page),
    `interval`, and `expires_in`.
    """
    status, payload = _post_form(DEVICE_AUTHORIZATION_ENDPOINT, {
        "client_id": KEYMASTER_CLIENT_ID,
        "scope": " ".join(SCOPES),
    })
    if status != 200 or "device_code" not in payload:
        raise SpotifyAuthError(
            "Spotify would not start a device authorization (HTTP %s)" % status)

    payload.setdefault("interval", MIN_POLL_INTERVAL_SECONDS)
    payload["interval"] = max(int(payload["interval"]), MIN_POLL_INTERVAL_SECONDS)
    return payload


def poll_device_token(device_code):
    """One poll of a pending device authorization. Blocking (network).

    Returns (status, credentials) where status is GRANT_PENDING or
    GRANT_SLOW_DOWN with credentials None, or GRANT_GRANTED with the blob to
    store. Raises DeviceAuthorizationError once the authorization is over --
    the user declined, or it expired -- and SpotifyAuthError on anything else.

    Callers must wait `interval` between polls and lengthen it on
    GRANT_SLOW_DOWN; Spotify escalates to hard failures otherwise.
    """
    status, payload = _post_form(TOKEN_ENDPOINT, {
        "client_id": KEYMASTER_CLIENT_ID,
        "grant_type": DEVICE_CODE_GRANT,
        "device_code": device_code,
    })
    if status == 200:
        return GRANT_GRANTED, _credentials_from_payload(payload)

    error = payload.get("error")
    if error == "authorization_pending":
        return GRANT_PENDING, None
    if error == "slow_down":
        return GRANT_SLOW_DOWN, None
    if error in ("access_denied", "expired_token"):
        raise DeviceAuthorizationError(error)
    raise SpotifyAuthError(
        "Spotify rejected the device authorization (HTTP %s, %s)" % (status, error))


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


def refresh_credentials(credentials):
    """Mint a fresh access token from a stored refresh token. Blocking.

    Returns (credentials, rotated) where `rotated` is True if the refresh token
    itself changed and the caller must persist the new blob. Keymaster rotates
    on every refresh and revokes the previous token immediately, so `rotated`
    is in practice always True -- see music/credentials.py.
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
