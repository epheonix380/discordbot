import discord
import datetime
import pytz
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

    for reminder in reminders:
        time = datetime.datetime.strptime((reminder["time"]), "%Y-%m-%dT%H:%M:%S.%fZ")
        if (reminder["frequency"][2:3] == ":"):
            freq = datetime.datetime.strptime(reminder["frequency"], '%H:%M:%S')
            frequency = datetime.timedelta(days=freq.day, hours=freq.hour, minutes=freq.minute, seconds=freq.second)
        else:  
            freq = datetime.datetime.strptime(reminder["frequency"][-8:-1:], '%H:%M:%S')
            freq1 = datetime.timedelta(days=freq.day, hours=freq.hour, minutes=freq.minute, seconds=freq.second)
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
