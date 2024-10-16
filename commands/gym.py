import datetime
import discord
from django.db import models
from storage.models import Member, MemberGymDay
from storage.serializers import MemberSerializer, MemberGymDaySerializer
from helpers.timeStrore import getDefaultTimezone, getFormat
from helpers.timeUtils import getTimeFromString
import pytz
import time
from asgiref.sync import sync_to_async

@sync_to_async
def handleGymOptInHelper(message:discord.Message):
    [member, isCreated] = Member.objects.get_or_create(member_id=message.author.id)
    member.isGym = True
    member.save()

@sync_to_async
def getMemberTime(uid):
    try:
        member = Member.objects.get(member_id=uid)
        return member.gymCheckinTime
    except:
        return None
    
@sync_to_async
def getMemberDate(uid):
    try:
        member = Member.objects.get(member_id=uid)
        return member.lastGymCheckinDate
    except:
        return None
    
@sync_to_async
def setMemberDate(uid, date:datetime.date):
    try:
        member = Member.objects.get(member_id=uid)
        member.lastGymCheckinDate = date
        member.save()
        return True
    except:
        return None
    
@sync_to_async
def setMemberTime(message:discord.Message, time:datetime.time):
    try:
        member = Member.objects.get(member_id=message.author.id)
        member.gymCheckinTime = time
        member.save()
    except:
        return False

async def handleGymOptIn(message:discord.Message):
    await handleGymOptInHelper(message)
    await message.channel.send("Opted in to gym")

@sync_to_async
def getMembersHelper():
    qs =  Member.objects.filter(isGym=True)
    data = MemberSerializer(qs, many=True).data
    return data

@sync_to_async
def getGymObjectsHelper(member_id:str):
    qs = MemberGymDay.objects.filter(member_id__member_id=member_id, date__gte=datetime.date(year=2023, month=7, day=10)).order_by("date")
    data = MemberGymDaySerializer(qs, many=True).data
    return data


@sync_to_async
def getIsMemberCheckedIn(uid, date:datetime.date):
    qs = MemberGymDay.objects.filter(member__member_id=uid, date=date)
    if qs.count() == 0:
        return None
    else:
        return qs[0].isGym


@sync_to_async
def setMemberGymDaily(member_id:str, date:datetime.date,isGym:bool):
    [member, isMember] = Member.objects.get_or_create(member_id=member_id)
    print(member)
    print(isMember)
    memberGymDay = MemberGymDay(member=member, date=date, isGym=isGym)
    print(memberGymDay)
    memberGymDay.save()

async def handleGym(message:discord.Message, client:discord.Client):
    instructions = message.content.split(" ")
    if (len(instructions) > 1):
        if instructions[1] == "time":
            memberTime:datetime.time = await getMemberTime(message.author.id)
            timeFormat = await getFormat(message.author.id)
            if len(instructions) > 2:
                time = getTimeFromString("".join(instructions[2::]))
                await setMemberTime(message,time)
            else:
                formatedTime = memberTime.strftime(timeFormat)
                await message.channel.send(f"Your current checkin time is: {formatedTime}")
        elif instructions[1] == "checkin":
            
            defaultTimezone = await getDefaultTimezone(message.author.id)
            if defaultTimezone is None:
                defaultTimezone = datetime.timezone.utc
            else:
                try:
                    defaultTimezone = pytz.timezone(defaultTimezone)
                except:
                    defaultTimezone = datetime.timezone.utc
            memberTime:datetime.datetime = datetime.datetime.now(tz=defaultTimezone)
            user:discord.User = await client.fetch_user(message.author.id)
            user_dm = await user.create_dm()
            checkin = await getIsMemberCheckedIn(message.author.id, memberTime.date())
            timeFormat = await getFormat(message.author.id)
            if checkin is not None:
                await user_dm.send(f"Looks like you already checked in today and said that you **{'did' if checkin else 'did not'} do** exercise")
            else:
                await sendGymMessage(user_dm=user_dm, date=memberTime.date(), format=timeFormat)
        elif instructions[1] == "register":
            await handleGymOptIn(message=message)
        elif instructions[1] == "status":
            await handleGymStatus(message=message)
    else:
        await message.channel.send("Specifier required")
    await message.delete()


class GymButtonYes(discord.ui.Button):
    def __init__(self, member_id:str, date:datetime.date):
        super().__init__(style=discord.ButtonStyle.success, row=0)
        self.member_id = member_id
        self.date = date
        self.label = "Yes"

    async def callback(self, interaction: discord.Interaction):
        try:
            await setMemberGymDaily(member_id=self.member_id, date=self.date, isGym=True)
            await interaction.message.delete()
            format:str = await getFormat(self.member_id)
            format = format.replace("%H","").replace("%M","").replace("%I","").replace("%p","").replace(":","")
            formatedDate = self.date.strftime(format)
            await interaction.channel.send(f"Recorded as Yes for {formatedDate}")
        except models.Model.DoesNotExist:
            print("Member Does not exist")
            await interaction.channel.send(f"Unfortunately you do not exist in our systems")
        except:
            await interaction.channel.send(f"A weird error occured please contact your discord admin")
            print(self)
            print(self.member_id)
            print(self.date)
 

