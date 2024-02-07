import discord
import datetime
import re
import pytz
import time as TIME
from asgiref.sync import sync_to_async
from storage.models import Member, MemberReminder
from storage.serializers import MemberReminderSerializer
from helpers.timeStrore import getDefaultTimezone, getFormat

@sync_to_async
def getMembersHelper():
    qs =  MemberReminder.objects.filter(isComplete=False, time__lte=datetime.datetime.now(tz=datetime.timezone.utc))
    serialized = MemberReminderSerializer(qs, many=True)
    data = serialized.data
    return data

@sync_to_async
def updateReminder(id:str, newTime:datetime.datetime, tzTime:datetime.datetime):
    memberReminder = MemberReminder.objects.get(id=id)
    if newTime == tzTime:
        memberReminder.delete()
    else:
        memberReminder.time=newTime
        memberReminder.save()

@sync_to_async
def deleteReminder(id:str):
    memberReminder = MemberReminder.objects.get(id=id)
    memberReminder.delete()

async def handleReminderCheck(client:discord.Client):
    reminders = await getMembersHelper()
    currentTime = datetime.datetime.now(tz=datetime.timezone.utc)
    TIME.sleep(0)
    for reminder in reminders:
        TIME.sleep(0)

        time = datetime.datetime.strptime((reminder["time"]), "%Y-%m-%dT%H:%M:%S.%fZ")
        if (reminder["frequency"][2:3] == ":"):
            freq = datetime.datetime.strptime(reminder["frequency"], '%H:%M:%S')
            frequency = datetime.timedelta(hours=freq.hour, minutes=freq.minute, seconds=freq.second)
        else:  
            freq = datetime.datetime.strptime(reminder["frequency"][-8:-1:], '%H:%M:%S')
            freq1 = datetime.timedelta(hours=freq.hour, minutes=freq.minute, seconds=freq.second)
            freq2 = datetime.timedelta(days=int(reminder["frequency"][:-9:]))
            frequency = freq1 + freq2
        member = reminder["member"]
        tzTime = time.replace(tzinfo=datetime.timezone.utc)
        if tzTime<currentTime and tzTime+datetime.timedelta(minutes=5)>currentTime:
            if reminder["target"] is not None:
                channel:discord.guild.GuildChannel = await client.fetch_channel(int(reminder["origin_channel"]))
                await channel.send(content=f"<@{reminder['target']}> reminder to {reminder['reminder_text']}")
            else:
                user:discord.User = await client.fetch_user(str(member["member_id"]))
                user_dm = await user.create_dm()
                await user_dm.send(reminder["reminder_text"])
            newTime = tzTime + frequency
            await updateReminder(id=str(reminder["id"]), newTime=newTime, tzTime=tzTime)
        elif tzTime<currentTime:
            await deleteReminder(id=str(reminder["id"]))

            


@sync_to_async
def addReminder(member_id:str,origin_guild:str,origin_channel:str, target:str, reminder_text:str, time:datetime.datetime, frequency:datetime.timedelta = datetime.timedelta(seconds=0), isComplete:bool = False):
    member = Member.objects.get(member_id=member_id)
    reminder = MemberReminder(member=member,origin_guild=origin_guild, origin_channel=origin_channel, reminder_text=reminder_text, time=time, frequency=frequency, isComplete=isComplete, target=target)
    reminder.save()

def checkRegex(regex):
    return regex is not None

