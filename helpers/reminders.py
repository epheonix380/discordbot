import discord
import datetime
import re
import pytz
import time as TIME
from asgiref.sync import sync_to_async
from storage.models import Member, MemberReminder
from storage.serializers import MemberReminderSerializer

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
        if tzTime<currentTime:
            user:discord.User = await client.fetch_user(str(member["member_id"]))
            user_dm = await user.create_dm()
            await user_dm.send(reminder["reminder_text"])
            newTime = tzTime + frequency
            await updateReminder(id=str(reminder["id"]), newTime=newTime, tzTime=tzTime)
            


@sync_to_async
def addReminder(member_id:str,reminder_text:str, time:datetime.datetime, frequency:datetime.timedelta = datetime.timedelta(seconds=0), isComplete:bool = False):
    member = Member.objects.get(member_id=member_id)
    print(time)
    reminder = MemberReminder(member=member, reminder_text=reminder_text, time=time, frequency=frequency, isComplete=isComplete)
    reminder.save()

def checkRegex(regex):
    return regex is not None

async def handleReminderAdd(message:discord.Message):
    inRegex = re.search("(?<=(\sin\s))[\w\W]+?(?=$|(to)|(repeat after))",message.content)
    onRegex = re.search("(?<=(\son\s))[\w\W]+?(?=$|(to)|(repeat after))",message.content)
    atRegex = re.search("(?<=(\sat\s))[\w\W]+?(?=$|(to)|(repeat after))",message.content)
    toRegex = re.search("(?<=(\sto\s))[\w\W]+?(?=$|(in)|(at)|(on)|(repeat after))",message.content)
    to = ""
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
            minuteRegex = re.search("[\d]+?(?=\s+?((mins)|(minutes)))",inGroup)
            if checkRegex(daysRegex):
                days = daysRegex.group(0)
            if checkRegex(hourRegex):
                hours = hourRegex.group(0)
            if checkRegex(minuteRegex):
                minutes = minuteRegex.group(0)
            now = datetime.datetime.now()
            await addReminder(member_id=message.author.id, reminder_text=to, time=now, frequency=datetime.timedelta(days=days, hours=hours, minutes=minutes))
            await message.channel.send("Added reminder")
        elif checkRegex(onRegex):
            print(onRegex.group(0))
        elif checkRegex(atRegex):
            print(atRegex.group(0))
        await message.channel.send("Hi")
    elif amount > 1:
        await message.channel.send("Too many identifiers")
    else:
        await message.channel.send("Too little identifiers")
