from storage.models import Guild
from asgiref.sync import sync_to_async

@sync_to_async
def getNSFWChannel(uid):
    qs = Guild.objects.filter(guild_id=uid) 
    if (qs.count() > 0):
        return str(qs[0].nsfw_channel)
    else:
        return None

@sync_to_async
def setNSFWChannel(uid, channelID):
    member, created = Guild.objects.update_or_create(guild_id=uid,defaults={
        'nsfw_channel':str(channelID)
    })
    return created

@sync_to_async
def getGuessTheHeroChannel(uid):
    qs = Guild.objects.filter(guild_id=uid) 
    if (qs.count() > 0):
        return str(qs[0].guess_the_hero)
    else:
        return None

@sync_to_async
def setGuessTheHeroChannel(uid, channelID):
    member, created = Guild.objects.update_or_create(guild_id=uid,defaults={
        'guess_the_hero':str(channelID)
    })
    return created
