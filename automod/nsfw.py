import discord
import requests
import re
from nudity import NudeDetector

def check_conditions(labels):
    for label in labels:
        if label["class"] == "BELLY_EXPOSED":
            if label["score"] > 0.75:
                print("BELLY_EXPOSED")
                return True
        if label["class"] == "FEMALE_GENITALIA_COVERED":
            if label["score"] > 0.99:
                print("FEMALE_GENITALIA_COVERED")
                return True
        if label["class"] == "BUTTOCKS_EXPOSED":
            if label["score"] > 0.5:
                print("BUTTOCKS_EXPOSED")
                return True
        if label["class"] == "FEMALE_BREAST_EXPOSED":
            if label["score"] > 0.5:
                print("FEMALE_BREAST_EXPOSED")
                return True
        if label["class"] == "FEMALE_GENITALIA_EXPOSSED":
            if label["score"] > 0.5:
                print("FEMALE_GENITALIA_EXPOSSED")
                return True
        if label["class"] == "ANUS_EXPOSED":
            if label["score"] > 0.5:
                print("ANUS_EXPOSED")
                return True
        if label["class"] == "MALE_GENITALIA_EXPOSED":
            if label["score"] > 0.5:
                print("MALE_GENITALIA_EXPOSED")
                return True
    return False

async def handle_nsfw(message: discord.Message):
    trigger = True
    nude_detector = NudeDetector()
    nsfw_count = 0
    containsEmbeds = False
    regex = re.compile("https?\:\S+\.(png)|https?\:\S+\.(jpg)|https?\:\S+\.(jpeg)|https?\:\S+\.(gif)")
    i = 0
    files = []
    for thing in message.attachments:
        try:
            img_data = requests.get(thing.url).content
            with open(f"SPOILER_{i}_{thing.filename}", "wb") as handler:
                handler.write(img_data)
                obj = nude_detector.detect(f"SPOILER_{i}_{thing.filename}")
                print(obj)
                if check_conditions(obj):
                    nsfw_count = nsfw_count + 1
                    trigger = trigger and False
                    files.append(discord.File(f"SPOILER_{i}_{thing.filename}"))
                else:
                    with open(f"{i}_{thing.filename}", "wb") as handler:
                        handler.write(img_data)
                        files.append(discord.File(f"{i}_{thing.filename}"))
                        trigger = trigger and True
                i = i+1
        except:
            continue
    for embed in message.embeds:
        try:
            img_data = requests.get(embed.url).content
            with open(f"SPOILER_{i}_{thing.filename}", "wb") as handler:
                handler.write(img_data)
                obj = nude_detector.detect(f"SPOILER_{i}_{thing.filename}")
                print(obj)

                if check_conditions(obj):
                    nsfw_count = nsfw_count + 1
                    containsEmbeds = True
                    trigger = trigger and False
                    files.append(discord.File(f"SPOILER_{i}_{thing.filename}"))
                else:
                    with open(f"{i}_{thing.filename}", "wb") as handler:
                        handler.write(img_data)
                        files.append(discord.File(f"{i}_{thing.filename}"))
                        trigger = trigger and True
                i=i+1
        except Exception as e:
            print(str(e))
            continue
        
    if trigger:
        return nsfw_count
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
        return nsfw_count

async def handel_regex_nsfw(message):
    trigger = True
    nude_detector = NudeDetector()
    containsEmbeds = False
    nsfw_count = 0
    i = 0
    files = []
    regex = re.compile("https?\:\S+\.(png)|https?\:\S+\.(jpg)|https?\:\S+\.(jpeg)|https?\:\S+\.(gif)")
    arr = re.finditer(regex, message.content)
    for match in arr:
        try:
            if match.group(0) is not None:
                img_data = requests.get(str(match.group(0))).content
                with open(f"SPOILER_{i}.png", "wb") as handler:
                    handler.write(img_data)
                    obj = nude_detector.detect(f"SPOILER_{i}.png")
                    print(obj)

                    if check_conditions(obj):
                        nsfw_count = nsfw_count + 1
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
        return nsfw_count
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
        return nsfw_count
        