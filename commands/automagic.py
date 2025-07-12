import discord
import re
from helpers.timeStrore import getDefaultTimezone
import pytz
import datetime
import math

async def automagic(message: discord.Message):
    timeStringRaw = re.findall(r"(\d\d?:\d\d\s?(am)?(pm)?)",message.content)
    reply = ""
    for timeStringTuple in timeStringRaw:
        timeString = timeStringTuple if type(timeStringTuple) is str else timeStringTuple[0]
        if len(timeString) > 0:
            defaultTimeZone = await getDefaultTimezone(message.author.id)
            if defaultTimeZone is not None:
                hour = int(timeString.split(":")[0])
                minute = int(timeString.split(":")[1][0:2])
                if (len(timeString.split(":")[1])>=4 and timeString.split(":")[1][-2:].lower()=="pm"):
                    hour = (hour + 12)%24
                timezone = pytz.timezone(defaultTimeZone)
                today = datetime.datetime.now(tz=timezone)
                time = timezone.localize(datetime.datetime(year=today.year, month=today.month, day=today.day, hour=hour, minute=minute))
                reply += f"{timeString} **-->** <t:{math.floor(time.timestamp())}:t>\n"
    timeStringRaw = re.findall(r"\b(?:1[0-2]|[1-9])\s?[ap]m\b",message.content)
    for timeStringTuple in timeStringRaw:
        timeString = timeStringTuple if type(timeStringTuple) is str else timeStringTuple[0]
        if len(timeString) > 0:
            defaultTimeZone = await getDefaultTimezone(message.author.id)
            if defaultTimeZone is not None:
                hour = int(re.search(r"\d+",timeString).group(0))
                ending = "am"
                if (len(timeString)>=3 and timeString[-2:].lower()=="pm"):
                    ending = "pm"
                    hour = (hour + 12)%24
                timezone = pytz.timezone(defaultTimeZone)
                today = datetime.datetime.now(tz=timezone)
                time = timezone.localize(datetime.datetime(year=today.year, month=today.month, day=today.day, hour=hour, minute=0))
                reply += f"{timeString} **-->** <t:{math.floor(time.timestamp())}:t>\n"
    if len(reply) > 0:
        await message.reply(reply)
