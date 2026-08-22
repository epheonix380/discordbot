"""Voice-channel plumbing. Deliberately knows nothing about Spotify.

Audio no longer originates here: librespot decodes it and music/pcm_source.py
feeds it to discord.py. What's left is joining, moving and leaving voice.
"""
import logging

import discord

logger = logging.getLogger("music.playback")


def ensure_opus_loaded():
    # discord.py's find_library('opus') doesn't always resolve libopus.so.0
    # (no libopus-dev/libopus.so symlink on a slim image) even though the
    # runtime lib is present -- load it explicitly rather than relying on
    # auto-detection. Safe to call repeatedly. Without this, voice silently
    # produces nothing.
    if not discord.opus.is_loaded():
        discord.opus.load_opus("libopus.so.0")


async def join_or_move(client, voice_channel):
    """Connect to (or move into) a voice channel, returning the VoiceClient."""
    guild = voice_channel.guild
    voice_client = discord.utils.get(client.voice_clients, guild=guild)

    if voice_client is not None and not voice_client.is_connected():
        # A half-dead voice client stays registered against the guild in
        # discord.py's own state, so connect() would raise "Already connected
        # to a voice channel." rather than reconnecting. Drop it first.
        logger.info("discarding stale voice client for guild %s before rejoining", guild.id)
        try:
            await leave(voice_client)
        except Exception:
            logger.warning("failed to cleanly drop stale voice client for guild %s",
                           guild.id, exc_info=True)
        voice_client = None

    if voice_client is None:
        return await voice_channel.connect()
    if voice_client.channel.id != voice_channel.id:
        await voice_client.move_to(voice_channel)
    return voice_client


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
