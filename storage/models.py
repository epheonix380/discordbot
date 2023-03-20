from django.db import models
import pytz
TIMEZONES = tuple(zip(pytz.all_timezones, pytz.all_timezones))

# Create your models here.

class GuessTheHero(models.Model):
    guild_id = models.CharField(max_length=18)
    created_at = models.DateTimeField(auto_now_add=True)
    image_url = models.CharField(max_length=256)
    hero_name = models.CharField(max_length=64, default="")
    guessed = models.BooleanField(default=False)

class Guild(models.Model):
    guild_id = models.CharField(max_length=18, unique=True)
    guess_the_hero = models.CharField(max_length=24, null=True, blank=True, default=None)
    nsfw_channel = models.CharField(max_length=24, null=True, blank=True, default=None)

class TimeZone(models.Model):
    time_zone = models.CharField(max_length=32, choices=TIMEZONES)

class Member(models.Model):
    member_id = models.CharField(max_length=18, unique=True)
    time_zone = models.ForeignKey(TimeZone, on_delete=models.CASCADE, default=None, null=True)
    time_format = models.CharField(max_length=64, default="%H:%M on %d-%m-%Y")

class GuildMemberMap(models.Model):
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    
class MemberTimeZoneMap(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    time_zone = models.ForeignKey(TimeZone, on_delete=models.CASCADE)

class ListOfChoices(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    name = models.CharField(max_length=64, unique=True, null=True, default=None)
    last_used = models.DateTimeField(auto_now=True)

class Item(models.Model):
    list = models.ForeignKey(ListOfChoices, on_delete=models.CASCADE)
    name = models.CharField(max_length=128)

class BotIgnoreChannels(models.Model):
    channel_id = models.CharField(max_length=18, unique=True)
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE)