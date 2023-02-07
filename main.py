import discord
from dotenv import load_dotenv
import os
import re
from commands.nsfw import handle_nsfw, handel_regex_nsfw
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
    if str(message.author.id) == "845668514341191750":
        return
    elif message.content.startswith(','):
        await message.channel.send("That is our prefix!")
    elif message.attachments or len(message.embeds)>0:
        await handle_nsfw(message)
    elif re.match("(http)s?\:\S*\.(?:png|jpg|jpeg|gif)", message.content):
        await handel_regex_nsfw(message)

    
    

client.run(TOKEN)