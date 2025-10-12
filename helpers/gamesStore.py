import asyncio
from api_client import api_client

async def getOrCreate(appid, channelid, guildid):
    async with api_client as client:
        # Get or create game version
        game_result = await client._make_request('GET', '/api/game-versions/', params={'appid': appid})
        if 'error' not in game_result and game_result.get('results'):
            game_data = game_result['results'][0]
            wasCreated = False
        else:
            # Create new game version
            game_result = await client._make_request('POST', '/api/game-versions/', data={'appid': appid})
            game_data = game_result
            wasCreated = True
        
        # Ensure guild exists
        await client.create_or_update_guild(str(guildid), {})
        
        # Ensure channel exists
        await client.create_or_update_channel(str(channelid), {
            'guild': guildid
        })
        
        # Create or get subscription
        subscription_result = await client._make_request('POST', '/api/game-subscriptions/', data={
            'game': game_data['id'],
            'channel': channelid
        })
        
        return game_data, wasCreated

async def updateCurrentVersion(appid, version, patchVersion=None, name=None):
    async with api_client as client:
        # Get game version
        game_result = await client._make_request('GET', '/api/game-versions/', params={'appid': appid})
        if 'error' not in game_result and game_result.get('results'):
            game_id = game_result['results'][0]['id']
            
            # Update game version
            update_data = {'version': version}
            if name is not None:
                update_data['name'] = name
            if patchVersion is not None:
                update_data['patchVersion'] = patchVersion
                
            await client._make_request('PATCH', f'/api/game-versions/{game_id}/', data=update_data)

async def getAllGames():
    async with api_client as client:
        result = await client._make_request('GET', '/api/game-versions/')
        if 'error' not in result:
            return result.get('results', [])
        return []

async def getAllGamesForChannel(channelid):
    async with api_client as client:
        result = await client._make_request('GET', '/api/game-subscriptions/', params={
            'channel__channel_id': channelid
        })
        if 'error' not in result:
            return result.get('results', [])
        return []

async def getAllChannelsForGame(appid):
    async with api_client as client:
        result = await client._make_request('GET', '/api/game-subscriptions/', params={
            'game__appid': appid
        })
        if 'error' not in result:
            return result.get('results', [])
        return []

