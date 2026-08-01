import logging
from datetime import datetime, timezone

from librespot.core import Session
from librespot.proto import Authentication_pb2 as Authentication

logger = logging.getLogger("music.session_manager")

_sessions = {}


def _login_credentials_from_json(credentials_json):
    # librespot-python@18104622's Session.Builder().stored_file()/.stored() only
    # parse a {"type", "credentials"} or {"auth_type", "auth_data"} blob shape.
    # That is NOT what OAuth.save_creds() writes (`type: OAUTH_PKCE_TOKEN`,
    # `access_token`, `refresh_token`, `expires_at`) -- feeding one through the
    # other silently yields no login_credentials and create() raises "You must
    # select an authentication method." So build the LoginCredentials directly,
    # the same way OAuth.get_credentials() does internally.
    access_token = credentials_json.get("access_token")
    if not access_token:
        raise ValueError("credentials blob is missing 'access_token'")

    expires_at = credentials_json.get("expires_at")
    if expires_at is not None:
        expiry = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            raise ValueError("stored Spotify credentials have expired; user needs to re-link")

    return Authentication.LoginCredentials(
        typ=Authentication.AuthenticationType.AUTHENTICATION_SPOTIFY_TOKEN,
        auth_data=access_token.encode("utf-8"),
    )


def build_session(credentials_json):
    """Build a librespot Session from a credentials blob shaped like OAuth.save_creds() output.

    Blocking -- opens a real connection to a Spotify access point. Must be run
    off the asyncio loop, e.g. via loop.run_in_executor(...).
    """
    builder = Session.Builder()
    builder.login_credentials = _login_credentials_from_json(credentials_json)
    return builder.create()


def get_session(member_id, credentials_json):
    """Return a cached Session for member_id, building one if needed. Blocking."""
    member_id = str(member_id)
    session = _sessions.get(member_id)
    if session is not None:
        return session
    session = build_session(credentials_json)
    _sessions[member_id] = session
    return session


def cache_session(member_id, session):
    """Register an already-built Session (e.g. one built during linking) in the cache."""
    _sessions[str(member_id)] = session


def close_session(member_id):
    session = _sessions.pop(str(member_id), None)
    if session is None:
        return
    try:
        session.close()
    except Exception:
        logger.exception("error closing librespot session for member %s", member_id)
