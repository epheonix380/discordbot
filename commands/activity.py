import discord
import re
from helpers.statsStore import getGuildActivity, getIndividualGuildID

async def handleActivity(message:discord.Message):
    instructions = message.content.split(" ")
    if (len(instructions) > 1):
        firstInstruction = re.search("\d{18}",instructions[1])
        if (firstInstruction is not None and firstInstruction.group(0) != ""):
            member_id = firstInstruction.group(0)
            file = await getIndividualGuildID(message.guild.id,message.author.id, message)
            discordFile = discord.File(fp=file, filename=file)
            await message.channel.send("Here is the activity for this member", file=discordFile)

    else:
        file = await getGuildActivity(message.guild.id, message)
        discordFile = discord.File(fp=file, filename=file)
        await message.channel.send("Here is the activity for this guild", file=discordFile)