"""Manual verification script for SPOTIFY_CONNECT_PLAN.md Phase 3.

Not wired into the bot or main.py -- run by hand with a real Discord bot
token, a voice channel the bot can join, and real Spotify credentials (see
music/phase2_smoke_test.py for the credentials.json shape) to prove
join -> play -> clean disconnect actually works end to end.

Usage:
    DISCORD_TOKEN=... python -m music.phase3_smoke_test <voice_channel_id> <credentials.json> <spotify:track:...>

Success looks like: the bot joins the given voice channel, the track is
audible, and the bot cleanly disconnects afterwards with no leftover
ffmpeg/librespot processes or exceptions in the log.
"""
import asyncio
import json
import os
import sys

import discord

from music import playback, session_manager


async def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    voice_channel_id = int(sys.argv[1])
    credentials_path = sys.argv[2]
    track_uri = sys.argv[3]

    token = os.environ["DISCORD_TOKEN"]
    with open(credentials_path) as f:
        credentials_json = json.load(f)

    intents = discord.Intents.default()
    intents.voice_states = True
    client = discord.Client(intents=intents)
    done = asyncio.Event()

    @client.event
    async def on_ready():
        print("Logged in as", client.user)
        channel = client.get_channel(voice_channel_id) or await client.fetch_channel(voice_channel_id)

        print("Building librespot session...")
        loop = asyncio.get_event_loop()
        session = await loop.run_in_executor(None, session_manager.build_session, credentials_json)

        print("Joining", channel)
        voice_client = await playback.join(channel)

        def after(error):
            if error:
                print("playback error:", error)
            else:
                print("playback finished")
            client.loop.call_soon_threadsafe(done.set)

        print("Playing", track_uri)
        await playback.play_track(voice_client, session, track_uri, after=after)

        await done.wait()
        print("Leaving voice...")
        await playback.leave(voice_client)
        session.close()
        await client.close()

    await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
