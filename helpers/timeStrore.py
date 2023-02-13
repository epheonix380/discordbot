from storage.models import TimeZone, Member, MemberTimeZoneMap
from asgiref.sync import sync_to_async
from storage.serializers import TimeMapSerializer

@sync_to_async
def getFormat(uid):
    qs = Member.objects.filter(member_id=uid) 
    if (qs.count() > 0):
        return str(qs[0].time_format)
    else:
        return "%H:%M on %d-%m-%Y"

@sync_to_async
def setFormat(uid, time_format):
    member, created = Member.objects.update_or_create(member_id=uid,defaults={
        "time_format":time_format})
    return created

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

@sync_to_async
def addTimezone(uid, timezone):
    member, memberCreated = Member.objects.get_or_create(member_id=uid)
    time_zone, timeCreated = TimeZone.objects.update_or_create(time_zone=str(timezone))
    timeMap, timeMapCreated = MemberTimeZoneMap.objects.update_or_create(member=member, time_zone=time_zone)
    return timeMapCreated

@sync_to_async
def removeTimezone(uid, timezone):
    time_zone, timeCreated = TimeZone.objects.update_or_create(time_zone=str(timezone))
    member, memberCreated = Member.objects.get_or_create(member_id=uid)
    qs = MemberTimeZoneMap.objects.filter(member=member, time_zone=time_zone)
    if (qs.count()>0):
        qs[0].delete()
        return True
    return False

@sync_to_async
def getTimezones(uid):
    member, memberCreated = Member.objects.get_or_create(member_id=uid)
    qs = MemberTimeZoneMap.objects.filter(member=member)
    data = TimeMapSerializer(qs,many=True).data
    return data
    
