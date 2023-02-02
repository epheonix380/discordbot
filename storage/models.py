from django.db import models
import pytz
TIMEZONES = tuple(zip(pytz.all_timezones, pytz.all_timezones))

# Create your models here.

class Guild(models.Model):
    guild_id = models.CharField(max_length=18)
    nsfw_channel = models.CharField(max_length=18, null=True, blank=True)

class Member(models.Model):
    member_id = models.CharField(max_length=18)
    time_zone = models.CharField(max_length=32, choices=TIMEZONES)

class GuildMemberMap(models.Model):
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)

class TimeZone(models.Model):
    time_zone = models.CharField(max_length=32, choices=TIMEZONES)
    gmt_offset = models.IntegerField(default=0)
    
class MemberTimeZoneMap(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    time_zone = models.ForeignKey(TimeZone, on_delete=models.CASCADE)

class BotIgnoreChannels(models.Model):
    channel_id = models.CharField(max_length=18)
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE)