"""Hosted OAuth callback for the Spotify link flow.

Spotify redirects the user's browser here after they authorize. We exchange
the code, persist the credentials, and finish the link -- the user never
copies a code anywhere.

Binds to 127.0.0.1 only. TLS is terminated by nginx in front of this (Spotify
requires https for any non-loopback redirect URI), so this process never
handles certificates or public traffic directly.
"""
import asyncio
import html
import json
import logging

from aiohttp import web

from helpers import spotifyStore
from music import oauth_flow, session_manager

logger = logging.getLogger("music.callback_server")

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8888
CALLBACK_PATH = "/spotify/callback"


def _page(title, body, status=200):
    return web.Response(status=status, content_type="text/html", text=f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#121212;color:#fff;display:flex;align-items:center;
       justify-content:center;height:100vh;margin:0;text-align:center}}
  .card{{max-width:26rem;padding:2rem}}
  h1{{color:#1DB954;font-size:1.5rem;margin:0 0 .75rem}}
  p{{color:#b3b3b3;line-height:1.5;margin:0}}
</style></head>
<body><div class="card"><h1>{html.escape(title)}</h1><p>{body}</p></div></body></html>""")


async def _finish_link(client, entry, credentials_json):
    """Persist credentials and tell the user, in Discord, that they're linked.

    Runs on the bot's event loop. Deliberately best-effort about the Discord
    half: the credentials are already saved by then, so a DM failure must not
    make the link look like it failed.
    """
    loop = asyncio.get_event_loop()
    user_id = entry["user_id"]

    session = await loop.run_in_executor(
        None, session_manager.build_session, credentials_json)
    spotify_username = session.username() or ""

    await spotifyStore.setLink(
        user_id,
        credentials=json.dumps(credentials_json),
        spotify_username=spotify_username,
    )
    session_manager.cache_session(user_id, session)

    # Import here rather than at module scope: music.commands imports heavy
    # Discord/protobuf machinery and importing it at load time would create a
    # cycle (commands -> oauth_flow -> callback_server -> commands).
    from music import commands as music_commands

    guild = client.get_guild(entry["guild_id"]) if entry.get("guild_id") else None
    voice_channel = (guild.get_channel(entry["voice_channel_id"])
                     if guild and entry.get("voice_channel_id") else None)
    member = guild.get_member(user_id) if guild else None

    # Only auto-join if they're still sitting in the channel they started from
    # -- checked live, not trusted from the pending record.
    still_there = (
        member is not None and member.voice is not None
        and member.voice.channel is not None and voice_channel is not None
        and member.voice.channel.id == voice_channel.id
    )

    if still_there:
        await music_commands.join_and_register_device(
            client, loop, user_id, guild, voice_channel, session)

    try:
        user = client.get_user(user_id) or await client.fetch_user(user_id)
        if still_there:
            await user.send(
                f"Spotify linked as **{spotify_username}**. I've joined "
                f"**{voice_channel.name}** -- open Spotify and pick "
                f"**{session_manager.DEFAULT_DEVICE_NAME}** as your device to start playing."
            )
        else:
            await user.send(
                f"Spotify linked as **{spotify_username}**. Hop into a voice "
                f"channel and run `,play` to get started."
            )
    except Exception:
        # DMs closed, or the user blocked the bot. The link itself is fine.
        logger.warning("linked member %s but could not DM them", user_id, exc_info=True)

    return spotify_username


def build_app(client):
    """Build the aiohttp app. `client` is the running discord.Client."""

    async def handle_callback(request):
        state = request.query.get("state", "")
        code = request.query.get("code", "")
        error = request.query.get("error", "")

        if error:
            # User clicked "Cancel", or Spotify rejected the request.
            logger.info("Spotify callback returned error=%s", error)
            return _page("Link cancelled",
                         "Spotify didn't authorize the link. You can run "
                         "<code>,play</code> in Discord to try again.", status=400)

        if not state or not code:
            return _page("Invalid request",
                         "This link is missing information. Run <code>,play</code> "
                         "in Discord to get a fresh one.", status=400)

        entry = oauth_flow.peek_state(state)
        if entry is None:
            return _page("Link expired",
                         "That link has already been used or has expired. Run "
                         "<code>,play</code> in Discord to get a fresh one.", status=400)

        loop = asyncio.get_event_loop()
        try:
            # complete_link_by_state consumes the state, so a replayed
            # callback URL cannot redeem a second set of credentials.
            credentials_json, entry = await loop.run_in_executor(
                None, oauth_flow.complete_link_by_state, state, code)
        except KeyError:
            return _page("Link expired",
                         "That link has already been used or has expired. Run "
                         "<code>,play</code> in Discord to get a fresh one.", status=400)
        except Exception:
            # Never log `code` or the credentials themselves.
            logger.exception("token exchange failed for a Spotify callback")
            return _page("Couldn't link",
                         "Spotify wouldn't complete the link. Run <code>,play</code> "
                         "in Discord to try again.", status=502)

        try:
            username = await _finish_link(client, entry, credentials_json)
        except Exception:
            logger.exception("failed to finish Spotify link for member %s", entry["user_id"])
            return _page("Almost there",
                         "Your Spotify account authorized, but I couldn't start a "
                         "session. Make sure it's a <b>Premium</b> account, then run "
                         "<code>,play</code> in Discord again.", status=500)

        return _page("Spotify linked",
                     f"Linked as <b>{html.escape(username)}</b>. "
                     "You can close this tab and head back to Discord.")

    async def handle_health(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get(CALLBACK_PATH, handle_callback)
    # Spotify matches redirect_uri byte-for-byte against what's registered, so
    # serve the bare root too -- a URI registered as "https://<host>" (no path)
    # redirects to "/", which would otherwise 404.
    app.router.add_get("/", handle_callback)
    app.router.add_get("/healthz", handle_health)
    return app


async def start(client):
    """Start the callback server on the bot's event loop. Returns the runner."""
    runner = web.AppRunner(build_app(client), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, LISTEN_HOST, LISTEN_PORT)
    await site.start()
    logger.info("Spotify callback server listening on %s:%s%s (redirect=%s)",
                LISTEN_HOST, LISTEN_PORT, CALLBACK_PATH, oauth_flow.REDIRECT_URL)
    return runner
