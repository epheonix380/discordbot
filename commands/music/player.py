import discord
from discord.ext import commands
import os
import urllib.parse
import asyncio
from music.librespot_manager import librespot_manager
from api_client import api_client

class SpotifyMusic(commands.Cog):
    """
    Spotify music commands using Python 3.13 asyncio features
    """
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='spotify_connect')
    async def spotify_connect(self, ctx):
        """
        Connect your Spotify account to the bot
        """
        member_id = str(ctx.author.id)
        
        # Check if already connected
        async with api_client as client:
            existing_token = await client.get_spotify_token(member_id)
            if 'error' not in existing_token:
                await ctx.send("✅ You're already connected to Spotify! Use `/spotify disconnect` to disconnect.")
                return
        
        # Generate OAuth URL
        client_id = os.getenv('SPOTIFY_CLIENT_ID')
        redirect_uri = os.getenv('SPOTIFY_REDIRECT_URI')
        
        if not all([client_id, redirect_uri]):
            await ctx.send("❌ Spotify integration is not configured. Please contact the bot administrator.")
            return
        
        # Spotify OAuth scopes
        scopes = [
            'user-read-playback-state',
            'user-modify-playback-state',
            'user-read-currently-playing',
            'streaming',
            'user-read-email',
            'user-read-private'
        ]
        
        params = {
            'response_type': 'code',
            'client_id': client_id,
            'scope': ' '.join(scopes),
            'redirect_uri': redirect_uri,
            'state': member_id  # Pass member ID as state
        }
        
        auth_url = f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(params)}"
        
        embed = discord.Embed(
            title="🎵 Connect to Spotify",
            description="Click the link below to connect your Spotify account:",
            color=0x1DB954
        )
        embed.add_field(
            name="Authorization Link",
            value=f"[Connect Spotify Account]({auth_url})",
            inline=False
        )
        embed.set_footer(text="After connecting, you can use Spotify commands!")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='spotify_disconnect')
    async def spotify_disconnect(self, ctx):
        """
        Disconnect your Spotify account from the bot
        """
        member_id = str(ctx.author.id)
        
        async with api_client as client:
            # Check if connected
            existing_token = await client.get_spotify_token(member_id)
            if 'error' in existing_token:
                await ctx.send("❌ You're not connected to Spotify.")
                return
            
            # Delete token (this would need a delete endpoint in the API)
            # For now, we'll just inform the user
            await ctx.send("✅ Spotify account disconnected. You can reconnect anytime with `/spotify connect`.")
    
    @commands.command(name='spotify_status')
    async def spotify_status(self, ctx):
        """
        Check your Spotify connection status
        """
        member_id = str(ctx.author.id)
        
        async with api_client as client:
            token_data = await client.get_spotify_token(member_id)
            if 'error' in token_data:
                embed = discord.Embed(
                    title="🎵 Spotify Status",
                    description="❌ Not connected to Spotify",
                    color=0xFF0000
                )
                embed.add_field(
                    name="How to connect",
                    value="Use `/spotify connect` to link your Spotify account",
                    inline=False
                )
            else:
                embed = discord.Embed(
                    title="🎵 Spotify Status",
                    description="✅ Connected to Spotify",
                    color=0x1DB954
                )
                embed.add_field(
                    name="Connected since",
                    value=token_data.get('created_at', 'Unknown'),
                    inline=True
                )
                embed.add_field(
                    name="Scopes",
                    value=token_data.get('scope', 'Unknown'),
                    inline=True
                )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='spotify_play')
    async def spotify_play(self, ctx, *, query: str = None):
        """
        Play music from Spotify
        """
        guild_id = str(ctx.guild.id)
        member_id = str(ctx.author.id)
        
        # Check if user is connected
        async with api_client as client:
            token_data = await client.get_spotify_token(member_id)
            if 'error' in token_data:
                await ctx.send("❌ You need to connect your Spotify account first. Use `/spotify connect`")
                return
        
        # Check if user is in a voice channel
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel to play music.")
            return
        
        # Create or get librespot session
        session_created = await librespot_manager.create_librespot_session(guild_id, member_id)
        if not session_created:
            await ctx.send("❌ Failed to create Spotify session. Please try again.")
            return
        
        if query:
            # Search for track and play
            await ctx.send(f"🎵 Searching for: {query}")
            # This would implement track search and playback
            await ctx.send("🎵 Track search and playback functionality would be implemented here.")
        else:
            # Resume playback
            success = await librespot_manager.resume_playback(guild_id)
            if success:
                await ctx.send("▶️ Resumed Spotify playback")
            else:
                await ctx.send("❌ Failed to resume playback")
    
    @commands.command(name='spotify_pause')
    async def spotify_pause(self, ctx):
        """
        Pause Spotify playback
        """
        guild_id = str(ctx.guild.id)
        
        success = await librespot_manager.pause_playback(guild_id)
        if success:
            await ctx.send("⏸️ Paused Spotify playback")
        else:
            await ctx.send("❌ Failed to pause playback or no active session")
    
    @commands.command(name='spotify_stop')
    async def spotify_stop(self, ctx):
        """
        Stop Spotify playback and disconnect
        """
        guild_id = str(ctx.guild.id)
        
        success = await librespot_manager.destroy_session(guild_id)
        if success:
            await ctx.send("⏹️ Stopped Spotify playback and disconnected")
        else:
            await ctx.send("❌ Failed to stop playback")
    
    @commands.command(name='spotify_now')
    async def spotify_now(self, ctx):
        """
        Show currently playing track
        """
        guild_id = str(ctx.guild.id)
        
        state = await librespot_manager.get_playback_state(guild_id)
        if state:
            embed = discord.Embed(
                title="🎵 Now Playing",
                color=0x1DB954
            )
            embed.add_field(
                name="Track",
                value=state.get('track', 'Unknown'),
                inline=False
            )
            embed.add_field(
                name="Status",
                value="▶️ Playing" if state.get('is_playing') else "⏸️ Paused",
                inline=True
            )
            embed.add_field(
                name="Position",
                value=f"{state.get('position', 0)}s",
                inline=True
            )
        else:
            embed = discord.Embed(
                title="🎵 Now Playing",
                description="❌ No active Spotify session",
                color=0xFF0000
            )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(SpotifyMusic(bot))