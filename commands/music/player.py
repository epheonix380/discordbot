import discord

async def start_player(author: discord.Member, client: discord.Client):
    voice:discord.VoiceState = author.voice   
    vc:discord.VoiceProtocol = await voice.channel.connect()
    
    