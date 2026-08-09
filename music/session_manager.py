import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from librespot.core import Session
from librespot.proto import Authentication_pb2 as Authentication
from librespot.proto import Connect_pb2 as Connect

DEFAULT_DEVICE_NAME = "Discord Bot"

logger = logging.getLogger("music.session_manager")

_sessions = {}

# Every librespot/Spotify blocking call (session login, ConnectDevice
# registration, put_state) runs here instead of asyncio's shared default
# executor. librespot is synchronous and thread-heavy on its own (a raw TCP
# "Receiver" thread per session, plus -- since the dealer-connect fix -- a
# real websocket thread per session too); routing all of it through a
# dedicated pool keeps it from queueing behind or contending with unrelated
# executor work elsewhere in the bot (Django DB calls, image processing,
# etc.) sharing the default pool. Matches the isolation the user already
# proved out in another branch (librespot driven from its own thread rather
# than loop.run_in_executor(None, ...)). Not unbounded -- capped so a burst
# of concurrent ,play calls can't spawn unlimited OS threads.
SPOTIFY_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="spotify-worker")


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


def build_session(credentials_json, device_name=DEFAULT_DEVICE_NAME):
    """Build a librespot Session from a credentials blob shaped like OAuth.save_creds() output.

    Blocking -- opens a real connection to a Spotify access point (this also
    opens the session's dealer websocket -- Session.authenticate() calls
    self.dealer().connect() internally regardless of whether anything ever
    registers a Connect-state listener on it). Must be run off the asyncio
    loop, e.g. via loop.run_in_executor(...).

    device_name/device_type are what shows up for this device in the user's
    Spotify app once something (music/connect_device.py) registers Connect
    state for this session -- SPEAKER is a more accurate default than
    librespot's own "COMPUTER"/"librespot-python" for how this bot actually
    plays audio.
    """
    builder = Session.Builder()
    builder.set_device_name(device_name)
    builder.set_device_type(Connect.DeviceType.SPEAKER)
    builder.login_credentials = _login_credentials_from_json(credentials_json)
    # Timed deliberately -- diagnosing a live event-loop stall right around
    # ,play (main gateway heartbeats missed, voice disconnects ~10s in). This
    # call is blocking librespot login (network + dealer socket + Receiver
    # thread startup); the caller is responsible for running it off the
    # event loop, but if this itself takes unexpectedly long that's a real
    # lead, not a red herring. See SPOTIFY_CONTEXT.md.
    started = time.monotonic()
    session = builder.create()
    logger.info("build_session: Session.Builder().create() took %.2fs", time.monotonic() - started)
    return session


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
