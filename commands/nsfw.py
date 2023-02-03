from nudenet.classifier import Classifier as NudeClassifier
import discord
import requests
import re
classifier = NudeClassifier()

async def handle_nsfw(message):
    trigger = True
    containsEmbeds = False
    i = 0
    files = []
    for thing in message.attachments:
        img_data = requests.get(thing.url).content
        with open(f"SPOILER_{i}.png", "wb") as handler:
            handler.write(img_data)
        obj = classifier.classify(f"SPOILER_{i}.png")
        if obj[f"SPOILER_{i}.png"]['safe']< 0.5:
            trigger = trigger and False
            files.append(discord.File(f"SPOILER_{i}.png"))
        else:
            with open(f"{i}.png", "wb") as handler:
                handler.write(img_data)
                files.append(discord.File(f"{i}.png"))
            trigger = trigger and True
        i = i+1
    for embed in message.embeds:
        img_data = requests.get(embed.url).content
        with open(f"SPOILER_{i}.png", "wb") as handler:
            handler.write(img_data)
        obj = classifier.classify(f"SPOILER_{i}.png")
        if obj[f"SPOILER_{i}.png"]['safe']< 0.5:
            containsEmbeds = True
            trigger = trigger and False
            files.append(discord.File(f"SPOILER_{i}.png"))
        else:
            with open(f"{i}.png", "wb") as handler:
                handler.write(img_data)
                files.append(discord.File(f"{i}.png"))
            trigger = trigger and True
            
        i=i+1
    if trigger:
        return
    else:
        if containsEmbeds:
            newContent = re.sub("(http)s?\:\S*\.(?:png|jpg|jpeg|gif)","NSFW LINK DETECTED", message.content)
            await message.channel.send(newContent, files=files)
        else:
            await message.channel.send(message.content, files=files)
        await message.delete()
