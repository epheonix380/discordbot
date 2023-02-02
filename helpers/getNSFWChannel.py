from storage.models import Guild

def getNSFWChannel(guild_id):
    qs = Guild.objects.filter(guild_id=guild_id) 
    if (qs.count > 0):
        return str(qs[0].guild_id)
    else:
        return None