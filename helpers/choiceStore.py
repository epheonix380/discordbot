import asyncio
from api_client import api_client

async def getRecentChoice(uid, name=None):
    async with api_client as client:
        params = {'member__member_id': uid}
        if name is not None:
            params['name'] = name
            
        result = await client._make_request('GET', '/api/list-of-choices/', params=params)
        if 'error' not in result and result.get('results'):
            # Get the most recent choice
            choices = result['results']
            if choices:
                latest_choice = choices[0]  # Assuming ordered by last_used desc
                # Get items for this choice
                items_result = await client._make_request('GET', '/api/items/', params={
                    'list': latest_choice['id']
                })
                if 'error' not in items_result:
                    return items_result.get('results', [])
        return None

async def setRecentChoice(uid, list, name=None):
    async with api_client as client:
        # Ensure member exists
        await client.create_or_update_member(str(uid), {})
        
        # Create list of choices
        choice_result = await client._make_request('POST', '/api/list-of-choices/', data={
            'member': uid,
            'name': name
        })
        
        if 'error' not in choice_result:
            choice_id = choice_result['id']
            # Create items for each choice
            for choice in list:
                await client._make_request('POST', '/api/items/', data={
                    'list': choice_id,
                    'name': str(choice)
                })
        return True
