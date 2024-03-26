import discord
import requests
import re

async def nsfw_helper_reference(message: discord.Message):
    i = 0
    files = []
    for thing in message.reference.resolved.attachments:
        img_data = requests.get(thing.url).content
        with open(f"SPOILER_{i}_{thing.filename}", "wb") as handler:
            handler.write(img_data)
            files.append(discord.File(f"SPOILER_{i}_{thing.filename}"))
            i = i+1
    content = ""
    if (len(str(message.reference.resolved.content)) > 0):
        content = "||"+str(message.reference.resolved.content)+"||"
    sentMessage = await message.reference.resolved.channel.send(content, files=files)
    sentBy = f"Sent by: <@{message.reference.resolved.author.id}>\n"
    await sentMessage.edit(content=sentBy+sentMessage.content)
    await message.reference.resolved.delete()
    await message.delete()

async def nsfw_helper(message: discord.Message):
    i = 0
    files = []
    for thing in message.attachments:
        img_data = requests.get(thing.url).content
        with open(f"SPOILER_{i}_{thing.filename}", "wb") as handler:
            handler.write(img_data)
            files.append(discord.File(f"SPOILER_{i}_{thing.filename}"))
            i = i+1
    content = ""
    if (len(str(message.content)) > 0):
        content = "||"+str(message.content)+"||"
    sentMessage = await message.channel.send(content, files=files)
    sentBy = f"Sent by: <@{message.author.id}>\n"
    await sentMessage.edit(content=sentBy+sentMessage.content)
    await message.delete()

async def manual_nsfw(message: discord.Message):
    if (message.reference and message.reference.resolved):
        await nsfw_helper_reference(message=message)
    else:
        channel: discord.TextChannel = message.channel
        history: list[discord.Message] = channel.history(limit=50, before=message, oldest_first=False)
        regex = re.compile("https?\:\S+\.(png)|https?\:\S+\.(jpg)|https?\:\S+\.(jpeg)|https?\:\S+\.(gif)")
        async for msg in history:
            if msg.author.id != 845668514341191750:
                arr = re.finditer(regex, msg.content)
                if len(msg.attachments) > 0:
                    await nsfw_helper(message=msg)
                    return
                elif any(elem.group(0) is not None for elem in arr):
                    await nsfw_helper(message=msg)
                    return
