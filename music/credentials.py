"""Mint librespot access tokens from a member's stored Spotify credentials.

This is the bridge between `music.spotify_auth` (pure OAuth, no Django) and the
`SpotifyLink` row. It exists as its own module because librespot's supervisor
thread calls it on every spawn, so it must be synchronous and it must be safe
to call concurrently.

**Keymaster rotates the refresh token on every refresh and revokes the old one
immediately** (verified 2026-08-15: reusing a rotated token returns
`invalid_grant / "Refresh token revoked"`). Two consequences are baked into
`mint_access_token` and must not be optimised away:

1. The rotated token is persisted in the same critical section that mints it.
   Minting without persisting bricks the user's link.
2. Mints are serialised per member. Two concurrent refreshes would revoke each
   other and leave the user unlinked.
"""
import json
import logging
import threading

from helpers import spotifyStore
from music import spotify_auth

logger = logging.getLogger("music.credentials")


class NotLinkedError(Exception):
    """No usable Spotify credentials are stored for this member."""


_locks = {}
_locks_guard = threading.Lock()


def _lock_for(member_id):
    with _locks_guard:
        lock = _locks.get(member_id)
        if lock is None:
            lock = threading.Lock()
            _locks[member_id] = lock
        return lock


def mint_access_token(member_id):
    """Return a fresh access token for this member. Blocking; never on the loop.

    Always refreshes rather than reusing a stored token: the supervisor calls
    this per spawn (including restarts), and a token that is merely "not expired
    yet" can still die mid-session, which is exactly the failure mode librespot
    cannot recover from on its own.
    """
    member_id = str(member_id)
    with _lock_for(member_id):
        link = spotifyStore.getLinkSync(member_id)
        if link is None:
            raise NotLinkedError("member %s has no Spotify link" % member_id)

        try:
            credentials = json.loads(link["credentials"])
        except (TypeError, ValueError) as exc:
            raise NotLinkedError("stored credentials are not valid JSON") from exc

        updated, rotated = spotify_auth.refresh_credentials(credentials)

        # Persist BEFORE handing the token out. Spotify has already revoked the
        # previous refresh token by this point, so if we crash between here and
        # the write, the user is locked out and must re-link.
        if not spotifyStore.setCredentialsSync(member_id, json.dumps(updated)):
            raise NotLinkedError("link disappeared while refreshing")
        if rotated:
            logger.info("persisted rotated refresh token for member %s", member_id)

        return updated["access_token"]


def needs_relink(credentials_blob):
    """True if a stored blob predates the keymaster switch (or is unreadable).

    Credentials minted by the old third-party dev app cannot be used: login5
    refuses non-first-party clients, so librespot could never start with them.
    Treat those rows as unlinked rather than failing a refresh the user can do
    nothing about.
    """
    try:
        credentials = json.loads(credentials_blob)
    except (TypeError, ValueError):
        return True
    if credentials.get("client_id") != spotify_auth.KEYMASTER_CLIENT_ID:
        return True
    return not credentials.get("refresh_token")


def token_provider(member_id):
    """A zero-arg callable for music.librespot_process.LibrespotProcess."""
    def provide():
        return mint_access_token(member_id)
    return provide


def forget(member_id):
    with _locks_guard:
        _locks.pop(str(member_id), None)
