import asyncio
import json
import logging

import discord

from helpers import spotifyStore
from music import oauth_flow, playback, search, session_manager

logger = logging.getLogger("music.commands")

PREMIUM_NOTICE = "**Spotify Premium is required** to stream through the bot."
UNSUPPORTED_QUERY_NOTICE = (
    "I can only play direct Spotify track links right now, e.g. `spotify:track:...` "
    "or an `open.spotify.com/track/...` URL -- searching by name is coming soon."
)


async def _join_and_play(client: discord.Client, guild: discord.Guild, voice_channel, session, track_uri):
    voice_client = discord.utils.get(client.voice_clients, guild=guild)
    if voice_client is None or not voice_client.is_connected():
        voice_client = await playback.join(voice_channel)
    elif voice_client.channel.id != voice_channel.id:
        await voice_client.move_to(voice_channel)
    await playback.play_track(voice_client, session, track_uri)


async def handle_play(message: discord.Message, client: discord.Client):
    query = message.content[len(",play"):].strip()
    if not query:
        await message.channel.send("Usage: `,play <spotify:track:... URI or open.spotify.com/track/... link>`")
        return

    voice_state = message.author.voice
    if voice_state is None or voice_state.channel is None:
        await message.channel.send("Join a voice channel first, then try `,play` again.")
        return
    voice_channel = voice_state.channel

    link = await spotifyStore.getLink(message.author.id)
    loop = asyncio.get_event_loop()

    if link is None:
        auth_url = await loop.run_in_executor(
            None, oauth_flow.start_link, message.author.id, query, message.guild.id, voice_channel.id)
        await message.channel.send(
            "You haven't linked Spotify yet. " + PREMIUM_NOTICE + "\n"
            "1. Open this link and log in/authorize: " + auth_url + "\n"
            "2. The page will likely fail to load after you authorize -- that's expected. "
            "Copy the `code=...` value (or the whole URL) from your browser's address bar.\n"
            "3. DM it to me here and I'll link your account and start playing."
        )
        return

    track_uri = search.resolve_track_uri(query)
    if track_uri is None:
        await message.channel.send(UNSUPPORTED_QUERY_NOTICE)
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
        await _join_and_play(client, message.guild, voice_channel, session, track_uri)
    except Exception:
        logger.exception("failed to play %s for member %s", track_uri, message.author.id)
        await message.channel.send("Couldn't play that track (it may be unavailable or region-locked).")
        return

    await message.channel.send(f"Now playing {track_uri} in {voice_channel.name}.")


async def handle_spotify(message: discord.Message, client: discord.Client):
    parts = message.content.split()
    if len(parts) >= 2 and parts[1] == "unlink":
        deleted = await spotifyStore.deleteLink(message.author.id)
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
            "I don't have a pending Spotify link for you -- start with `,play <track>` in a server first."
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

    query = pending.get("pending_query")
    guild_id = pending.get("guild_id")
    voice_channel_id = pending.get("voice_channel_id")
    track_uri = search.resolve_track_uri(query) if query else None

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

    if track_uri is None or not still_in_channel:
        await message.channel.send(
            f"Linked to Spotify as **{spotify_username or 'your account'}**! "
            f"Go back to the server and use `,play {query or '<track>'}` again to hear it."
        )
        return

    try:
        await _join_and_play(client, guild, voice_channel, session, track_uri)
    except Exception:
        logger.exception("failed to auto-play %s for member %s after linking", track_uri, message.author.id)
        await message.channel.send(
            f"Linked as **{spotify_username or 'your account'}**, but couldn't start playback automatically. "
            f"Use `,play {query}` again in the server."
        )
        return

    await message.channel.send(
        f"Linked to Spotify as **{spotify_username or 'your account'}** and now playing in {voice_channel.name}!"
    )