async def handleReminderAdd(message:discord.Message):
    inRegex = re.search("(?<=(\sin\s))[\w\W]+?(?=$|( to )|( repeat after ))",message.content)
    onRegex = re.search("(?<=(\son\s))[\w\W]+?(?=$|( to )|( repeat after ))",message.content)
    atRegex = re.search("(?<=(\sat\s))[\w\W]+?(?=$|( to )|( repeat after ))",message.content)
    toRegex = re.search("(?<=(\sto\s))[\w\W]+?(?=$|( in )|( at )|( on )|( repeat after ))",message.content)
    to = ""
    origin_guild = message.guild.id
    origin_channel = message.channel.id
    target = None
    split = message.content.split(" ")
    if split[1] == "me":
        target = None
    elif split[1].startswith("<@") and split[1].endswith(">"):
        target = split[1][2:-1:1]
    if checkRegex(toRegex):
        to = toRegex.group(0)
    amount = 0 + 1 if checkRegex(inRegex) else 0 + 1 if checkRegex(onRegex) else 0 + 1 if checkRegex(atRegex) else 0
    if amount == 1:
        days = 0
        hours = 0
        minutes = 0
        if checkRegex(inRegex):
            inGroup = inRegex.group(0)
            daysRegex = re.search("[\d]+?(?=\s+?((days)|(day)))",inGroup)
            hourRegex = re.search("[\d]+?(?=\s+?((hours)|(hour)|(hrs)|(hr)|(h)))",inGroup)
            minuteRegex = re.search("[\d]+?(?=\s+?((min)|(mins)|(minutes)|(minute)))",inGroup)
            if checkRegex(daysRegex):
                days = int(daysRegex.group(0))
            if checkRegex(hourRegex):
                hours = int(hourRegex.group(0))
            if checkRegex(minuteRegex):
                minutes = int(minuteRegex.group(0))
            now = datetime.datetime.now(tz=datetime.timezone.utc)
            future_time = now + datetime.timedelta(days=days, hours=hours, minutes=minutes)
            await addReminder(member_id=message.author.id, reminder_text=to, time=future_time, target=target, origin_guild=origin_guild, origin_channel=origin_channel)
            await message.channel.send(f"I'll remind {'you' if target is None else '<@' + target + '>'} in {str(days)+' days, ' if days>0 else ''}{str(hours)+' hours, ' if hours>0 else ''}{str(minutes)+' minutes' if minutes>0 else ''} to {to}")
        elif checkRegex(onRegex):
            print(onRegex.group(0))
        elif checkRegex(atRegex):
            atGroup = atRegex.group(0)
            hourRegex = re.search("[\d]{1,2}(?=\s?((pm)|(:)|(am)))",atGroup)
            minuteRegex = re.search("(?<=(:))[\d]{2}", atGroup)
            pmRegex = re.search("(?<=\d)(pm)", atGroup)
            userTimezone = await getDefaultTimezone(message.author.id)
            if userTimezone is None:
                content = "No default timezone found:\nThis version of the command requires you to set a default timezone if you do not want to set one you can use this command instead:\n```,time convert <time> <from-city-name> to <to-city-name>```\nOr you can set your default timezone using this command:\n```,time default <city-name>```"
                return await message.channel.send(content)
            if checkRegex(hourRegex):
                hours = int(hourRegex.group(0))
                if checkRegex(pmRegex):
                    if(pmRegex.group(0) == "pm"):
                        hours = (hours + 12)%24
            if checkRegex(minuteRegex):
                minutes = int(minuteRegex.group(0))
            fromTimeZone = pytz.timezone(userTimezone)
            today = datetime.datetime.now(tz=fromTimeZone)
            future_time = fromTimeZone.localize(datetime.datetime(year=today.year, month=today.month, day=today.day, hour=hours, minute=minutes))
            if (future_time < today):
                future_time = future_time + datetime.timedelta(days=1)
            timeFormat = await getFormat(message.author.id)
            formatedTimeString = future_time.strftime(timeFormat)
            await addReminder(member_id=message.author.id, reminder_text=to, time=future_time, target=target, origin_guild=origin_guild, origin_channel=origin_channel)
            await message.channel.send(f"I'll remind {'you' if target is None else '<@' + target + '>'} at {formatedTimeString}")
        
    elif amount > 1:
        await message.channel.send("Too many identifiers")
    else:
        await message.channel.send("Too little identifiers")
