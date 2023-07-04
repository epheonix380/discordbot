import discord
from threading import Thread
from datetime import datetime
import time
import asyncio
from asgiref.sync import async_to_sync
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord import app_commands
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
intents.all()
if __name__ == '__main__':
    import django
    django.setup()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

from commands.nsfw import manual_nsfw
from commands.time import timeHandler
from commands.admin import admin
from commands.ticTacToe import tic
from commands.guessTheHero import auto_complete, guessTheHeroHandler, saveHeroName, guessHero
from commands.choices import choices, saveChoices
from helpers.guildStore import getNSFWChannel, getGuessTheHeroChannel
from helpers.statsStore import addGuildActivity, getGuildActivity
from commands.activity import handleActivity
from commands.help import helpHandler
from commands.summary import handleSummary
from commands.gym import handleDailyGym, handleGymOptIn, sendGymMessage

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message: discord.Message):
    arr = []
    for match in re.finditer("https?\:\S+\.(png)|https?\:\S+\.(jpg)|https?\:\S+\.(jpeg)|https?\:\S+\.(gif)", message.content):
        if match.group(0) is not None:
            arr.append(match.group(0))
    if str(message.author.id) == "845668514341191750":
        return
    nsfwChannel = await getNSFWChannel(message.guild.id)
    is_nsfw = 0
    if (nsfwChannel is None or str(nsfwChannel)[2:-1:1] != str(message.channel.id)):
        if message.attachments: #or len(message.embeds)>0:
            is_nsfw = await handle_nsfw(message)
        elif len(arr) != 0:
            is_nsfw = await handel_regex_nsfw(message)
    guessTheHeroChannel = await getGuessTheHeroChannel(message.guild.id)
    if (guessTheHeroChannel is not None and str(guessTheHeroChannel)[2:-1:1] == str(message.channel.id)):
        await guessTheHeroHandler(message=message)
    if message.content.startswith(",nsfw"):
        is_nsfw = 0
        await manual_nsfw(message=message)
    elif message.content.startswith(",time"):
        await timeHandler(message=message)
    elif message.content.startswith(",help"):
        await helpHandler(message=message)
    elif message.content.startswith(",admin"):
        await admin(message=message)
    elif message.content.startswith(",choose"):
        await choices(message=message)
    elif message.content.startswith(",choices"):
        await saveChoices(message=message)
    elif message.content.startswith(",activity"):
        await handleActivity(message)
    elif message.content.startswith(",summary"):
        await handleSummary(message=message)
    elif message.content.startswith(",gymOptIn"):
        await handleGymOptIn(message=message)
    elif message.content.startswith(",test"):
        await handleDailyGym(client=client)
    await addGuildActivity(message.guild.id, message, is_nsfw)

@tree.command(name="test",description="This is a test command", guild=None)
async def first_commant(interaction: discord.Interaction):
    await interaction.response.send_message("Test")

@tree.command(name="hero",description="Register a hero for guess the hero", guild=None)
@app_commands.autocomplete(hero=auto_complete)
async def first_commant(interaction: discord.Interaction,hero:str):
    await saveHeroName(interaction=interaction, hero=hero)

@tree.command(name="guess",description="Guess a hero for guess the hero", guild=None)
@app_commands.autocomplete(hero=auto_complete)
async def first_commant(interaction: discord.Interaction,hero:str):
    await guessHero(interaction=interaction, hero=hero)


@client.event
async def on_ready():
    list = await tree.sync(guild=None)
    print("Ready!")

async def tick():
    await handleDailyGym(client=client)

    
scheduler = AsyncIOScheduler()
scheduler.add_job(tick, 'interval', hours=1)
scheduler.start()
loop = asyncio.get_event_loop()
loop.create_task(client.start(TOKEN))
loop.run_forever()


