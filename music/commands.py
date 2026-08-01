import asyncio
import json
import logging
import time

import discord
from librespot.proto import Connect_pb2 as Connect

from helpers import spotifyStore
from music import oauth_flow, playback, session_manager
from music.connect_device import ConnectDevice

logger = logging.getLogger("music.commands")

PREMIUM_NOTICE = "**Spotify Premium is required** to stream through the bot."

STATE_REPORT_INTERVAL_SECONDS = 5

_connect_devices = {}  # str(member_id) -> ConnectDevice
_connect_handlers = {}  # str(member_id) -> ConnectCommandHandler


async def _join_and_play(client: discord.Client, guild: discord.Guild, voice_channel, session, track_uri):
    voice_client = discord.utils.get(client.voice_clients, guild=guild)
    if voice_client is None or not voice_client.is_connected():
        voice_client = await playback.join(voice_channel)
    elif voice_client.channel.id != voice_channel.id:
        await voice_client.move_to(voice_channel)
    await playback.play_track(voice_client, session, track_uri)
    return voice_client


def _find_member_voice_channel(client: discord.Client, member_id):
    """Look across every guild the bot shares with this member for their
    current voice channel. Needed because a Connect "transfer" command
    arrives with no Discord context at all -- just a Spotify track URI."""
    member_id = int(member_id)
    for guild in client.guilds:
        member = guild.get_member(member_id)
        if member is not None and member.voice is not None and member.voice.channel is not None:
            return guild, member.voice.channel
    return None, None


class ConnectCommandHandler:
    """Bridges music.connect_device.ConnectDevice's dealer-thread callbacks
    (on_transfer/on_resume/on_pause) into this bot's asyncio/Discord world.

    Those callbacks run on librespot's own worker thread, not the event
    loop, so every Discord action here is scheduled via
    asyncio.run_coroutine_threadsafe and waited on synchronously (which is
    fine -- we're not on the loop thread) so ConnectDevice.on_request can
    still return a real SUCCESS/UPSTREAM_ERROR to Spotify. NOT verified
    against a live dealer session -- see SPOTIFY_CONTEXT.md.
    """

    def __init__(self, client: discord.Client, loop, member_id, session):
        self.client = client
        self.loop = loop
        self.member_id = member_id
        self.session = session
        self.connect_device = None  # set by the caller right after construction
        self.guild_id = None
        self.current_track_uri = None
        self.is_paused = False
        self._position_at_start_ms = 0
        self._started_at_monotonic = None
        self._report_task = None

    def _run_coroutine(self, coro, timeout=20):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    def _current_position_ms(self):
        if self._started_at_monotonic is None:
            return self._position_at_start_ms
        elapsed_ms = int((time.monotonic() - self._started_at_monotonic) * 1000)
        return self._position_at_start_ms + elapsed_ms

    def _mark_playing(self, track_uri, position_ms, is_paused):
        self.current_track_uri = track_uri
        self._position_at_start_ms = position_ms
        self._started_at_monotonic = None if is_paused else time.monotonic()
        self.is_paused = is_paused

    def on_transfer(self, track_uri, position_ms, is_paused):
        self._run_coroutine(self._do_transfer(track_uri, position_ms, is_paused))

    def on_resume(self):
        self._run_coroutine(self._do_resume())

    def on_pause(self):
        self._run_coroutine(self._do_pause())

    async def _do_transfer(self, track_uri, position_ms, is_paused):
        guild, voice_channel = _find_member_voice_channel(self.client, self.member_id)
        if guild is None:
            raise RuntimeError(f"member {self.member_id} isn't visibly in a voice channel the bot shares")
        self.guild_id = guild.id
        voice_client = await _join_and_play(self.client, guild, voice_channel, self.session, track_uri)
        if is_paused:
            voice_client.pause()
        self._mark_playing(track_uri, position_ms, is_paused)
        await self._report_state_async(Connect.PutStateReason.PLAYER_STATE_CHANGED)
        self._ensure_report_task()

    async def _do_resume(self):
        voice_client = self._active_voice_client()
        if voice_client is None:
            raise RuntimeError("not connected to voice for this member's last known guild")
        voice_client.resume()
        self.is_paused = False
        self._started_at_monotonic = time.monotonic()
        await self._report_state_async(Connect.PutStateReason.PLAYER_STATE_CHANGED)

    async def _do_pause(self):
        voice_client = self._active_voice_client()
        if voice_client is None:
            raise RuntimeError("not connected to voice for this member's last known guild")
        voice_client.pause()
        self._position_at_start_ms = self._current_position_ms()
        self.is_paused = True
        self._started_at_monotonic = None
        await self._report_state_async(Connect.PutStateReason.PLAYER_STATE_CHANGED)

    def _active_voice_client(self):
        guild = self.client.get_guild(self.guild_id) if self.guild_id else None
        if guild is None:
            return None
        return discord.utils.get(self.client.voice_clients, guild=guild)

    async def _report_state_async(self, reason):
        if self.connect_device is None or self.current_track_uri is None:
            return
        await self.loop.run_in_executor(
            None,
            self.connect_device.put_state,
            reason,
            not self.is_paused,
            self.is_paused,
            self.current_track_uri,
            self._current_position_ms(),
        )

    def _ensure_report_task(self):
        if self._report_task is None or self._report_task.done():
            self._report_task = self.loop.create_task(self._report_loop())

    async def _report_loop(self):
        try:
            while True:
                await asyncio.sleep(STATE_REPORT_INTERVAL_SECONDS)
                if self.current_track_uri is None:
                    continue
                try:
                    await self._report_state_async(Connect.PutStateReason.PLAYER_STATE_CHANGED)
                except Exception:
                    logger.exception("periodic Connect state report failed for member %s", self.member_id)
        except asyncio.CancelledError:
            pass

    def close(self):
        # Task.cancel() isn't documented as thread-safe; close() may be
        # called from librespot's worker thread indirectly (e.g. a future
        # command handler tearing itself down), so always hop onto the loop.
        if self._report_task is not None:
            task = self._report_task
            self.loop.call_soon_threadsafe(task.cancel)
            self._report_task = None


