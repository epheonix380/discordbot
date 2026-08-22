"""`,play` and `,spotify` -- the Discord surface of the Connect receiver.

The flow, end to end:

    ,play  ->  in a voice channel?  ->  linked?
                                          no  -> DM an auth link; user pastes
                                                 the redirect URL back (see
                                                 music/oauth_flow.py for why it
                                                 cannot be automatic)
                                          yes -> join voice, spawn librespot,
                                                 attach its PCM to the voice
                                                 client

Nothing plays as a result of `,play` itself. The bot becomes a Spotify Connect
device named "Discord Bot"; playback starts when the user picks it in their own
Spotify app. Free-text search / `,play <track>` were removed deliberately and
must not come back -- see SPOTIFY_CONTEXT.md's "Scope change".
"""
import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

import discord

from helpers import spotifyStore
from music import credentials, librespot_process, oauth_flow, playback, spotify_auth
from music.pcm_source import LibrespotPCMSource

logger = logging.getLogger("music.commands")

PREMIUM_NOTICE = "**Spotify Premium is required** to stream through the bot."
DEVICE_NAME = librespot_process.DEVICE_NAME

# Every Spotify/librespot blocking call (token refresh, process spawn) runs
# here rather than asyncio's shared default executor, so it can't queue behind
# or contend with unrelated executor work elsewhere in the bot (Django DB
# calls, image processing). Carried over from the old session_manager.
SPOTIFY_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="spotify-worker")

# How long a registered device may sit with no audio before we disconnect and
# reap the process. A default, not a considered policy -- the user has not
# picked one yet.
IDLE_TIMEOUT_SECONDS = int(os.environ.get("SPOTIFY_IDLE_TIMEOUT_SECONDS", "600"))
IDLE_CHECK_INTERVAL_SECONDS = 30

_idle_tasks = {}  # str(member_id) -> asyncio.Task


def _executor_call(loop, func, *args):
    return loop.run_in_executor(SPOTIFY_EXECUTOR, func, *args)


async def _dm(user, content):
    """DM a user; returns False if their DMs are closed."""
    try:
        await user.send(content)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


async def _send_link(message, auth_url):
    body = (
        "**Link your Spotify account** " + PREMIUM_NOTICE + "\n\n"
        "1. Open this link and authorize:\n" + auth_url + "\n\n"
        "2. Your browser will then fail to load a `127.0.0.1:5588` page — "
        "**that's expected**, nothing is supposed to be listening there.\n\n"
        "3. Copy the **whole URL** out of your browser's address bar and paste "
        "it back to me here in DM.\n\n"
        "_You only have to do this once._"
    )
    if await _dm(message.author, body):
        if message.guild is not None:
            await message.channel.send("Check your DMs — I've sent you a Spotify link.")
    else:
        await message.channel.send(
            "I couldn't DM you (your DMs may be closed). Open them and run `,play` again."
        )


async def _stop_session(member_id, guild=None, client=None):
    """Tear down one member's playback: leave voice, reap librespot."""
    member_id = str(member_id)

    task = _idle_tasks.pop(member_id, None)
    if task is not None:
        task.cancel()

    if client is not None and guild is not None:
        voice_client = discord.utils.get(client.voice_clients, guild=guild)
        if voice_client is not None:
            try:
                await playback.leave(voice_client)
            except Exception:
                logger.warning("failed to leave voice for member %s", member_id, exc_info=True)

    loop = asyncio.get_event_loop()
    await _executor_call(loop, librespot_process.stop, member_id)
    credentials.forget(member_id)


async def _start_session(client, message, voice_channel):
    """Join voice and bring up this member's Connect device. Returns an error
    string for the user, or None on success."""
    member_id = str(message.author.id)
    loop = asyncio.get_event_loop()

    started = time.monotonic()
    try:
        process = await _executor_call(
            loop, librespot_process.ensure_running, member_id,
            credentials.token_provider(member_id))
    except credentials.NotLinkedError:
        return "I don't have working Spotify credentials for you. Run `,spotify unlink`, then `,play` to relink."
    except spotify_auth.SpotifyAuthError:
        logger.exception("token refresh failed for member %s", member_id)
        return ("Spotify wouldn't renew your login. Run `,spotify unlink`, then `,play` to relink.")
    except librespot_process.LibrespotProcessError as exc:
        logger.error("could not start librespot for member %s: %s", member_id, exc)
        return "Couldn't start your Spotify session: %s" % exc
    logger.info("librespot ready for member %s in %.2fs", member_id, time.monotonic() - started)

    try:
        voice_client = await playback.join_or_move(client, voice_channel)
    except Exception:
        logger.exception("failed to join voice for member %s", member_id)
        await _stop_session(member_id)
        return "Couldn't join your voice channel. Try `,play` again."

    playback.ensure_opus_loaded()
    if voice_client.is_playing():
        voice_client.stop()
    voice_client.play(LibrespotPCMSource(process.buffer, member_id=member_id))

    _restart_idle_watchdog(client, member_id, voice_channel.guild.id, process)
    return None


def _restart_idle_watchdog(client, member_id, guild_id, process):
    member_id = str(member_id)
    existing = _idle_tasks.pop(member_id, None)
    if existing is not None:
        existing.cancel()
    _idle_tasks[member_id] = asyncio.ensure_future(
        _idle_watchdog(client, member_id, guild_id, process))


