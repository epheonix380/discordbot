import discord
from .session import PlayerSession

async def start_player(message: discord.Message, client: discord.Client):
    voice:discord.VoiceState = message.author.voice   
    vc:discord.VoiceProtocol = await voice.channel.connect()
    session = PlayerSession(guild_name=message.guild.name, channel_name=message.channel.name)
    
    