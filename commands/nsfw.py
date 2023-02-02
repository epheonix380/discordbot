from nudenet.classifier import Classifier as NudeClassifier
import discord
from storage.models import *
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
        else:
            files += discord.File("SPOILER_{i}.png")
        trigger = trigger and True
    if trigger:
        return
    else:
        await message.channel.send(message.content, files=files)