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
    return regex is not None and len(regex) > 0


async def addReminder(message:discord.Message):
    inRegex = re.findall("(?<=(\sin\s))[\w\W]+?(?=$|(to)|(repeat after))",message.content)
    onRegex = re.findall("(?<=(\son\s))[\w\W]+?(?=$|(to)|(repeat after))",message.content)
    atRegex = re.findall("(?<=(\sat\s))[\w\W]+?(?=$|(to)|(repeat after))",message.content)
    amount = 0 + 1 if checkRegex(inRegex) else 0 + 1 if checkRegex(onRegex) else 0 + 1 if checkRegex(atRegex) else 0
    if amount == 1:
        message.channel.send("Hi")
    elif amount > 1:
        message.channel.send("Too many identifiers")
    else:
        message.channel.send("Too little identifiers")
