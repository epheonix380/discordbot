from storage.models import GuildMealPrepping, MemberMealPrepperMap, Member, MMPMWeek, Guild, Channel, ChannelCategories
from storage.serializers import GuildMealPrepperSerializer, MemberMealPrepSerializer
from asgiref.sync import sync_to_async

@sync_to_async
def getGuildMealPrep(guild_id):
    qs = GuildMealPrepping.objects.filter(guild__guild_id=guild_id).first()
    if qs is not None:
        data = GuildMealPrepperSerializer(data).data
        return data
    else:
        return None

@sync_to_async
def setGuildMealPrep(guild_id, channel_id, day_of_week=None, retries=None, carbs=None, protein=None, bad=None):
    try:
        guild, isCreate = Guild.objects.get_or_create(guild_id=guild_id)
        channel, isChannelNew = Channel.objects.get_or_create(channel_id=channel_id, guild=guild, defaults={
            "category": ChannelCategories.MEAL_PREP
        })
        obj = GuildMealPrepping(guild=guild, channel=channel)
        obj.save()
        return True
    except:
        return False

@sync_to_async
def createForAllMembers(guild_id: str, createFunc):
    gmp = GuildMealPrepping.objects.filter(guild__guild_id=guild_id).first()
    if gmp is not None:
        mmpm = MemberMealPrepperMap.objects.filter(meal_prep=gmp)
        success = []
        for member in mmpm:
            week, retries, carb, protein, bad = createFunc(gmp.day_of_week, gmp.retries, gmp.carbs, gmp.protein, gmp.bad)
            MMPMWeek.objects.create(mmpm=member, week=week, retries=retries, carb=carb, protein=protein, bad=bad)
            success.append(member.member_id)
        return [gmp.guild.guild_id, gmp.channel.channel_id, success]
    return [gmp.guild.guild_id, gmp.channel.channel_id,[]]

# 
@sync_to_async
def getMemberMealPrep(member_id):
    qs = MemberMealPrepperMap.objects.filter(member_id__member_id = member_id)
    data = MemberMealPrepSerializer(qs, many=True).data
    return data

@sync_to_async
def getMemberMealPrepInGuild(member_id, guild_id):
    guild_meal = GuildMealPrepping.objects.filter(guild__guild_id=guild_id).first()
    if guild_meal is not None:
        qs = MemberMealPrepperMap.objects.filter(member_id__member_id = member_id, meal_prep=guild_meal).first()
        data = MemberMealPrepSerializer(qs).data
        return data
    return None

@sync_to_async
def addMemberToGuildMealPrep(member_id, guild_id):
    gmp = GuildMealPrepping.objects.filter(guild__guild_id=guild_id).first()
    member, memberCreated = Member.objects.get_or_create(member_id=member_id)
    if gmp is not None:
        MemberMealPrepperMap.objects.create(member_id=member, meal_prep=gmp)
        return True
    else:
        return False
    
@sync_to_async
def removeMemberFromGuildMealPrep(member_id, guild_id):
    member, memberCreated = Member.objects.get_or_create(member_id=member_id)
    if memberCreated:
        return False
    guild = GuildMealPrepping.objects.filter(guild__guild_id=guild_id).first()
    if guild is not None:
        memberMap = MemberMealPrepperMap.objects.filter(member_id=member, meal_prep=guild).first()
        if memberMap is not None:
            memberMap.delete()
            return True
    return False