def _ensure_connect_device(client: discord.Client, loop, member_id, session):
    """Get-or-create the Connect receiver for this member's session. Idempotent
    per member -- reuses the existing device/handler if one is already active."""
    member_id = str(member_id)
    device = _connect_devices.get(member_id)
    if device is not None:
        return device
    handler = ConnectCommandHandler(client, loop, member_id, session)
    device = ConnectDevice(session, handler, device_name=session_manager.DEFAULT_DEVICE_NAME)
    handler.connect_device = device
    _connect_devices[member_id] = device
    _connect_handlers[member_id] = handler
    return device


def _close_connect_device(member_id):
    member_id = str(member_id)
    handler = _connect_handlers.pop(member_id, None)
    if handler is not None:
        handler.close()
    device = _connect_devices.pop(member_id, None)
    if device is not None:
        try:
            device.close()
        except Exception:
            logger.exception("error closing Connect device for member %s", member_id)


async def _join_and_register_device(client: discord.Client, loop, member_id, guild: discord.Guild, voice_channel, session):
    """Join the caller's voice channel and (re)register their Connect device
    there. Nothing plays yet -- playback only starts once the Spotify app
    sends a transfer command for this device."""
    voice_client = discord.utils.get(client.voice_clients, guild=guild)
    if voice_client is None or not voice_client.is_connected():
        voice_client = await playback.join(voice_channel)
    elif voice_client.channel.id != voice_channel.id:
        await voice_client.move_to(voice_channel)
    _ensure_connect_device(client, loop, member_id, session)
    _connect_handlers[str(member_id)].guild_id = guild.id
    return voice_client


