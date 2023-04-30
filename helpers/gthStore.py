from storage.models import GuessTheHero
from asgiref.sync import sync_to_async

@sync_to_async
def setHeroImage(guild_id,image_url,id):
    gth = GuessTheHero(guild_id=guild_id,image_url=image_url,message_id=id)
    gth.save()
    return str(gth.pk)

@sync_to_async
def setHeroName(pk, hero_name):
    gth = GuessTheHero.objects.get(pk=pk)
    gth.hero_name = hero_name
    gth.save()

@sync_to_async
def setMsgId(pk, message_id):
    gth = GuessTheHero.objects.get(pk=pk)
    gth.message_id = message_id
    gth.save()

@sync_to_async
def setHeroGuessed(guild_id):
    qs = GuessTheHero.objects.filter(guild_id=guild_id).order_by("-created_at")
    if (qs.count() > 0):
        pk = qs[0].pk
        gth = GuessTheHero.objects.get(pk=pk)
        gth.guessed = True
        gth.save()

@sync_to_async
def setHeroGuessedViaMsgId(guild_id, message_id):
    qs = GuessTheHero.objects.filter(guild_id=guild_id, message_id=message_id)
    if (qs.count() > 0):
        pk = qs[0].pk
        gth = GuessTheHero.objects.get(pk=pk)
        gth.guessed = True
        gth.save()

@sync_to_async
def getHeroGuessed(guild_id):
    qs = GuessTheHero.objects.filter(guild_id=guild_id).order_by("-created_at")
    if (qs.count() > 0):
        return qs[0].guessed
    else:
        return False

@sync_to_async
def getHeroName(guild_id):
    qs = GuessTheHero.objects.filter(guild_id=guild_id).order_by("-created_at")
    if (qs.count() > 0):
        return str(qs[0].hero_name)
    else:
        return None

@sync_to_async
def getHeroNameViaMsgId(guild_id, message_id):
    qs = GuessTheHero.objects.filter(guild_id=guild_id, message_id=message_id)
    if (qs.count() > 0):
        return str(qs[0].hero_name)
    else:
        return None

@sync_to_async
def getHeroImage(guild_id):
    qs = GuessTheHero.objects.filter(guild_id=guild_id).order_by("-created_at")
    if (qs.count() > 0):
        return str(qs[0].image_url)
    else:
        return None
    
@sync_to_async
def getHeroReady(guild_id):
    qs = GuessTheHero.objects.filter(guild_id=guild_id).order_by("-created_at")
    if (qs.count() > 0):
        return str(qs[0].hero_name)==""
    else:
        return None
