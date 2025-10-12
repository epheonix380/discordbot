from api_client import api_client
from asgiref.sync import sync_to_async
import asyncio

@sync_to_async
def getNSFWChannel(uid):
    async def _get_nsfw_channel():
        async with api_client as client:
            result = await client.get_guild_by_id(str(uid))
            if 'error' not in result and result.get('nsfw_channel'):
                return f"<#{result['nsfw_channel']}>"
            return None
    
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(_get_nsfw_channel())
    except RuntimeError:
        # No event loop running, create a new one
        return asyncio.run(_get_nsfw_channel())

@sync_to_async
def setNSFWChannel(uid, channelID):
    async def _set_nsfw_channel():
        async with api_client as client:
            data = {'nsfw_channel': str(channelID)[2:-1:1]}
            result = await client.create_or_update_guild(str(uid), data)
            return 'error' not in result
    
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(_set_nsfw_channel())
    except RuntimeError:
        # No event loop running, create a new one
        return asyncio.run(_set_nsfw_channel())

@sync_to_async
def getGuessTheHeroChannel(uid):
    async def _get_gth_channel():
        async with api_client as client:
            result = await client.get_guild_by_id(str(uid))
            if 'error' not in result and result.get('guess_the_hero'):
                return f"<#{result['guess_the_hero']}>"
            return None
    
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(_get_gth_channel())
    except RuntimeError:
        # No event loop running, create a new one
        return asyncio.run(_get_gth_channel())

@sync_to_async
def setGuessTheHeroChannel(uid, channelID):
    async def _set_gth_channel():
        async with api_client as client:
            data = {'guess_the_hero': str(channelID)[2:-1:1]}
            result = await client.create_or_update_guild(str(uid), data)
            return 'error' not in result
    
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(_set_gth_channel())
    except RuntimeError:
        # No event loop running, create a new one
        return asyncio.run(_set_gth_channel())
