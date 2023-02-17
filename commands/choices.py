import random
from helpers.choiceStore import getRecentChoice, setRecentChoice

async def saveChoices(message):
    instructions = message.content.split(" ")
    name = instructions[1]
    choices_string = " ".join(instructions[2::])
    choices = choices_string.split(",")
    await setRecentChoice(uid=message.author.id, list=choices, name=name)
    await message.channel.send(f"Successfully added choices named {name}")
    await message.delete()


async def choices(message):
    if len(message.content) <= 9:
        choices = await getRecentChoice(uid=message.author.id)
        choice = random.choice(choices)
        await message.channel.send(choice['name'])
    elif len(message.content.split(" "))==2:
        instructions = message.content.split(" ")
        name = instructions[1]
        choices = await getRecentChoice(uid=message.author.id, name=name)
        choice = random.choice(choices)
        await message.channel.send(choice['name'])
    else:
        content = message.content[8::]
        choices = content.split(",")
        await setRecentChoice(uid=message.author.id, list=choices)
        choice = random.choice(choices)
        await message.channel.send(choice)
    await message.delete()