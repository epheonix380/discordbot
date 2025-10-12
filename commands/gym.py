import datetime
import discord
from api_client import api_client
from helpers.timeStrore import getDefaultTimezone, getFormat
from helpers.timeUtils import getTimeFromString
import pytz
import time
import asyncio

async def handleGymOptInHelper(message:discord.Message):
    async with api_client as client:
        # Get or create member
        existing_member = await client.get_member_by_id(str(message.author.id))
        if 'error' in existing_member:
            # Create new member
            await client.create_or_update_member(str(message.author.id), {
                'isGym': True
            })
        else:
            # Update existing member
            await client.create_or_update_member(str(message.author.id), {
                'isGym': True
            })

async def getMemberTime(uid):
    async with api_client as client:
        member = await client.get_member_by_id(str(uid))
        if 'error' not in member:
            return member.get('gymCheckinTime')
        return None
    
async def getMemberDate(uid):
    async with api_client as client:
        member = await client.get_member_by_id(str(uid))
        if 'error' not in member:
            return member.get('lastGymCheckinDate')
        return None
    
async def setMemberDate(uid, date:datetime.date):
    async with api_client as client:
        await client.create_or_update_member(str(uid), {
            'lastGymCheckinDate': date.isoformat()
        })
        return True
    
async def setMemberTime(message:discord.Message, time:datetime.time):
    async with api_client as client:
        await client.create_or_update_member(str(message.author.id), {
            'gymCheckinTime': time.isoformat()
        })
        return True

async def handleGymOptIn(message:discord.Message):
    await handleGymOptInHelper(message)
    await message.channel.send("Opted in to gym")

async def getMembersHelper():
    async with api_client as client:
        # Get all members with isGym=True
        result = await client._make_request('GET', '/api/members/', params={'isGym': 'true'})
        if 'error' not in result:
            return result.get('results', [])
        return []

async def getGymObjectsHelper(member_id:str):
    async with api_client as client:
        # Get gym days for member since 2023-07-10
        result = await client._make_request('GET', '/api/member-gym-days/', params={
            'member__member_id': member_id,
            'date__gte': '2023-07-10'
        })
        if 'error' not in result:
            return result.get('results', [])
        return []

async def getIsMemberCheckedIn(uid, date:datetime.date):
    async with api_client as client:
        result = await client._make_request('GET', '/api/member-gym-days/', params={
            'member__member_id': uid,
            'date': date.isoformat()
        })
        if 'error' not in result:
            results = result.get('results', [])
            if len(results) > 0:
                return results[0].get('isGym')
        return None

async def setMemberGymDaily(member_id:str, date:datetime.date, isGym:bool):
    async with api_client as client:
        # Ensure member exists
        await client.create_or_update_member(member_id, {})
        
        # Create gym day record
        await client._make_request('POST', '/api/member-gym-days/', data={
            'member': member_id,
            'date': date.isoformat(),
            'isGym': isGym
        })

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
        except Exception as e:
            print(f"Error: {e}")
            await interaction.channel.send(f"Unfortunately you do not exist in our systems")
 

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
        except Exception as e:
            print(f"Error: {e}")
            await interaction.channel.send(f"Unfortunately you do not exist in our systems")









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

       