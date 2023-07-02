import datetime
import discord
from storage.models import Member, MemberGymDay
from storage.serializers import MemberSerializer
from helpers.timeStrore import getDefaultTimezone
import pytz
from asgiref.sync import sync_to_async

@sync_to_async
def handleGymOptInHelper(message:discord.Message):
    [member, isCreated] = Member.objects.get_or_create(member_id=message.author.id)
    member.isGym = True
    member.save()

async def handleGymOptIn(message:discord.Message):
    await handleGymOptInHelper(message)
    await message.channel.send("Opted in to gym")

@sync_to_async
def getMembersHelper():
    qs =  Member.objects.filter(isGym=True)
    data = MemberSerializer(qs, many=True).data
    print(data)
    return data

@sync_to_async
def setMemberGymDaily(member_id:str, date:datetime.date,isGym:bool):
    member = Member.objects.get(member_id=member_id)
    memberGymDay = MemberGymDay(member=member, date=date, isGym=isGym)
    memberGymDay.save()

class GymButtonYes(discord.ui.Button):
    def __init__(self, member_id:str, date:datetime.date):
        super().__init__(style=discord.ButtonStyle.success, row=0)
        self.member_id = member_id
        self.date = date
        self.label = "Yes"

    async def callback(self, interaction: discord.Interaction):
        await setMemberGymDaily(member_id=self.member_id, date=self.date, isGym=True)
        await interaction.channel.send("Recorded")

class GymButtonNo(discord.ui.Button):
    def __init__(self, member_id:str, date:datetime.date):
        super().__init__(style=discord.ButtonStyle.red, row=0)
        self.member_id = member_id
        self.date = date
        self.label = "No"


    async def callback(self, interaction: discord.Interaction):
        await setMemberGymDaily(member_id=self.member_id, date=self.date, isGym=False)
        await interaction.channel.send("Recorded")




class GymView(discord.ui.View):
    def __init__(self , member_id:str, date:datetime.date):
        super().__init__()
        self.add_item(GymButtonNo(member_id=member_id, date=date))
        self.add_item(GymButtonYes(member_id=member_id, date=date))

async def sendGymMessage(user_dm:discord.DMChannel, date:datetime.date):
    await user_dm.send(content="Exercise checkin, did you do exercise today?", view=GymView(member_id=user_dm.recipient.id, date=date))
     

async def handleDailyGym(client: discord.Client):
    members = await getMembersHelper()
    for member in members:
        defaultTimezone = await getDefaultTimezone(str(member["member_id"]))
        if defaultTimezone is None:
            defaultTimezone = datetime.timezone.utc
        else:
            defaultTimezone = pytz.timezone(defaultTimezone)
        memberTime = datetime.datetime.now(tz=defaultTimezone)
        if memberTime.hour == 22 and member["isGym"]:
            user:discord.User = await client.fetch_user(str(member["member_id"]))
            user_dm = await user.create_dm()
            await sendGymMessage(user_dm=user_dm, date=memberTime.date())

       