from nudenet.classifier import Classifier as NudeClassifier
import discord
import requests
import re
classifier = NudeClassifier()

async def handle_nsfw(message):
    trigger = True
    containsEmbeds = False
    regex = re.compile("https?\:\S+\.(png)|https?\:\S+\.(jpg)|https?\:\S+\.(jpeg)|https?\:\S+\.(gif)")
    i = 0
    files = []
    for thing in message.attachments:
        try:
            img_data = requests.get(thing.url).content
            with open(f"SPOILER_{i}.png", "wb") as handler:
                handler.write(img_data)
                obj = classifier.classify(f"SPOILER_{i}.png")
                if obj[f"SPOILER_{i}.png"]['safe']< 0.4 or (message.author.id == "226315767564599297" and obj[f"SPOILER_{i}.png"]['safe']< 0.75):
                    
                    trigger = trigger and False
                    files.append(discord.File(f"SPOILER_{i}.png"))
                else:
                    with open(f"{i}.png", "wb") as handler:
                        handler.write(img_data)
                        files.append(discord.File(f"{i}.png"))
                        trigger = trigger and True
                i = i+1
        except:
            continue
    for embed in message.embeds:
        try:
            img_data = requests.get(embed.url).content
            with open(f"SPOILER_{i}.png", "wb") as handler:
                handler.write(img_data)
                obj = classifier.classify(f"SPOILER_{i}.png")
                if obj[f"SPOILER_{i}.png"]['safe']< 0.4 or (message.author.id == "226315767564599297" and obj[f"SPOILER_{i}.png"]['safe']< 0.75):
                    
                    containsEmbeds = True
                    trigger = trigger and False
                    files.append(discord.File(f"SPOILER_{i}.png"))
                else:
                    with open(f"{i}.png", "wb") as handler:
                        handler.write(img_data)
                        files.append(discord.File(f"{i}.png"))
                        trigger = trigger and True
                i=i+1
                print("test1")
        except Exception as e:
            print(str(e))
            continue
        
    if trigger:
        return
    else:
        sentMessage = ""
        if containsEmbeds:
            newContent = re.sub(regex,"NSFW LINK DETECTED", message.content)
            sentMessage = await message.channel.send(newContent, files=files)
        else:
            sentMessage = await message.channel.send(message.content, files=files)
        sentBy = f"Sent by: <@{message.author.id}>\n"
        await sentMessage.edit(content=sentBy+sentMessage.content)
        await message.delete()

async def handel_regex_nsfw(message):
    trigger = True
    containsEmbeds = False
    i = 0
    files = []
    regex = re.compile("https?\:\S+\.(png)|https?\:\S+\.(jpg)|https?\:\S+\.(jpeg)|https?\:\S+\.(gif)")
    arr = re.finditer(regex, message.content)
    for match in arr:
        print(match)
        try:
            if match.group(0) is not None:
                img_data = requests.get(str(match.group(0))).content
                with open(f"SPOILER_{i}.png", "wb") as handler:
                    handler.write(img_data)
                    obj = classifier.classify(f"SPOILER_{i}.png")
                    if obj[f"SPOILER_{i}.png"]['safe']< 0.4 or (message.author.id == "226315767564599297" and obj[f"SPOILER_{i}.png"]['safe']< 0.75):
                        
                        containsEmbeds = True
                        trigger = trigger and False
                        files.append(discord.File(f"SPOILER_{i}.png"))
                    else:
                        with open(f"{i}.png", "wb") as handler:
                            handler.write(img_data)
                            files.append(discord.File(f"{i}.png"))
                            trigger = trigger and True
                    i=i+1
        except Exception as e:
            print(str(e))
            continue
    if trigger:
        return
    else:
        sentMessage = ""
        if containsEmbeds:
            newContent = re.sub(regex,"NSFW LINK DETECTED", message.content)
            sentMessage = await message.channel.send(newContent, files=files)
        else:
            sentMessage = await message.channel.send(message.content, files=files)
        sentBy = f"Sent by: <@{message.author.id}>\n"
        await sentMessage.edit(content=sentBy+sentMessage.content)
        await message.delete()
        