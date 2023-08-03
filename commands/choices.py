import random
import discord
from helpers.choiceStore import getRecentChoice, setRecentChoice

async def saveChoices(message):
    instructions = message.content.split(" ")
    name = instructions[1]
    choices_string = " ".join(instructions[2::])
    choices = choices_string.split(",")
    await setRecentChoice(uid=message.author.id, list=choices, name=name)
    await message.channel.send(f"Successfully added choices named {name}")
    await message.delete()


async def choices(message: discord.Message, client:discord.Client):
    if message.reference is not None:
        channel = client.get_channel(message.reference.channel_id)
        oldMessage:discord.Message = await channel.fetch_message(message.reference.message_id)
        lines = oldMessage.content.splitlines()
        choices = lines[1].split(", ")
        oldChoice = lines[3]
        if len(choices) > 1:
            choices.remove(oldChoice)
            choice = random.choice(choices)
            choicesString = ', '.join(choices)
            content = f"Choosing from these options:\n{choicesString}\nChose:\n{choice}"
            await message.channel.send(content)
        await message.channel.send("List is only 1 long, cannot remove anymore items")
    elif len(message.content) <= 9:
        choices = await getRecentChoice(uid=message.author.id)
        choice = random.choice(choices)
        choicesString = ', '.join(choices)
        content = f"Choosing from these options:\n{choicesString}\nChose:\n{choice['name']}"
        await message.channel.send(content)
    elif len(message.content.split(" "))==2:
        instructions = message.content.split(" ")
        name = instructions[1]
        choices = await getRecentChoice(uid=message.author.id, name=name)
        choice = random.choice(choices)
        choicesString = ', '.join(choices)
        content = f"Choosing from these options:\n{choicesString}\nChose:\n{choice['name']}"
        await message.channel.send(content)
    else:
        content = message.content[8::]
        choices = content.split(",")
        await setRecentChoice(uid=message.author.id, list=choices)
        choice = random.choice(choices)
        choicesString = ', '.join(choices)
        content = f"Choosing from these options:\n{choicesString}\nChose:\n{choice}"
        await message.channel.send(content)
    await message.delete()