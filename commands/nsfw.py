import discord
import requests
import re

async def manual_nsfw(message):
    if (message.reference and message.reference.resolved):

        i = 0
        files = []
        for thing in message.reference.resolved.attachments:
            img_data = requests.get(thing.url).content
            with open(f"SPOILER_{i}.png", "wb") as handler:
                handler.write(img_data)
                files.append(discord.File(f"SPOILER_{i}.png"))
                i = i+1
        content = ""
        if (len(str(message.reference.resolved.content)) > 0):
            content = "||"+str(message.reference.resolved.content)+"||"
        await message.reference.resolved.channel.send(content, files=files)
        await message.reference.resolved.delete()
        await message.delete()
    else:
        await message.reply("You need to reply to a message with this command")