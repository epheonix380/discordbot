from storage.models import Member
from asgiref.sync import sync_to_async


@sync_to_async
def setSpotifyUsernameAndToken(uid,username, token):
    member, created =Member.objects.update_or_create(member_id=uid,defaults={
        "spotify_username":username,"spotify_authtoken":token})
    return created

@sync_to_async
def getSpotifyUsernameAndToken(uid):
    qs = Member.objects.get(member_id=uid)
    return {
        "username":str(qs.spotify_username),
        "token":str(qs.spotify_authtoken)
    }