import base64
import logging
import os
import sys
import threading
import time

from librespot import Version
from librespot.core import ApResolver, DealerClient
from librespot.mercury import MercuryRequests
from librespot.proto import Connect_pb2 as Connect
from librespot.structure import MessageListener, RequestListener

# librespot-python@18104622's proto/TransferState_pb2.py (and Playback_pb2,
# Queue_pb2, Session_pb2, Context_pb2, ContextPage_pb2, Canvaz_pb2) use
# old-style bare `import Foo_pb2` statements instead of relative/package
# imports, which raise ModuleNotFoundError under normal Python 3 import
# rules -- `from librespot.proto import TransferState_pb2` fails outright.
# Confirmed by reading the installed package; this isn't specific to this
# repo. Putting librespot/proto on sys.path once, here, lets those sibling
# imports resolve the same way they would if run from inside that directory.
# Contained to this module's import time; only adds one directory, and the
# generated names (Playback_pb2 etc.) don't collide with anything else.
try:
    from librespot.proto import TransferState_pb2 as TransferState
except ModuleNotFoundError:
    import librespot.proto as _librespot_proto
    _proto_dir = os.path.dirname(_librespot_proto.__file__)
    if _proto_dir not in sys.path:
        sys.path.insert(0, _proto_dir)
    from librespot.proto import TransferState_pb2 as TransferState

logger = logging.getLogger("music.connect_device")

DEALER_MESSAGE_URIS = [
    "hm://pusher/v1/connections/",
    "hm://connect-state/v1/connect/volume",
    "hm://connect-state/v1/cluster",
]
DEALER_REQUEST_URI_PREFIX = "hm://connect-state/v1/"


def _patch_dealer_connect():
    """Real fix for a librespot-python bug, not a workaround: DealerClient
    .connect() builds a ConnectionHolder wrapping a bare
    websocket.WebSocketApp(url) but never assigns its on_open/on_message/
    on_failure methods as that WebSocketApp's callbacks, and never calls
    run_forever() (or starts a thread to run it). Confirmed by reading the
    installed source directly: websocket.WebSocketApp(url) is constructed
    with no on_open/on_message/on_error kwargs, and `run_forever` does not
    appear anywhere else in core.py. The dealer socket is therefore
    structurally incapable of ever connecting -- nothing is listening for
    Spotify to open the connection, let alone read from it.

    This matters a lot here: the whole Connect receiver is driven entirely by
    messages arriving over this socket (the pusher connection_id first, which
    triggers put_state(NEW_DEVICE) -- see ConnectDevice.on_message -- then
    transfer/play/pause commands). With the socket dead, the device can never
    appear in the user's Spotify app, full stop, regardless of anything in
    this bot's own code.

    Replaces DealerClient.connect() with a corrected version that wires the
    ConnectionHolder's callbacks onto the WebSocketApp and runs its event
    loop on a dedicated daemon thread. Applied once, process-wide, at import
    time; idempotent via a marker attribute so importing this module twice
    doesn't double-patch.
    """
    if getattr(DealerClient.connect, "_discordbot_patched", False):
        return

    def connect(self):
        connection = DealerClient.ConnectionHolder(
            self._DealerClient__session,
            self,
            "wss://{}/?access_token={}".format(
                ApResolver.get_random_dealer(),
                self._DealerClient__session.tokens().get("playlist-read"),
            ),
        )
        ws = connection._ConnectionHolder__ws
        ws.on_open = connection.on_open
        ws.on_message = connection.on_message
        ws.on_error = connection.on_failure
        ws.on_close = lambda ws, code, msg: connection.on_failure(
            ws, "closed: {} {}".format(code, msg))
        self._DealerClient__connection = connection
        threading.Thread(target=ws.run_forever, daemon=True,
                         name="librespot-dealer-ws").start()

    connect._discordbot_patched = True
    DealerClient.connect = connect


_patch_dealer_connect()


def _isolate_dealer_listener_state(dealer):
    """Work around a real bug in librespot-python@18104622's DealerClient:
    __message_listeners/__request_listeners (and their locks) are declared
    at class-body scope, and __init__ never assigns them on self. Every
    DealerClient instance therefore shares the *same* dict objects. With one
    Session/DealerClient per linked Discord user (this bot's architecture),
    that means messages/requests delivered on user A's dealer websocket get
    fanned out to every listener ever registered by *any* user's
    DealerClient, including user B's -- on_message/on_request never receive
    anything identifying which session's socket the frame arrived on, so
    there's no way to filter after the fact. Left alone, one user's Connect
    commands could reach another user's handler.

    Giving each instance its own dicts here restores per-instance isolation.
    Confirmed by reading librespot/core.py directly, not assumed.

    Idempotent per dealer instance -- only replaces a dict that's still the
    shared class-level one, so calling this more than once on the same
    dealer (e.g. if a caller ever constructs a second ConnectDevice against
    an already-isolated session, which shouldn't normally happen but isn't
    otherwise guarded against) won't wipe out listeners already registered
    on it.
    """
    if "_DealerClient__message_listeners" not in vars(dealer):
        dealer._DealerClient__message_listeners = {}
    if "_DealerClient__request_listeners" not in vars(dealer):
        dealer._DealerClient__request_listeners = {}


