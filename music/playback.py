import asyncio
import logging

import discord

from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.metadata import TrackId

logger = logging.getLogger("music.playback")


def ensure_opus_loaded():
    # discord.py's find_library('opus') doesn't always resolve libopus.so.0
    # (no libopus-dev/libopus.so symlink on a slim image) even though the
    # runtime lib is present -- load it explicitly rather than relying on
    # auto-detection. Safe to call repeatedly.
    if not discord.opus.is_loaded():
        discord.opus.load_opus("libopus.so.0")


def _build_track_source(session, track_uri, quality=AudioQuality.VERY_HIGH):
    # Blocking: resolves track metadata/CDN over the network and spawns ffmpeg.
    track_id = TrackId.from_uri(track_uri)
    loaded = session.content_feeder().load(track_id, VorbisOnlyAudioQuality(quality), False, None)
    ogg_stream = loaded.input_stream.stream()
    source = discord.FFmpegPCMAudio(ogg_stream, pipe=True)
    return source, ogg_stream


async def join(voice_channel):
    """Connect to a voice channel, returning the VoiceClient."""
    return await voice_channel.connect()


async def leave(voice_client):
    """Stop any playback and disconnect from voice."""
    if voice_client is None:
        return
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    await voice_client.disconnect(force=True)


async def play_track(voice_client, session, track_uri, *, loop=None, after=None):
    """Fetch a track and play it on an already-connected VoiceClient.

    The fetch (network + ffmpeg spawn) runs off the event loop. `after(error)`
    is called (if given) once playback finishes, after the underlying
    librespot stream has been closed.
    """
    ensure_opus_loaded()
    loop = loop or asyncio.get_event_loop()
    source, ogg_stream = await loop.run_in_executor(None, _build_track_source, session, track_uri)

    def _after(error):
        try:
            ogg_stream.close()
        except Exception:
            logger.exception("error closing librespot stream after playback")
        if after is not None:
            after(error)

    voice_client.play(source, after=_after)
    return source
