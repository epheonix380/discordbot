from storage.models import Guild
from helpers.db import sync_to_async  # resilient wrapper: reconnects after a Postgres restart

@sync_to_async
def getNSFWChannel(guild_id):
    qs = Guild.objects.filter(guild_id=guild_id) 
    if (qs.count() > 0):
        return str(qs[0].nsfw_channel)
    else:
        return None