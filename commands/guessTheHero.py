import re
from typing import List
import discord
from discord import ui
from discord import ButtonStyle
from discord.ui.text_input import TextStyle
from helpers.gthStore import getHeroGuessCountViaMsgId, addGuessCountViaMsgId, getHeroClueCount, getHeroGuessCount,addGuessCount, addClueCount, setHeroNameViaUserId,setHeroGuessedViaMsgId, getHeroNameViaMsgId, getHeroReady, setHeroImage, setHeroName, getHeroName, setHeroGuessed, getHeroImage,getHeroGuessed
from helpers.dota2Heroes import getDota2HeroesList, getHeroAttr, getHeroAttack, getHeroLegs
from discord import app_commands

heroes = getDota2HeroesList()

async def auto_complete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    
    choices = [discord.app_commands.Choice(name=choice, value=choice) for choice in heroes if current.lower() in choice.lower()][:25]
    return choices

async def saveHeroName(interaction : discord.Interaction, hero:str):
    if hero in heroes:
        user_id = interaction.user.id
        success = await setHeroNameViaUserId(user_id, hero)
        if success:
            await interaction.response.send_message(f"Hero is **{hero}**", ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occured", ephemeral=True)
    else:
        await interaction.response.send_message(f"**{hero}** was not recognized as a valid dota2 hero", ephemeral=True)




async def guessTheHeroHandler(message):
    arr = []
    instruction = str(message.content).strip().split(" ")
    for match in re.finditer("https?\:\S+\.(png)|https?\:\S+\.(jpg)|https?\:\S+\.(jpeg)|https?\:\S+\.(gif)", message.content):
        if match.group(0) is not None:
            arr.append(match.group(0))
    if len(instruction) == 1 and instruction[0] == ",refresh":
        url = await getHeroImage(message.guild.id)
        await message.channel.send(url)
    elif len(instruction) == 1 and instruction[0] == ",reveal":
        if message.reference is not None:
            name = await getHeroNameViaMsgId(message.guild.id, reference)

        else:
            name = await getHeroName(message.guild.id)
        await message.channel.send(f"The hero was **{name}**")
    elif len(instruction) == 1 and instruction[0] == ",clue":
        count = await getHeroClueCount(message.guild.id)
        name = await getHeroName(message.guild.id)
        if count == 0:
            clue = str(getHeroAttr(name))
            await message.channel.send(f"The main attribute of the hero is {clue}")
        elif count == 1:
            clue = str(getHeroAttack(name))
            await message.channel.send(f"The main attack of the hero is {clue}")
        elif count == 2:
            clue = str(getHeroLegs(name))
            await message.channel.send(f"The hero has {clue} legs")
        else:
            await message.channel.send("Ran out of clues use ,reveal to reveal the hero")
        await addClueCount(message.guild.id)
    elif message.attachments or len(arr) > 0:
        url = ""
        if message.attachments:
            url = message.attachments[0].url
        else:
            url = arr[0]
        guild_id = message.guild.id
        pk = await setHeroImage(guild_id, url, message.id, message.author.id)
        channel = await message.author.create_dm()
        await message.reply(f"A guess the hero image was detected, do you wish to input the hero name?\n{url}\nIf so please use /hero")
    elif message.reference is not None:
        reference = message.reference.message_id
        name = await getHeroNameViaMsgId(message.guild.id, reference)
        if name is not None and name != "":
            for match in re.finditer(f"{str(name).lower()}", str(message.content).lower()):
                if match.group(0) is not None:
                    arr.append(match.group(0))
            if (len(arr)>0):
                await setHeroGuessedViaMsgId(message.guild.id, reference)
                guessCount = str(await getHeroGuessCountViaMsgId(message.guild.id, message.id))
                await message.reply(f"Correct the hero was **{name}**, correctly guess in {guessCount} guesses")
            else:
                await addGuessCountViaMsgId(message.guild.id, message.id)
                await message.add_reaction("❌")
        else:
            await message.channel.send("We could not find that guess the hero message.")
    elif (not await getHeroGuessed(message.guild.id)) and (not await getHeroReady(message.guild.id)):
        name = await getHeroName(message.guild.id)
        arr = []
        for match in re.finditer(f"{str(name).lower()}", str(message.content).lower()):
            if match.group(0) is not None:
                arr.append(match.group(0))
        if (len(arr)>0):
            await setHeroGuessed(message.guild.id)
            guessCount = str(await getHeroGuessCount(message.guild.id))
            await message.reply(f"Correct the hero was **{name}**, correctly guess in {guessCount} guesses")
        else:
            await addGuessCount(message.guild.id)
            await message.add_reaction("❌")

