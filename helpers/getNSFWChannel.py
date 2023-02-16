from storage.models import Guild
from asgiref.sync import sync_to_async

@sync_to_async
def getNSFWChannel(guild_id):
    qs = Guild.objects.filter(guild_id=guild_id) # pylint: disable=maybe-no-member
    if (qs.count() > 0):
        return str(qs[0].nsfw_channel)
    else:
        return None