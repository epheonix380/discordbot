from storage.models import TimeZone, Member, MemberTimeZoneMap
from asgiref.sync import sync_to_async

@sync_to_async
def getDefaultTimezone(uid):
    qs = Member.objects.filter(member_id=uid) 
    if (qs.count() > 0):
        return str(qs[0].time_zone.time_zone)
    else:
        return None

@sync_to_async
def setDefaultTimezone(uid, timezone):
    time_zone, timeCreate = TimeZone.objects.update_or_create(time_zone=str(timezone))
    member, created = Member.objects.update_or_create(member_id=uid,defaults={
        'time_zone':time_zone
    })
    return created
