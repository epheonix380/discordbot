from storage.models import TimeZone, Member, MemberTimeZoneMap
from asgiref.sync import sync_to_async
from storage.serializers import TimeMapSerializer

@sync_to_async
def getFormat(uid):# pylint: disable=missing-function-docstring
    qs = Member.objects.filter(member_id=uid) # pylint: disable=maybe-no-member
    if (qs.count() > 0):
        return str(qs[0].time_format)
    else:
        return "%H:%M on %d-%m-%Y"

@sync_to_async
def setFormat(uid, time_format):# pylint: disable=missing-function-docstring
    member, created = Member.objects.update_or_create(member_id=uid,defaults={# pylint: disable=maybe-no-member
        "time_format":time_format})
    print(member)
    return created

@sync_to_async
def getDefaultTimezone(uid):# pylint: disable=missing-function-docstring
    qs = Member.objects.filter(member_id=uid) # pylint: disable=maybe-no-member
    if (qs.count() > 0):
        return str(qs[0].time_zone.time_zone)
    else:
        return None

@sync_to_async
def setDefaultTimezone(uid, timezone):# pylint: disable=missing-function-docstring
    time_zone, timeCreate = TimeZone.objects.update_or_create(time_zone=str(timezone))# pylint: disable=maybe-no-member
    member, created = Member.objects.update_or_create(member_id=uid,defaults={# pylint: disable=maybe-no-member
        'time_zone':time_zone
    })
    return created

@sync_to_async
def addTimezone(uid, timezone):# pylint: disable=missing-function-docstring
    member, memberCreated = Member.objects.get_or_create(member_id=uid)# pylint: disable=maybe-no-member
    time_zone, timeCreated = TimeZone.objects.update_or_create(time_zone=str(timezone))# pylint: disable=maybe-no-member
    timeMap, timeMapCreated = MemberTimeZoneMap.objects.update_or_create(member=member, time_zone=time_zone)# pylint: disable=maybe-no-member
    return timeMapCreated

@sync_to_async
def removeTimezone(uid, timezone):# pylint: disable=missing-function-docstring
    time_zone, timeCreated = TimeZone.objects.update_or_create(time_zone=str(timezone))# pylint: disable=maybe-no-member
    member, memberCreated = Member.objects.get_or_create(member_id=uid)# pylint: disable=maybe-no-member
    qs = MemberTimeZoneMap.objects.filter(member=member, time_zone=time_zone)# pylint: disable=maybe-no-member
    if (qs.count()>0):
        qs[0].delete()
        return True
    return False

@sync_to_async
def getTimezones(uid):# pylint: disable=missing-function-docstring
    member, memberCreated = Member.objects.get_or_create(member_id=uid)# pylint: disable=maybe-no-member
    qs = MemberTimeZoneMap.objects.filter(member=member)# pylint: disable=maybe-no-member
    data = TimeMapSerializer(qs,many=True).data
    return data
    
