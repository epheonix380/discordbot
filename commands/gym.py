import datetime
import discord
from django.db import models
from storage.models import Member, MemberGymDay
from storage.serializers import MemberSerializer
from helpers.timeStrore import getDefaultTimezone, getFormat
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
    return data

@sync_to_async
def setMemberGymDaily(member_id:str, date:datetime.date,isGym:bool):
    [member, isMember] = Member.objects.get_or_create(member_id=member_id)
    print(member)
    print(isMember)
    memberGymDay = MemberGymDay(member=member, date=date, isGym=isGym)
    print(memberGymDay)
    memberGymDay.save()

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
        except:
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
        except:
            print(self)
            print(self.member_id)
            print(self.date)









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
            try:
                defaultTimezone = pytz.timezone(defaultTimezone)
            except:
                defaultTimezone = datetime.timezone.utc
        memberTime = datetime.datetime.now(tz=defaultTimezone)
        if memberTime.hour == 22 and member["isGym"]:
            user:discord.User = await client.fetch_user(str(member["member_id"]))
            user_dm = await user.create_dm()
            await sendGymMessage(user_dm=user_dm, date=memberTime.date())

       