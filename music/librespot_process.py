"""One librespot process per linked Discord member, supervised.

Data path (LIBRESPOT_RUST_PLAN.md 3.2):

    Spotify CDN -> librespot (decrypt + decode -> 44.1kHz s16le)
                -> OS pipe                       <- kernel; Python not involved
                -> ffmpeg (resample to 48kHz)
                -> pump thread -> PCMBuffer -> discord.py

Why a pump thread and a buffer instead of handing ffmpeg's stdout straight to
discord.py: librespot *will* be restarted underneath a live voice connection
(see below), and swapping an fd out from under `vc.play()` is not something
discord.py tolerates. The buffer is the stable thing; the processes behind it
come and go.

**Restarts are mandatory, not just defensive.** librespot reconnects a dropped
session using the credentials it was started with (main.rs:2042-2052) and never
refreshes that in-memory copy, so a process older than its access token's hour
re-authenticates with a dead token on the first network blip and exits(1). We
mint a fresh token on every spawn, which makes that exit self-healing. librespot
also exits when its own reconnects exceed its internal rate limit, so this
supervisor keeps its own backoff -- without one, a persistently failing account
would spawn processes in a tight loop.

Everything here is synchronous/blocking; callers run it off the event loop.
"""
import logging
import os
import shutil
import subprocess
import threading
import time

from music.pcm_source import PCMBuffer

logger = logging.getLogger("music.librespot_process")

LIBRESPOT_BIN = os.environ.get("LIBRESPOT_BIN", "/usr/local/bin/librespot")
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")

DEVICE_NAME = os.environ.get("SPOTIFY_DEVICE_NAME", "Discord Bot")

# Premium accounts get 320; librespot's own default is 160.
BITRATE = os.environ.get("LIBRESPOT_BITRATE", "320")

# Cap concurrent processes. Each is a real process with a TCP connection and a
# few tens of MB RSS, on a 2-core / 3GB host that also runs the bot.
MAX_PROCESSES = int(os.environ.get("LIBRESPOT_MAX_PROCESSES", "5"))

# librespot decodes at 44.1kHz; Discord requires 48kHz stereo s16le. ffmpeg
# exists in this pipeline only to resample -- librespot has no --sample-rate.
SOURCE_RATE = "44100"
TARGET_RATE = "48000"

RESTART_BACKOFF_START_SECONDS = 1.0
RESTART_BACKOFF_MAX_SECONDS = 60.0
# A run that lasted at least this long is treated as healthy, so the next
# failure starts from a short backoff again rather than the escalated one.
RESTART_BACKOFF_RESET_SECONDS = 60.0

STOP_TIMEOUT_SECONDS = 5


class LibrespotProcessError(Exception):
    pass


