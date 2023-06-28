import datetime
import discord
from storage.models import Member
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

async def handleDailyGym(client: discord.Client):
    members = await getMembersHelper()
    print(members)
    for member in members:
        print(member)
        defaultTimezone = await getDefaultTimezone(str(member["member_id"]))
        if defaultTimezone is None:
            defaultTimezone = datetime.timezone.utc
        else:
            defaultTimezone = pytz.timezone(defaultTimezone)
        memberTime = datetime.datetime.now(tz=defaultTimezone)
        print(memberTime)
        if memberTime.hour == 21:
            user:discord.User = await client.fetch_user(str(member["member_id"]))
            user_dm = await user.create_dm()
            await user_dm.send("Gym Checkin Test!")
            