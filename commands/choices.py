import random
from helpers.choiceStore import getRecentChoice, setRecentChoice

async def choices(message):
    if len(message.content) <= 9:
        choices = await getRecentChoice(uid=message.author.id)
        print(choices)
        choice = random.choice(choices)
        await message.channel.send(choice['name'])
    else:
        content = message.content[8::]
        choices = content.split(",")
        await setRecentChoice(uid=message.author.id, list=choices)
        choice = random.choice(choices)
        await message.channel.send(choice)
    await message.delete()