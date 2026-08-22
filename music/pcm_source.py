"""The bridge between librespot's PCM output and discord.py's audio player.

Two pieces:

- `PCMBuffer` -- a bounded FIFO written by the librespot pump thread and read by
  discord.py's AudioPlayer thread.
- `LibrespotPCMSource` -- a `discord.AudioSource` over that buffer.

**The buffer is bounded and its writer blocks when full, on purpose.** That is
not a memory optimisation: it is what paces playback. librespot's pipe backend
has no clock of its own and emits audio as fast as it can decode, relying
entirely on backpressure from whatever reads it. Remove the bound (or make the
writer drop instead of block) and librespot races through the user's queue at
decode speed -- measured in the 2026-08-15 spike at ~37 minutes of audio in 6.5
minutes of wall clock, which presents in the Spotify app as tracks skipping
past at high speed. See LIBRESPOT_RUST_PLAN.md Step 0.

The other half of the same coin: while a device is registered but idle,
librespot writes *nothing* (measured: 3840 bytes across 272 idle seconds). So
`read()` must synthesise silence rather than return `b''`, because discord.py
treats `b''` as end-of-track and stops playback.
"""
import logging
import threading

import discord

logger = logging.getLogger("music.pcm_source")

# discord.py's AudioPlayer reads one 20ms frame of 48kHz stereo s16le per tick.
FRAME_SIZE = 3840
SILENT_FRAME = b"\x00" * FRAME_SIZE

# How much decoded audio to hold. Bigger absorbs more scheduling jitter at the
# cost of latency between a Spotify app action and it being audible. One second
# is a starting point; tune this before reaching for anything cleverer.
DEFAULT_CAPACITY_BYTES = FRAME_SIZE * 50  # ~1s


class PCMBuffer:
    """Bounded byte FIFO. One writer thread, one reader thread."""

    def __init__(self, capacity_bytes=DEFAULT_CAPACITY_BYTES):
        self._capacity = capacity_bytes
        self._data = bytearray()
        self._condition = threading.Condition()
        self._closed = False
        self.underruns = 0
        # Monotonic count of everything ever written. The idle watchdog uses it
        # to tell "registered but nobody is playing" from "actively streaming";
        # buffer length alone can't, because a healthy stream is drained as
        # fast as it arrives.
        self.total_written = 0

    def write(self, chunk):
        """Append bytes, blocking while the buffer is full.

        Returns False once the buffer is closed. Chunks larger than the
        capacity are written in slices so an oversized read upstream cannot
        deadlock us.
        """
        offset = 0
        while offset < len(chunk):
            with self._condition:
                if self._closed:
                    return False
                while not self._closed and len(self._data) >= self._capacity:
                    self._condition.wait(timeout=1.0)
                if self._closed:
                    return False
                space = self._capacity - len(self._data)
                piece = chunk[offset:offset + space]
                self._data.extend(piece)
                offset += len(piece)
                self.total_written += len(piece)
                self._condition.notify_all()
        return True

    def read_frame(self, size=FRAME_SIZE):
        """Pop exactly `size` bytes, or return b'' without consuming anything.

        All-or-nothing deliberately: handing back a partial frame would shift
        every subsequent frame out of alignment.
        """
        with self._condition:
            if len(self._data) < size:
                return b""
            frame = bytes(self._data[:size])
            del self._data[:size]
            self._condition.notify_all()
            return frame

    def clear(self):
        with self._condition:
            self._data.clear()
            self._condition.notify_all()

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    @property
    def closed(self):
        return self._closed

    def __len__(self):
        with self._condition:
            return len(self._data)


class LibrespotPCMSource(discord.AudioSource):
    """discord.AudioSource over a PCMBuffer. Never signals end-of-track.

    A Connect receiver's session lasts as long as the user wants the device, so
    this source is deliberately endless -- silence during pauses, gaps and
    librespot restarts. Disconnecting is the caller's job (idle timeout, empty
    channel, unlink), never this class's.
    """

    def __init__(self, buffer, member_id=None):
        self._buffer = buffer
        self._member_id = member_id
        self._reported_underrun = False

    def is_opus(self):
        return False

    def read(self):
        frame = self._buffer.read_frame(FRAME_SIZE)
        if frame:
            self._reported_underrun = False
            return frame

        self._buffer.underruns += 1
        # Log the transition, not every 20ms tick -- an idle device underruns
        # 50 times a second and would drown the log.
        if not self._reported_underrun:
            logger.debug("PCM underrun for member %s; emitting silence", self._member_id)
            self._reported_underrun = True
        return SILENT_FRAME

    def cleanup(self):
        # The buffer outlives any single source (librespot restarts refill it),
        # so tearing it down here would be wrong. Ownership sits with
        # music.librespot_process.
        pass
