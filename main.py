import discord
from commands.nsfw import handle_nsfw
from dotenv import load_dotenv
from helpers.getNSFWChannel import getNSFWChannel
import os 
load_dotenv()

TOKEN = os.getenv("TOKEN")
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message):
    if message.content.startswith(','):
        await message.channel.send("That is our prefix!")
    elif message.attachments:
        if not (message.channel.id == getNSFWChannel(message.guild.id)):
            await handle_nsfw(message)
    
    

client.run(TOKEN)