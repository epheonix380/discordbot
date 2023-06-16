import discord
import datetime
from helpers.statsStore import getEvents
from helpers.timeStrore import getFormat, getDefaultTimezone
import pytz

async def handleSummary(message:discord.Message):
    instructions = message.content.split(" ")
    quantity = 5
    msgContent = []
    if (len(instructions)>1):
        quantity = int(instructions[1])
    events = await getEvents(message.guild.id, quantity)
    if (events is not None):
        timeFormat = await getFormat(message.author.id)
        defaultTimezone = await getDefaultTimezone(message.author.id)
        if defaultTimezone is None:
            defaultTimezone = datetime.timezone.utc
        else:
            defaultTimezone = pytz.timezone(defaultTimezone)
        for event in events:
            print(event['dateTime'])
            dateTime:datetime.datetime = event['dateTime']
            dateTime.replace(tzinfo=datetime.timezone.utc)
            dateTime = dateTime.astimezone(defaultTimezone)
            msgContent.append(f"At {dateTime.strftime(timeFormat)} https://discord.com/channels/{message.guild.id}/{event['channel_id']}/{event['startingMessage']}")
        content = "\n".join(msgContent)
        await message.channel.send(content=content)
    else:
        await message.channel.send("No summaries for now, check back later!")