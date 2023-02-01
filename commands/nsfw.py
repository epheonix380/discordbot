from nudenet import NudeClassifier
import requests
classifier = NudeClassifier()

async def handle_nsfw(message):
    trigger = True
    for thing in message.attachments:
        
        
        img_data = requests.get(thing.url).content
        with open("ideallyHashed.png", "wb") as handler:
            handler.write(img_data)
        obj = classifier.classify("ideallyHashed.png")
        if obj["ideallyHashed.png"]['safe']< 0.5:
            trigger = trigger and False
            await message.reply(content="We believe this to be nsfw")
        trigger = trigger and True
    if trigger:
        await message.reply(content="No nsfw images detected")