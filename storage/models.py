from django.db import models
import pytz
TIMEZONES = tuple(zip(pytz.all_timezones, pytz.all_timezones))

# Create your models here.

class Guild(models.Model):
    '''Class represents Guild'''

    guild_id = models.CharField(max_length=18, unique=True)
    nsfw_channel = models.CharField(max_length=18, null=True, blank=True, default=None)


class TimeZone(models.Model):
    '''Class represents TimeZone'''

    time_zone = models.CharField(max_length=32, choices=TIMEZONES)

class Member(models.Model):
    '''Class represents Member'''

    member_id = models.CharField(max_length=18, unique=True)
    time_zone = models.ForeignKey(TimeZone, on_delete=models.CASCADE, default=None, null=True)
    time_format = models.CharField(max_length=64, default="%H:%M on %d-%m-%Y")


class GuildMemberMap(models.Model):
    '''Class represents GuildMemberMap'''

    guild = models.ForeignKey(Guild, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)


class MemberTimeZoneMap(models.Model):
    '''Class represents MemberTimeZoneMap'''

    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    time_zone = models.ForeignKey(TimeZone, on_delete=models.CASCADE)

class BotIgnoreChannels(models.Model):
    '''Class represents BotIgnoreChannels'''
    
    channel_id = models.CharField(max_length=18, unique=True)
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE)