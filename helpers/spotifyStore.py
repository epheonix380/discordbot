from storage.models import Member
from asgiref.sync import sync_to_async

@sync_to_async
def getToken(uid):
    qs = Member.objects.filter(member_id=uid) 
    if (qs.count() > 0):
        token =  str(qs[0].spotify)
        if token == "":
            return "{}"
        return token
    else:
        return "{}"

@sync_to_async
def setToken(uid, token):
    member, created = Member.objects.update_or_create(member_id=uid,defaults={
        "spotify":token})
    return created
