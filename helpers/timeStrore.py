from api_client import api_client
import asyncio

async def getFormat(uid):
    async with api_client as client:
        member = await client.get_member_by_id(str(uid))
        if 'error' not in member:
            return member.get('time_format', '%H:%M on %d-%m-%Y')
        return "%H:%M on %d-%m-%Y"

async def setFormat(uid, time_format):
    async with api_client as client:
        await client.create_or_update_member(str(uid), {
            'time_format': time_format
        })
        return True

async def getDefaultTimezone(uid):
    async with api_client as client:
        member = await client.get_member_by_id(str(uid))
        if 'error' not in member:
            timezone_data = member.get('time_zone')
            if timezone_data:
                return timezone_data.get('time_zone')
        return None

async def setDefaultTimezone(uid, timezone):
    async with api_client as client:
        # Create or get timezone
        timezone_result = await client._make_request('POST', '/api/timezones/', data={
            'time_zone': str(timezone)
        })
        
        # Update member with timezone
        await client.create_or_update_member(str(uid), {
            'time_zone': timezone_result.get('id') if 'error' not in timezone_result else None
        })
        return True

async def addTimezone(uid, timezone):
    async with api_client as client:
        # Ensure member exists
        await client.create_or_update_member(str(uid), {})
        
        # Create or get timezone
        timezone_result = await client._make_request('POST', '/api/timezones/', data={
            'time_zone': str(timezone)
        })
        
        # Create timezone mapping
        mapping_result = await client._make_request('POST', '/api/member-timezone-maps/', data={
            'member': uid,
            'time_zone': timezone_result.get('id') if 'error' not in timezone_result else None
        })
        return 'error' not in mapping_result

async def removeTimezone(uid, timezone):
    async with api_client as client:
        # Get timezone
        timezone_result = await client._make_request('GET', '/api/timezones/', params={
            'time_zone': str(timezone)
        })
        
        if 'error' not in timezone_result and timezone_result.get('results'):
            timezone_id = timezone_result['results'][0]['id']
            
            # Delete mapping
            mapping_result = await client._make_request('DELETE', f'/api/member-timezone-maps/', params={
                'member__member_id': uid,
                'time_zone': timezone_id
            })
            return 'error' not in mapping_result
        return False

async def getTimezones(uid):
    async with api_client as client:
        result = await client._make_request('GET', '/api/member-timezone-maps/', params={
            'member__member_id': uid
        })
        if 'error' not in result:
            return result.get('results', [])
        return []
    
