from nudenet.classifier import Classifier as NudeClassifier
import discord
import requests
classifier = NudeClassifier()

async def handle_nsfw(message):
    trigger = True
    i = 0
    files = []
    for thing in message.attachments:
        img_data = requests.get(thing.url).content
        with open("SPOILER_{i}.png", "wb") as handler:
            handler.write(img_data)
        obj = classifier.classify("SPOILER_{i}.png")
        if obj["SPOILER_{i}.png"]['safe']< 0.5:
            trigger = trigger and False
            files.append(discord.File("SPOILER_{i}.png"))
        else:
            trigger = trigger and True
            files.append(discord.File("{i}.png"))
    if trigger:
        return
    else:
        await message.channel.send(message.content, files=files)
        await message.delete()