class GymButtonNo(discord.ui.Button):
    def __init__(self, member_id:str, date:datetime.date):
        super().__init__(style=discord.ButtonStyle.red, row=0)
        self.member_id = member_id
        self.date = date
        self.label = "No"


    async def callback(self, interaction: discord.Interaction):
        try:
            await setMemberGymDaily(member_id=self.member_id, date=self.date, isGym=False)
            await interaction.message.delete()
            format:str = await getFormat(self.member_id)
            format = format.replace("%H","").replace("%M","").replace("%I","").replace("%p","").replace(":","")
            formatedDate = self.date.strftime(format)
            await interaction.channel.send(f"Recorded as No for {formatedDate}")
        except models.Model.DoesNotExist:
            print("Member Does not exist")
            await interaction.channel.send(f"Unfortunately you do not exist in our systems")
        except:
            await interaction.channel.send(f"A weird error occured please contact your discord admin")
            print(self)
            print(self.member_id)
            print(self.date)









class GymView(discord.ui.View):
    def __init__(self , member_id:str, date:datetime.date ):
        super().__init__(timeout=None)
        self.timeout = None
        self.add_item(GymButtonNo(member_id=member_id, date=date))
        self.add_item(GymButtonYes(member_id=member_id, date=date))

async def sendGymMessage(user_dm:discord.DMChannel, date:datetime.date, format:str="%d-%m-%Y"):
    await user_dm.send(content=f"Exercise checkin for {date.strftime(format)}, did you do exercise today?", view=GymView(member_id=user_dm.recipient.id, date=date))

async def handleGymStatus(message:discord.Message):
    data = await getGymObjectsHelper(member_id=message.author.id)
    gymCount = 0
    latestDate = datetime.datetime(year=2023, month=7, day=10).date()
    weeks = []
    currentWeekCount = -1
    dates = []
    i=0
    for day in data:
        date = datetime.datetime.strptime(day["date"],"%Y-%m-%d").date()
        if date in dates:
            pass
        if date > latestDate:
            latestDate = date
        dates.append(date.isoformat())
        if date.isoweekday() == 1:
            currentWeekCount = currentWeekCount + 1
            weeks.append(0)
        elif i==0:
            currentWeekCount = 0
            weeks.append(0)
        if day["isGym"]:
            gymCount = gymCount + 1
            weeks[currentWeekCount] = weeks[currentWeekCount] + 1
        i = i + 1
    weekProgress = 0
    totalOwed = 0
    difference = datetime.datetime.now().date() - datetime.datetime(year=2023, month=7, day=10).date()
    total = difference.days
    print(total)
    i=0
    isThisWeekComplete = False
    howManyLeft = 0
    for week in weeks:
        if i<len(weeks)-1:
            if week >= 4:
                weekProgress = weekProgress + 1
            else:
                totalOwed = totalOwed + 1
        else:
            if week>=4:
                isThisWeekComplete = True
            else:
                howManyLeft = 4-week
        i = i + 1

    if len(weeks)-1 > 0 and total > 0:
        await message.channel.send(f"You have done exercise for {gymCount} out of {total} days. Thats {(gymCount*100)/total}%!\nYou have done 4 or more days of training in {weekProgress} out of {len(weeks)-1} weeks, thats {(weekProgress*100)/(len(weeks)-1)}%!\nThat means you only owe ${totalOwed*10} to the Japan trip fund.")
        if isThisWeekComplete:
            await message.channel.send(f"You have completed the goal of 4 sessions per week this week, congrats!")
        else:
            await message.channel.send(f"Looks like you need to exercise {howManyLeft} more times this week")
    elif total > 0:
        await message.channel.send(f"You have done exercise for {gymCount} out of {total} days. Thats {(gymCount*100)/total}%!\nThat means you only owe ${totalOwed*10} to the Japan trip fund.")
        if isThisWeekComplete:
            await message.channel.send(f"You have completed the goal of 4 sessions per week this week, congrats!")
        else:
            await message.channel.send(f"Looks like you need to exercise {howManyLeft} more times this week")
    else:
        await message.channel.send("You need to log your activity for at least 1 day for status to be available. Log it using ,gym checkin")



async def handleDailyGym(client: discord.Client):
    members = await getMembersHelper()
    time.sleep(0)
    for member in members:
        time.sleep(0)
        defaultTimezone = await getDefaultTimezone(str(member["member_id"]))
        if defaultTimezone is None:
            defaultTimezone = datetime.timezone.utc
        else:
            try:
                defaultTimezone = pytz.timezone(defaultTimezone)
            except:
                defaultTimezone = datetime.timezone.utc
        memberTime = datetime.datetime.now(tz=defaultTimezone)
        checkinTime:datetime.time = await getMemberTime(member["member_id"])
        if memberTime.hour == checkinTime.hour and memberTime.time()>=checkinTime and member["isGym"]:
            checkin = await getIsMemberCheckedIn(member["member_id"], memberTime.date())
            user:discord.User = await client.fetch_user(str(member["member_id"]))
            user_dm = await user.create_dm()
            if checkin is not None:
                print("Already checked in")
                print(user.global_name)
            else:
                lastSentData:datetime.date = await getMemberDate(member["member_id"])
                if memberTime.date() == lastSentData:
                    print("Already sent message")
                    print(user.global_name)
                else:
                    timeFormat = await getFormat(member["member_id"])
                    await sendGymMessage(user_dm=user_dm, date=memberTime.date(), format=timeFormat)
                    await setMemberDate(member["member_id"], memberTime.date())

       