async def _idle_watchdog(client, member_id, guild_id, process):
    """Disconnect and reap once nobody is listening.

    Three ways a session ends: the audio stops for IDLE_TIMEOUT_SECONDS, the
    voice channel empties, or the voice client goes away. Without this, a
    registered device would hold a process (and the user's credentials) open
    indefinitely.
    """
    last_bytes = process.buffer.total_written
    last_audio_at = time.monotonic()
    try:
        while True:
            await asyncio.sleep(IDLE_CHECK_INTERVAL_SECONDS)

            guild = client.get_guild(guild_id)
            voice_client = discord.utils.get(client.voice_clients, guild=guild) if guild else None
            if voice_client is None or not voice_client.is_connected():
                logger.info("voice client gone for member %s; reaping librespot", member_id)
                await _stop_session(member_id)
                return

            humans = [m for m in voice_client.channel.members if not m.bot]
            if not humans:
                logger.info("voice channel empty for member %s; reaping librespot", member_id)
                await _stop_session(member_id, guild=guild, client=client)
                return

            written = process.buffer.total_written
            if written != last_bytes:
                last_bytes = written
                last_audio_at = time.monotonic()
            elif time.monotonic() - last_audio_at >= IDLE_TIMEOUT_SECONDS:
                logger.info("no audio for %ss from member %s; reaping librespot",
                            IDLE_TIMEOUT_SECONDS, member_id)
                await _stop_session(member_id, guild=guild, client=client)
                return
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("idle watchdog crashed for member %s", member_id)


async def handle_play(message: discord.Message, client: discord.Client):
    voice_state = message.author.voice
    if voice_state is None or voice_state.channel is None:
        await message.channel.send("Join a voice channel first, then try `,play` again.")
        return
    voice_channel = voice_state.channel

    link = await spotifyStore.getLink(message.author.id)
    loop = asyncio.get_event_loop()

    if link is None or credentials.needs_relink(link["credentials"]):
        auth_url = await _executor_call(
            loop, oauth_flow.start_link, message.author.id,
            message.guild.id, voice_channel.id)
        await _send_link(message, auth_url)
        return

    error = await _start_session(client, message, voice_channel)
    if error:
        await message.channel.send(error)
        return

    await message.channel.send(
        "Ready! Open Spotify, tap the devices button and pick **%s** to start "
        "listening in %s." % (DEVICE_NAME, voice_channel.name)
    )


async def handle_spotify(message: discord.Message, client: discord.Client):
    parts = message.content.split()
    if len(parts) >= 2 and parts[1] == "unlink":
        guild = message.guild
        await _stop_session(message.author.id, guild=guild, client=client)
        oauth_flow.cancel(message.author.id)
        deleted = await spotifyStore.deleteLink(message.author.id)
        if deleted:
            await message.channel.send("Unlinked your Spotify account.")
        else:
            await message.channel.send("You don't have a linked Spotify account.")
        return
    await message.channel.send("Usage: `,spotify unlink`")


async def handle_spotify_pasteback(message: discord.Message, client: discord.Client):
    """DM handler: the user pastes the redirect URL they were sent to."""
    loop = asyncio.get_event_loop()
    member_id = message.author.id

    try:
        credentials_json, pending = await _executor_call(
            loop, oauth_flow.complete_link, member_id, message.content)
    except KeyError as exc:
        await message.channel.send(
            "I don't have a link in progress for you (%s). Run `,play` in a "
            "server to start one." % exc)
        return
    except spotify_auth.SpotifyAuthError:
        logger.exception("code exchange failed for member %s", member_id)
        await message.channel.send(
            "Spotify wouldn't accept that code. Make sure you pasted the whole "
            "URL from the address bar, or run `,play` again for a fresh link."
        )
        return

    await spotifyStore.setLink(
        member_id,
        credentials=json.dumps(credentials_json),
        scope=credentials_json.get("scope", ""),
    )

    guild = client.get_guild(pending["guild_id"]) if pending.get("guild_id") else None
    voice_channel = (guild.get_channel(pending["voice_channel_id"])
                     if guild and pending.get("voice_channel_id") else None)
    member = guild.get_member(member_id) if guild else None

    # Only auto-join if they're still where they started -- checked live, not
    # trusted from the pending record.
    still_there = (
        member is not None and member.voice is not None
        and member.voice.channel is not None and voice_channel is not None
        and member.voice.channel.id == voice_channel.id
    )
    if not still_there:
        await message.channel.send(
            "Spotify linked. Hop into a voice channel and run `,play` to get started."
        )
        return

    error = await _start_session(client, message, voice_channel)
    if error:
        await message.channel.send("Spotify linked, but " + error[0].lower() + error[1:])
        return

    await message.channel.send(
        "Spotify linked, and I've joined **%s**. Open Spotify and pick **%s** "
        "as your device to start playing." % (voice_channel.name, DEVICE_NAME)
    )


def has_pending_spotify_link(user_id):
    return oauth_flow.has_pending(user_id)


def looks_like_paste_back(content):
    return oauth_flow.looks_like_paste_back(content)
