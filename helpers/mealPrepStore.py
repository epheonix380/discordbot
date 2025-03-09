from storage.models import GuildMealPrepping, MemberMealPrepperMap, Member, MMPMWeek
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
def setGuildMealPrep(guild_id, channel_id, day_of_week=None, carbs=None, protein=None, bad=None):

    update_defaults = {}
    create_defaults = {
        "channel_id":channel_id,
        "day_of_week": "mon",
        "carbs": "Rice, Pasta, Noodle, Bread, Potato, Any, None of them",
        "protein": "Beef, Pork, Chicken, Vegetarian, seafood, Safe, Beef, Pork, Chicken, seafood",
        "bad": "color is red, budget it 5 bucks, safe, color is green, Cant use stove, safe, Must have dairy, Include a dessert, Safe"
    }
    if channel_id is not None:
        update_defaults['channel_id'] = channel_id
        create_defaults['channel_id'] = channel_id
    if day_of_week is not None:
        update_defaults['day_of_week'] = day_of_week
        create_defaults['day_of_week'] = day_of_week
    if carbs is not None:
        update_defaults['carbs'] = carbs
        create_defaults['carbs'] = carbs
    if protein is not None:
        update_defaults['protein'] = protein
        create_defaults['protein'] = protein
    if bad is not None:
        update_defaults['bad'] = bad
        create_defaults['bad'] = bad
    obj, isCreate = GuildMealPrepping.objects.update_or_create(
        guild_id=guild_id, 
        defaults=update_defaults,
        create_defaults=create_defaults)

@sync_to_async
def createForAllMembers(guild_id: str, createFunc: function):
    gmp = GuildMealPrepping.objects.filter(guild__guild_id=guild_id).first()
    if gmp is not None:
        mmpm = MemberMealPrepperMap.objects.filter(meal_prep=gmp)
        for member in mmpm:
            week, retries, carb, protein, bad = createFunc(gmp.day_of_week, gmp.retries, gmp.carbs, gmp.protein, gmp.bad)
            MMPMWeek.objects.create(mmpm=mmpm, week=week, retries=retries, carb=carb, protein=protein, bad=bad)
        return True
    return False

# 
@sync_to_async
def getMemberMealPrep(member_id):
    qs = MemberMealPrepperMap.objects.filter(member_id__member_id = member_id)
    data = MemberMealPrepSerializer(qs, many=True).data
    return data

@sync_to_async
def getMemberMealPrepInGuild(member_id, guild_id):
    guild_meal = GuildMealPrepping.objects.filter(guild__guild_id = guild_id).first()
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
