from storage.models import Member, SpotifyLink
from helpers.db import sync_to_async  # resilient wrapper: reconnects after a Postgres restart

@sync_to_async
def getLink(uid):
    qs = SpotifyLink.objects.filter(member__member_id=uid)
    if (qs.count() > 0):
        link = qs[0]
        return {
            "credentials": link.credentials,
            "spotify_username": link.spotify_username,
            "scope": link.scope,
        }
    else:
        return None

@sync_to_async
def setLink(uid, credentials, spotify_username="", scope=""):
    member, member_created = Member.objects.get_or_create(member_id=uid)
    link, created = SpotifyLink.objects.update_or_create(member=member, defaults={
        "credentials": credentials,
        "spotify_username": spotify_username,
        "scope": scope,
    })
    return created

@sync_to_async
def deleteLink(uid):
    qs = SpotifyLink.objects.filter(member__member_id=uid)
    if (qs.count() > 0):
        qs[0].delete()
        return True
    return False
