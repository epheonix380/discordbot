import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import os
import json
import base64
import requests

from api_client import api_client

logger = logging.getLogger(__name__)

class LibrespotManager:
    """
    Manages librespot sessions and Spotify Connect integration
    Uses Python 3.13 asyncio features
    """
    
    def __init__(self):
        self.sessions: Dict[str, Any] = {}  # guild_id -> session info
        self.device_name = os.getenv('SPOTIFY_DEVICE_NAME', 'Discord Bot')
        
    async def get_spotify_token(self, member_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Spotify token for a member from the API using Python 3.13 asyncio
        """
        async with api_client as client:
            result = await client.get_spotify_token(member_id)
            if 'error' not in result:
                return result
            return None
    
    async def refresh_spotify_token(self, member_id: str) -> Optional[Dict[str, Any]]:
        """
        Refresh Spotify token using refresh token
        """
        token_data = await self.get_spotify_token(member_id)
        if not token_data:
            return None
            
        client_id = os.getenv('SPOTIFY_CLIENT_ID')
        client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        
        if not all([client_id, client_secret]):
            logger.error("Missing Spotify credentials")
            return None
        
        try:
            token_url = 'https://accounts.spotify.com/api/token'
            auth_string = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
            
            headers = {
                'Authorization': f'Basic {auth_string}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': token_data['refresh_token']
            }
            
            response = requests.post(token_url, headers=headers, data=data)
            
            if response.status_code == 200:
                new_token_data = response.json()
                
                # Update token in database
                expires_in = new_token_data.get('expires_in', 3600)
                expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                updated_token_data = {
                    'access_token': new_token_data.get('access_token'),
                    'expires_at': expires_at.isoformat(),
                    'scope': new_token_data.get('scope', token_data['scope'])
                }
                
                # Keep existing refresh token if not provided
                if 'refresh_token' in new_token_data:
                    updated_token_data['refresh_token'] = new_token_data['refresh_token']
                else:
                    updated_token_data['refresh_token'] = token_data['refresh_token']
                
                async with api_client as client:
                    await client.create_or_update_spotify_token(member_id, updated_token_data)
                
                return updated_token_data
            else:
                logger.error(f"Token refresh failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Token refresh exception: {str(e)}")
            return None
    
    async def is_token_valid(self, token_data: Dict[str, Any]) -> bool:
        """
        Check if Spotify token is still valid
        """
        if not token_data:
            return False
            
        expires_at = datetime.fromisoformat(token_data['expires_at'].replace('Z', '+00:00'))
        return datetime.now() < expires_at - timedelta(minutes=5)  # 5 minute buffer
    
    async def get_valid_token(self, member_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a valid Spotify token, refreshing if necessary
        """
        token_data = await self.get_spotify_token(member_id)
        if not token_data:
            return None
            
        if await self.is_token_valid(token_data):
            return token_data
        
        # Token expired, try to refresh
        logger.info(f"Token expired for member {member_id}, attempting refresh")
        refreshed_token = await self.refresh_spotify_token(member_id)
        return refreshed_token
    
    async def create_librespot_session(self, guild_id: str, member_id: str) -> bool:
        """
        Create a librespot session for the guild
        """
        try:
            # Get valid token
            token_data = await self.get_valid_token(member_id)
            if not token_data:
                logger.error(f"No valid token for member {member_id}")
                return False
            
            # Import librespot here to avoid import errors if not installed
            try:
                from librespot.core import Session
            except ImportError:
                logger.error("librespot not installed. Install with: pip install git+https://github.com/kokarare1212/librespot-python.git")
                return False
            
            # Create session
            session = Session.Builder() \
                .user_pass(member_id, token_data['access_token']) \
                .create()
            
            # Store session info
            self.sessions[guild_id] = {
                'session': session,
                'member_id': member_id,
                'created_at': datetime.now(),
                'token_data': token_data
            }
            
            logger.info(f"Created librespot session for guild {guild_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create librespot session: {str(e)}")
            return False
    
    async def get_session(self, guild_id: str) -> Optional[Any]:
        """
        Get librespot session for guild
        """
        if guild_id not in self.sessions:
            return None
            
        session_info = self.sessions[guild_id]
        
        # Check if token needs refresh
        if not await self.is_token_valid(session_info['token_data']):
            logger.info(f"Refreshing token for guild {guild_id}")
            new_token = await self.refresh_spotify_token(session_info['member_id'])
            if new_token:
                session_info['token_data'] = new_token
            else:
                logger.error(f"Failed to refresh token for guild {guild_id}")
                return None
        
        return session_info['session']
    
    async def destroy_session(self, guild_id: str) -> bool:
        """
        Destroy librespot session for guild
        """
        if guild_id in self.sessions:
            try:
                session_info = self.sessions[guild_id]
                if 'session' in session_info:
                    # Close session if possible
                    pass
                del self.sessions[guild_id]
                logger.info(f"Destroyed librespot session for guild {guild_id}")
                return True
            except Exception as e:
                logger.error(f"Error destroying session: {str(e)}")
                return False
        return True
    
    async def play_track(self, guild_id: str, track_uri: str) -> bool:
        """
        Play a track using librespot
        """
        session = await self.get_session(guild_id)
        if not session:
            logger.error(f"No session for guild {guild_id}")
            return False
        
        try:
            # This would need to be implemented based on librespot capabilities
            # For now, we'll just log the attempt
            logger.info(f"Attempting to play track {track_uri} for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to play track: {str(e)}")
            return False
    
    async def pause_playback(self, guild_id: str) -> bool:
        """
        Pause playback
        """
        session = await self.get_session(guild_id)
        if not session:
            return False
        
        try:
            logger.info(f"Pausing playback for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause playback: {str(e)}")
            return False
    
    async def resume_playback(self, guild_id: str) -> bool:
        """
        Resume playback
        """
        session = await self.get_session(guild_id)
        if not session:
            return False
        
        try:
            logger.info(f"Resuming playback for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to resume playback: {str(e)}")
            return False
    
    async def get_playback_state(self, guild_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current playback state
        """
        session = await self.get_session(guild_id)
        if not session:
            return None
        
        try:
            # This would return current playback info
            return {
                'is_playing': True,  # Placeholder
                'track': None,       # Placeholder
                'position': 0        # Placeholder
            }
        except Exception as e:
            logger.error(f"Failed to get playback state: {str(e)}")
            return None

# Global librespot manager instance
librespot_manager = LibrespotManager()
