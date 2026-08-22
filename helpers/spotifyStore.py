from storage.models import Member, SpotifyLink
from helpers.db import sync_to_async, sync_db  # resilient wrappers: reconnect after a Postgres restart

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


# Synchronous variants for callers already off the event loop -- specifically
# music/credentials.py, which mints an access token from librespot's supervisor
# thread and must persist the rotated refresh token in the same critical
# section. Same connection guard as the async helpers above.

@sync_db
def getLinkSync(uid):
    qs = SpotifyLink.objects.filter(member__member_id=uid)
    if (qs.count() > 0):
        link = qs[0]
        return {
            "credentials": link.credentials,
            "spotify_username": link.spotify_username,
            "scope": link.scope,
        }
    return None


@sync_db
def setCredentialsSync(uid, credentials):
    """Overwrite just the credentials blob. Returns False if there is no link."""
    qs = SpotifyLink.objects.filter(member__member_id=uid)
    if (qs.count() == 0):
        return False
    link = qs[0]
    link.credentials = credentials
    link.save(update_fields=["credentials", "updated_at"])
    return True
