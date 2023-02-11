import discord
from dotenv import load_dotenv
from django.conf import settings
import os
import re
from automod.nsfw import handle_nsfw, handel_regex_nsfw
from backend import brocken as notSettings
load_dotenv()
TOKEN = os.getenv("TOKEN")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
intents = discord.Intents.default()
intents.message_content = True
if __name__ == '__main__':
    import django
    django.setup()
client = discord.Client(intents=intents)

from commands.nsfw import manual_nsfw
from commands.time import timeHandler
from commands.admin import admin
from helpers.getNSFWChannel import getNSFWChannel

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message):
    arr = []
    for match in re.finditer("https?\:\S+\.(png)|https?\:\S+\.(jpg)|https?\:\S+\.(jpeg)|https?\:\S+\.(gif)", message.content):
        if match.group(0) is not None:
            arr.append(match.group(0))
    if str(message.author.id) == "845668514341191750":
        return
    nsfwChannel = await getNSFWChannel(message.guild.id)
    if (str(nsfwChannel) != str(message.channel.id)):
        if message.attachments: #or len(message.embeds)>0:
            await handle_nsfw(message)
        elif len(arr) != 0:
            await handel_regex_nsfw(message)
    if message.content.startswith(",nsfw"):
        await manual_nsfw(message=message)
    elif message.content.startswith(",time"):
        await timeHandler(message=message)
    elif message.content.startswith(",admin"):
        await admin(message=message)
    elif message.content.startswith(','):
        await message.channel.send("That is our prefix!")


    
    

client.run(TOKEN)