async def handle_play(message: discord.Message, client: discord.Client):
    voice_state = message.author.voice
    if voice_state is None or voice_state.channel is None:
        await message.channel.send("Join a voice channel first, then try `,play` again.")
        return
    voice_channel = voice_state.channel

    link = await spotifyStore.getLink(message.author.id)
    loop = asyncio.get_event_loop()

    if link is None:
        auth_url = await loop.run_in_executor(
            None, oauth_flow.start_link, message.author.id, message.guild.id, voice_channel.id)
        await message.channel.send(
            "You haven't linked Spotify yet. " + PREMIUM_NOTICE + "\n"
            "1. Open this link and log in/authorize: " + auth_url + "\n"
            "2. The page will likely fail to load after you authorize -- that's expected. "
            "Copy the `code=...` value (or the whole URL) from your browser's address bar.\n"
            "3. DM it to me here and I'll link your account and join your voice channel."
        )
        return

    try:
        credentials_json = json.loads(link["credentials"])
        session = await loop.run_in_executor(
            None, session_manager.get_session, message.author.id, credentials_json)
    except Exception:
        logger.exception("failed to build librespot session for member %s", message.author.id)
        await message.channel.send(
            "Couldn't connect to your Spotify account. Try `,spotify unlink` then `,play` again to relink."
        )
        return

    try:
        await _join_and_register_device(client, loop, message.author.id, message.guild, voice_channel, session)
    except Exception:
        logger.exception("failed to join/register Connect device for member %s", message.author.id)
        await message.channel.send("Couldn't join your voice channel and register as a Spotify Connect device. Try `,play` again.")
        return

    await message.channel.send(
        f"Ready! Open Spotify and select **{session_manager.DEFAULT_DEVICE_NAME}** as your playback device "
        f"to start listening in {voice_channel.name}."
    )


async def handle_spotify(message: discord.Message, client: discord.Client):
    parts = message.content.split()
    if len(parts) >= 2 and parts[1] == "unlink":
        deleted = await spotifyStore.deleteLink(message.author.id)
        _close_connect_device(message.author.id)
        session_manager.close_session(message.author.id)
        if deleted:
            await message.channel.send("Unlinked your Spotify account.")
        else:
            await message.channel.send("You don't have a linked Spotify account.")
        return
    await message.channel.send("Usage: `,spotify unlink`")


async def handle_spotify_pasteback(message: discord.Message, client: discord.Client):
    loop = asyncio.get_event_loop()
    try:
        credentials_json, pending = await loop.run_in_executor(
            None, oauth_flow.complete_link, message.author.id, message.content)
    except KeyError:
        await message.channel.send(
            "I don't have a pending Spotify link for you -- start with `,play` in a server first."
        )
        return
    except Exception:
        logger.exception("failed to complete Spotify link for member %s", message.author.id)
        await message.channel.send(
            "That didn't work -- the code may be invalid or expired. Try `,play` again in the server to get a fresh link."
        )
        return

    try:
        session = await loop.run_in_executor(None, session_manager.build_session, credentials_json)
    except Exception:
        logger.exception("failed to build librespot session right after linking for member %s", message.author.id)
        await message.channel.send("Linked, but couldn't start a Spotify session yet. Try `,play` again in a moment.")
        return

    spotify_username = session.username() or ""
    await spotifyStore.setLink(
        message.author.id,
        credentials=json.dumps(credentials_json),
        spotify_username=spotify_username,
    )
    session_manager.cache_session(message.author.id, session)

    guild_id = pending.get("guild_id")
    voice_channel_id = pending.get("voice_channel_id")

    guild = client.get_guild(guild_id) if guild_id else None
    voice_channel = guild.get_channel(voice_channel_id) if guild and voice_channel_id else None
    member = guild.get_member(message.author.id) if guild else None
    still_in_channel = (
        member is not None
        and member.voice is not None
        and member.voice.channel is not None
        and voice_channel is not None
        and member.voice.channel.id == voice_channel.id
    )

    if not still_in_channel:
        await message.channel.send(
            f"Linked to Spotify as **{spotify_username or 'your account'}**! "
            "Go back to a voice channel and use `,play` to get set up."
        )
        return

    try:
        await _join_and_register_device(client, loop, message.author.id, guild, voice_channel, session)
    except Exception:
        logger.exception("failed to join/register Connect device for member %s after linking", message.author.id)
        await message.channel.send(
            f"Linked as **{spotify_username or 'your account'}**, but couldn't finish setting up. "
            "Use `,play` again in the server."
        )
        return

    await message.channel.send(
        f"Linked to Spotify as **{spotify_username or 'your account'}**! "
        f"Open Spotify and select **{session_manager.DEFAULT_DEVICE_NAME}** as your playback device "
        f"to start listening in {voice_channel.name}."
    )
