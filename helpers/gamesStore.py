from storage.models import GameVersion, GameVersionSubscriptions, Channel, Guild
from storage.serializers import GameSerializer, GameSubscriptionSerializer
from asgiref.sync import sync_to_async

@sync_to_async
def getOrCreate(appid, channelid, guildid):
    qs, wasCreated = GameVersion.objects.get_or_create(appid=appid)
    guild, z = Guild.objects.get_or_create(guild_id=guildid)
    channel, y = Channel.objects.get_or_create(channel_id=channelid, guild=guild)
    game, x = GameVersionSubscriptions.objects.get_or_create(game=qs, channel=channel)
    data = GameSerializer(qs).data
    guild.save()
    channel.save()
    game.save()
    return data, wasCreated

@sync_to_async
def updateCurrentVersion(appid, version, patchVersion=None, name=None):
    qs = GameVersion.objects.get(appid=appid)
    if(name is not None):
        qs.name = name
    if(patchVersion is not None):
        qs.patchVersion = patchVersion
    qs.version = version
    qs.save()

@sync_to_async
def getAllGames():
    qs = GameVersion.objects.all()
    data = GameSerializer(qs, many=True).data
    return data

@sync_to_async
def getAllGamesForChannel(channelid):
    qs = GameVersionSubscriptions.objects.filter(channel__channel_id=channelid)
    data = GameSubscriptionSerializer(qs, many=True).data
    return data

@sync_to_async
def getAllChannelsForGame(appid):
    qs = GameVersionSubscriptions.objects.filter(game__appid=appid)
    data = GameSubscriptionSerializer(qs, many=True).data
    return data