class ConnectDevice(MessageListener, RequestListener):
    """Registers a librespot Session as a Spotify Connect device and routes
    remote commands (transfer/play/pause/resume from the user's Spotify app)
    to a caller-supplied handler.

    All librespot dealer callbacks (on_message/on_request) run on
    librespot's own worker thread pool, never the asyncio loop. `handler`'s
    methods are called from that thread -- bridge to asyncio yourself (e.g.
    asyncio.run_coroutine_threadsafe), the way
    music/phase3_smoke_test.py bridges its `after` callback. `handler` needs:
      - on_transfer(track_uri, position_ms, is_paused)
      - on_resume()
      - on_pause()
    Exceptions raised from those are caught and reported upstream as
    UPSTREAM_ERROR; they don't crash the dealer worker thread.

    NOT verified against a live dealer connection or the Spotify app in this
    session -- built from reading librespot-python's actual proto
    definitions and its (unfinished, never-instantiated) librespot_player/
    reference sketch in the same repo, not from observed real traffic. See
    SPOTIFY_CONTEXT.md for what specifically needs live verification.
    """

    def __init__(self, session, handler, device_name=None, volume_steps=64, initial_volume=65536):
        self._session = session
        self._handler = handler
        self._connection_id = None
        self._device_info = Connect.DeviceInfo(
            can_play=True,
            capabilities=Connect.Capabilities(
                can_be_player=True,
                command_acks=True,
                is_controllable=True,
                is_observable=True,
                gaia_eq_connect_id=True,
                needs_full_player_state=False,
                supported_types=["audio/track"],
                supports_command_request=True,
                supports_gzip_pushes=True,
                supports_logout=True,
                supports_playlist_v2=True,
                supports_rename=False,
                supports_transfer_command=True,
                volume_steps=volume_steps,
            ),
            client_id=MercuryRequests.keymaster_client_id,
            device_id=session.device_id(),
            device_software_version=Version.version_string(),
            device_type=session.device_type(),
            name=device_name or session.device_name(),
            spirc_version="3.2.6",
            volume=initial_volume,
        )

        dealer = session.dealer()
        _isolate_dealer_listener_state(dealer)
        dealer.add_message_listener(self, DEALER_MESSAGE_URIS)
        dealer.add_request_listener(self, DEALER_REQUEST_URI_PREFIX)

    def close(self):
        try:
            dealer = self._session.dealer()
            dealer.remove_message_listener(self)
            dealer.remove_request_listener(self)
        except Exception:
            logger.exception("error tearing down Connect listeners")

    # -- MessageListener --
    def on_message(self, uri, headers, payload):
        if uri.startswith("hm://pusher/v1/connections/"):
            connection_id = headers.get("Spotify-Connection-Id")
            if not connection_id:
                logger.warning("pusher connections message had no Spotify-Connection-Id header: %r", headers)
                return
            self._connection_id = connection_id
            logger.info("Connect device %r got a connection_id, registering as NEW_DEVICE", self._device_info.name)
            self.put_state(Connect.PutStateReason.NEW_DEVICE)
        else:
            logger.debug("Unhandled Connect message on %s: %r", uri, payload)

    # -- RequestListener --
    def on_request(self, message_id, pid, sender, command):
        logger.info("Connect command from device %s: %r", sender, command)
        endpoint = command.get("endpoint") if isinstance(command, dict) else None
        try:
            if endpoint == "transfer":
                self._handle_transfer(command)
            elif endpoint in ("play", "resume"):
                self._handler.on_resume()
            elif endpoint == "pause":
                self._handler.on_pause()
            elif endpoint in ("skip_next", "skip_prev", "seek_to"):
                # No queue/seek support yet -- SPOTIFY_CONNECT_PLAN.md Phase 6.
                logger.warning("Connect endpoint %r isn't implemented yet", endpoint)
                return DealerClient.RequestResult.DEVICE_DOES_NOT_SUPPORT_COMMAND
            else:
                logger.warning("Unhandled Connect endpoint %r -- full command: %r", endpoint, command)
                return DealerClient.RequestResult.DEVICE_DOES_NOT_SUPPORT_COMMAND
        except Exception:
            logger.exception("error handling Connect command %r", endpoint)
            return DealerClient.RequestResult.UPSTREAM_ERROR
        return DealerClient.RequestResult.SUCCESS

    def _handle_transfer(self, command):
        data_b64 = command.get("data") if isinstance(command, dict) else None
        if not isinstance(data_b64, str):
            logger.warning("transfer command had no 'data' payload: %r", command)
            return
        transfer = TransferState.TransferState()
        transfer.ParseFromString(base64.b64decode(data_b64))
        track_uri = transfer.playback.current_track.uri or None
        if not track_uri:
            logger.warning("transfer command had no playback.current_track.uri: %r", transfer)
            return
        self._handler.on_transfer(
            track_uri,
            transfer.playback.position_as_of_timestamp,
            transfer.playback.is_paused,
        )

    def put_state(self, reason, is_playing=None, is_paused=None, track_uri=None, position_ms=0):
        """Report device/player state to Spotify. Blocking (network call)."""
        if self._connection_id is None:
            logger.warning("put_state(%s) called before a connection_id was known -- skipping", reason)
            return

        request = Connect.PutStateRequest(
            device=Connect.Device(device_info=self._device_info),
            member_type=Connect.MemberType.CONNECT_STATE,
            put_state_reason=reason,
            is_active=True,
            client_side_timestamp=int(time.time() * 1000),
        )
        if track_uri is not None:
            request.device.player_state.track.uri = track_uri
            request.device.player_state.track.provider = "context"
            request.device.player_state.is_playing = bool(is_playing)
            request.device.player_state.is_paused = bool(is_paused)
            request.device.player_state.position_as_of_timestamp = position_ms
            request.device.player_state.timestamp = int(time.time() * 1000)

        self._session.api().put_connect_state(self._connection_id, request)