class LibrespotProcess:
    """Supervises one member's librespot+ffmpeg pair and fills a PCMBuffer."""

    def __init__(self, member_id, token_provider, *, device_name=DEVICE_NAME,
                 bitrate=BITRATE, buffer=None):
        self.member_id = str(member_id)
        # Callable[[], str] returning a *fresh* access token. Injected rather
        # than done here so this module stays free of Django and Discord,
        # matching the split the rest of music/ already uses.
        self._token_provider = token_provider
        self._device_name = device_name
        self._bitrate = str(bitrate)

        self.buffer = buffer if buffer is not None else PCMBuffer()

        self._librespot = None
        self._ffmpeg = None
        self._process_lock = threading.Lock()
        self._supervisor = None
        self._stopping = threading.Event()
        self._started_at = None
        self.restart_count = 0
        self.last_error = None

    # ----- lifecycle -------------------------------------------------

    def start(self):
        """Start the supervisor thread. Returns once the first spawn is attempted."""
        if self._supervisor is not None:
            return
        if not shutil.which(LIBRESPOT_BIN) and not os.path.exists(LIBRESPOT_BIN):
            raise LibrespotProcessError("librespot binary not found at %s" % LIBRESPOT_BIN)

        first_spawn = threading.Event()
        self._supervisor = threading.Thread(
            target=self._supervise, args=(first_spawn,),
            name="librespot-%s" % self.member_id, daemon=True)
        self._supervisor.start()
        # Wait briefly so callers surface an immediate failure (bad token, no
        # binary) rather than replying "ready" to a process that never started.
        first_spawn.wait(timeout=20)
        if self.last_error is not None and not self.is_running:
            raise LibrespotProcessError(str(self.last_error))

    def stop(self):
        """Terminate the processes and stop supervising. Idempotent."""
        self._stopping.set()
        self.buffer.close()
        self._kill_processes()
        supervisor = self._supervisor
        if supervisor is not None and supervisor is not threading.current_thread():
            supervisor.join(timeout=STOP_TIMEOUT_SECONDS + 2)
        self._supervisor = None

    @property
    def is_running(self):
        with self._process_lock:
            return self._librespot is not None and self._librespot.poll() is None

    @property
    def uptime_seconds(self):
        return None if self._started_at is None else time.monotonic() - self._started_at

    # ----- internals -------------------------------------------------

    def _supervise(self, first_spawn):
        backoff = RESTART_BACKOFF_START_SECONDS
        while not self._stopping.is_set():
            run_started = time.monotonic()
            try:
                self._spawn()
            except Exception as exc:
                self.last_error = exc
                logger.exception("failed to spawn librespot for member %s", self.member_id)
            else:
                self.last_error = None
            finally:
                first_spawn.set()

            if self.is_running:
                self._pump()  # blocks until the chain dies or we are stopping

            self._kill_processes()
            if self._stopping.is_set():
                break

            ran_for = time.monotonic() - run_started
            if ran_for >= RESTART_BACKOFF_RESET_SECONDS:
                backoff = RESTART_BACKOFF_START_SECONDS
            self.restart_count += 1
            logger.warning(
                "librespot for member %s exited after %.1fs (restart #%d); retrying in %.0fs",
                self.member_id, ran_for, self.restart_count, backoff)

            if self._stopping.wait(timeout=backoff):
                break
            backoff = min(backoff * 2, RESTART_BACKOFF_MAX_SECONDS)

    def _spawn(self):
        # Fresh token per spawn -- see the module docstring.
        token = self._token_provider()
        if not token:
            raise LibrespotProcessError("token provider returned no access token")

        # The token goes in the environment, never argv: argv is world-readable
        # through /proc, and librespot only redacts it in its own logs.
        env = dict(os.environ, LIBRESPOT_ACCESS_TOKEN=token)

        librespot_cmd = [
            LIBRESPOT_BIN,
            "--name", self._device_name,
            "--device-type", "speaker",
            "--backend", "pipe",          # no --device => stdout
            "--format", "S16",
            "--bitrate", self._bitrate,
            "--disable-discovery",        # the user's phone is not on this LAN
            "--disable-audio-cache",      # disk hygiene; nothing needs it
            # Without these the softvol Log(60.0) curve at the volume the app
            # reports attenuates roughly 30dB (measured peak 1037/32767).
            "--volume-ctrl", "fixed",
            "--initial-volume", "100",
        ]

        ffmpeg_cmd = [
            FFMPEG_BIN, "-loglevel", "warning",
            "-f", "s16le", "-ar", SOURCE_RATE, "-ac", "2", "-i", "pipe:0",
            "-f", "s16le", "-ar", TARGET_RATE, "-ac", "2", "pipe:1",
        ]

        with self._process_lock:
            librespot = subprocess.Popen(
                librespot_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            try:
                ffmpeg = subprocess.Popen(
                    ffmpeg_cmd, stdin=librespot.stdout,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except Exception:
                librespot.kill()
                raise
            # ffmpeg owns the read end now; dropping our copy means librespot
            # gets SIGPIPE if ffmpeg goes away.
            librespot.stdout.close()

            self._librespot = librespot
            self._ffmpeg = ffmpeg
            self._started_at = time.monotonic()

        threading.Thread(
            target=self._drain_stderr, args=(librespot,),
            name="librespot-log-%s" % self.member_id, daemon=True).start()

        logger.info("spawned librespot for member %s (pid %s -> ffmpeg pid %s)",
                    self.member_id, librespot.pid, ffmpeg.pid)

    def _pump(self):
        """Move PCM from ffmpeg into the buffer until the chain dies."""
        ffmpeg = self._ffmpeg
        if ffmpeg is None or ffmpeg.stdout is None:
            return
        try:
            while not self._stopping.is_set():
                chunk = ffmpeg.stdout.read(4096)
                if not chunk:
                    break  # ffmpeg exited, i.e. librespot died or we are done
                if not self.buffer.write(chunk):
                    break  # buffer closed => teardown
        except (ValueError, OSError):
            # Pipe closed underneath us during teardown.
            pass

    def _drain_stderr(self, process):
        """librespot's stderr is the only visibility we have into it."""
        stream = process.stderr
        if stream is None:
            return
        try:
            for raw in iter(stream.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip()
                if not line:
                    continue
                lowered = line.lower()
                if "error" in lowered or "denied" in lowered:
                    logger.error("librespot[%s] %s", self.member_id, line)
                elif "warn" in lowered:
                    logger.warning("librespot[%s] %s", self.member_id, line)
                else:
                    logger.info("librespot[%s] %s", self.member_id, line)
        except (ValueError, OSError):
            pass

    def _kill_processes(self):
        with self._process_lock:
            processes = [p for p in (self._ffmpeg, self._librespot) if p is not None]
            self._ffmpeg = None
            self._librespot = None
            self._started_at = None

        for process in processes:
            if process.poll() is not None:
                continue
            try:
                process.terminate()
            except OSError:
                continue
        for process in processes:
            try:
                process.wait(timeout=STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                logger.warning("librespot/ffmpeg pid %s ignored SIGTERM; killing", process.pid)
                try:
                    process.kill()
                    process.wait(timeout=STOP_TIMEOUT_SECONDS)
                except (OSError, subprocess.TimeoutExpired):
                    logger.error("could not reap pid %s", process.pid)
        for process in processes:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except (ValueError, OSError):
                        pass


# ----- per-member registry ---------------------------------------------

_processes = {}
_registry_lock = threading.Lock()


def get(member_id):
    with _registry_lock:
        return _processes.get(str(member_id))


def ensure_running(member_id, token_provider, **kwargs):
    """Get-or-start this member's librespot. Blocking; run it off the loop."""
    member_id = str(member_id)
    with _registry_lock:
        existing = _processes.get(member_id)
        if existing is not None:
            if existing.is_running or existing._supervisor is not None:
                return existing
            _processes.pop(member_id, None)
        if len(_processes) >= MAX_PROCESSES:
            raise LibrespotProcessError(
                "too many active Spotify sessions (%d); try again later" % MAX_PROCESSES)
        process = LibrespotProcess(member_id, token_provider, **kwargs)
        _processes[member_id] = process

    try:
        process.start()
    except Exception:
        with _registry_lock:
            _processes.pop(member_id, None)
        raise
    return process


def stop(member_id):
    """Stop and reap this member's librespot. Safe to call when none exists."""
    with _registry_lock:
        process = _processes.pop(str(member_id), None)
    if process is not None:
        process.stop()
    return process is not None


def stop_all():
    with _registry_lock:
        processes = list(_processes.values())
        _processes.clear()
    for process in processes:
        process.stop()


def active_count():
    with _registry_lock:
        return len(_processes)
