import aiohttp
import asyncio
import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class APIClient:
    """
    Async HTTP client for communicating with Django REST API
    Uses Python 3.13 asyncio features
    """
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.getenv('DJANGO_API_URL', 'http://localhost:8000')
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make an HTTP request to the API using Python 3.13 asyncio features
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with self.session.request(method, url, json=data, params=params) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"API request failed: {response.status} - {error_text}")
                    return {'error': f'HTTP {response.status}: {error_text}'}
                
                if response.content_type == 'application/json':
                    return await response.json()
                else:
                    return {'data': await response.text()}
                    
        except Exception as e:
            logger.error(f"API request exception: {str(e)}")
            return {'error': str(e)}
    
    # Guild operations
    async def get_guild_by_id(self, guild_id: str) -> Dict[str, Any]:
        return await self._make_request('GET', f'/api/guilds/by_guild_id/', params={'guild_id': guild_id})
    
    async def create_or_update_guild(self, guild_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        existing = await self.get_guild_by_id(guild_id)
        if 'error' not in existing:
            return await self._make_request('PUT', f'/api/guilds/{existing["id"]}/', data=data)
        else:
            data['guild_id'] = guild_id
            return await self._make_request('POST', '/api/guilds/', data=data)
    
    # Member operations
    async def get_member_by_id(self, member_id: str) -> Dict[str, Any]:
        return await self._make_request('GET', f'/api/members/by_member_id/', params={'member_id': member_id})
    
    async def create_or_update_member(self, member_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        existing = await self.get_member_by_id(member_id)
        if 'error' not in existing:
            return await self._make_request('PUT', f'/api/members/{existing["id"]}/', data=data)
        else:
            data['member_id'] = member_id
            return await self._make_request('POST', '/api/members/', data=data)
    
    # Guild Activity operations
    async def add_guild_activity(self, guild_id: str, activity_data: Dict[str, Any]) -> Dict[str, Any]:
        # First ensure guild exists
        await self.create_or_update_guild(guild_id, {})
        
        # Get or create member
        member_id = activity_data.get('member_id')
        if member_id:
            await self.create_or_update_member(member_id, {})
        
        return await self._make_request('POST', '/api/guild-activities/', data=activity_data)
    
    async def get_guild_activities(self, guild_id: str) -> Dict[str, Any]:
        return await self._make_request('GET', f'/api/guild-activities/by_guild/', params={'guild_id': guild_id})
    
    # Weighted Guild Activity operations
    async def create_weighted_activity(self, activity_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('POST', '/api/weighted-guild-activities/', data=activity_data)
    
    async def get_weighted_activities(self, guild_id: str, min_activity: int = 25) -> Dict[str, Any]:
        return await self._make_request('GET', '/api/weighted-guild-activities/', 
                                      params={'guild__guild_id': guild_id, 'activity__gte': min_activity})
    
    # Member Guild Activity operations
    async def add_member_guild_activity(self, activity_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('POST', '/api/member-guild-activities/', data=activity_data)
    
    async def get_member_guild_activities(self, guild_id: str, member_id: str) -> Dict[str, Any]:
        return await self._make_request('GET', '/api/member-guild-activities/', 
                                      params={'guild__guild_id': guild_id, 'member__member_id': member_id})
    
    # Guess The Hero operations
    async def create_guess_the_hero(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('POST', '/api/guess-the-hero/', data=data)
    
    async def update_guess_the_hero(self, hero_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('PUT', f'/api/guess-the-hero/{hero_id}/', data=data)
    
    # List of Choices operations
    async def create_list_of_choices(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('POST', '/api/list-of-choices/', data=data)
    
    async def get_list_of_choices_by_member(self, member_id: str) -> Dict[str, Any]:
        return await self._make_request('GET', '/api/list-of-choices/', params={'member__member_id': member_id})
    
    # Item operations
    async def create_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('POST', '/api/items/', data=data)
    
    async def get_items_by_list(self, list_id: int) -> Dict[str, Any]:
        return await self._make_request('GET', '/api/items/', params={'list': list_id})
    
    # Member Reminder operations
    async def create_reminder(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('POST', '/api/member-reminders/', data=data)
    
    async def get_active_reminders(self) -> Dict[str, Any]:
        return await self._make_request('GET', '/api/member-reminders/', params={'isComplete': False})
    
    async def update_reminder(self, reminder_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('PUT', f'/api/member-reminders/{reminder_id}/', data=data)
    
    # Member Gym Day operations
    async def create_gym_day(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('POST', '/api/member-gym-days/', data=data)
    
    async def get_gym_days_by_member(self, member_id: str) -> Dict[str, Any]:
        return await self._make_request('GET', '/api/member-gym-days/', params={'member__member_id': member_id})
    
    # Game Version operations
    async def create_game_version(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('POST', '/api/game-versions/', data=data)
    
    async def get_all_game_versions(self) -> Dict[str, Any]:
        return await self._make_request('GET', '/api/game-versions/')
    
    async def update_game_version(self, game_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('PUT', f'/api/game-versions/{game_id}/', data=data)
    
    # Game Subscription operations
    async def create_game_subscription(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('POST', '/api/game-subscriptions/', data=data)
    
    async def get_game_subscriptions_by_channel(self, channel_id: str) -> Dict[str, Any]:
        return await self._make_request('GET', '/api/game-subscriptions/', params={'channel__channel_id': channel_id})
    
    # Spotify Token operations
    async def get_spotify_token(self, member_id: str) -> Dict[str, Any]:
        return await self._make_request('GET', f'/api/spotify-tokens/by_member/', params={'member_id': member_id})
    
    async def create_or_update_spotify_token(self, member_id: str, token_data: Dict[str, Any]) -> Dict[str, Any]:
        existing = await self.get_spotify_token(member_id)
        if 'error' not in existing:
            return await self._make_request('PUT', f'/api/spotify-tokens/{existing["id"]}/', data=token_data)
        else:
            # Ensure member exists first
            await self.create_or_update_member(member_id, {})
            token_data['member'] = member_id
            return await self._make_request('POST', '/api/spotify-tokens/', data=token_data)
    
    # Channel operations
    async def create_channel(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('POST', '/api/channels/', data=data)
    
    async def get_channels_by_guild(self, guild_id: str) -> Dict[str, Any]:
        return await self._make_request('GET', '/api/channels/', params={'guild__guild_id': guild_id})
    
    # Bot Ignore Channels operations
    async def create_bot_ignore_channel(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._make_request('POST', '/api/bot-ignore-channels/', data=data)
    
    async def get_bot_ignore_channels_by_guild(self, guild_id: str) -> Dict[str, Any]:
        return await self._make_request('GET', '/api/bot-ignore-channels/', params={'guild__guild_id': guild_id})

# Global API client instance
api_client = APIClient()
