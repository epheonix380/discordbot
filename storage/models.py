from django.db import models
import pytz
TIMEZONES = tuple(zip(pytz.all_timezones, pytz.all_timezones))

# Create your models here.

class GuessTheHero(models.Model):
    guild_id = models.CharField(max_length=24)
    created_at = models.DateTimeField(auto_now_add=True)
    image_url = models.CharField(max_length=256)
    hero_name = models.CharField(max_length=64, default="")
    guessed = models.BooleanField(default=False)
    clue_count = models.IntegerField(default=0)
    guess_count = models.IntegerField(default=0)
    user_id = models.CharField(max_length=24, null=True, default=None)
    message_id = models.CharField(max_length=24, null=True, default=None)

class Guild(models.Model):
    guild_id = models.CharField(max_length=24, unique=True)
    guess_the_hero = models.CharField(max_length=24, null=True, blank=True, default=None)
    nsfw_channel = models.CharField(max_length=24, null=True, blank=True, default=None)

class GuildActivity(models.Model):
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    activity = models.IntegerField(default=0)
    word_count = models.IntegerField(default=0)
    image_count = models.IntegerField(default=0)
    nsfw_count = models.IntegerField(default=0)

class WeightedGuildActivity(models.Model):
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE)
    dateTime = models.DateTimeField(auto_now_add=True)
    activity = models.IntegerField(default=0)
    channel_id = models.CharField(max_length=32, default=None, null=True)
    startingMessage = models.CharField(max_length=32)
    endingMessage = models.CharField(max_length=32, default="")

class TimeZone(models.Model):
    time_zone = models.CharField(max_length=32, choices=TIMEZONES)

class Member(models.Model):
    member_id = models.CharField(max_length=24, unique=True)
    time_zone = models.ForeignKey(TimeZone, on_delete=models.CASCADE, default=None, null=True)
    time_format = models.CharField(max_length=64, default="%H:%M on %d-%m-%Y")

class MemberGuildActivity(models.Model):
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    date = models.DateField(auto_now=True)
    activity = models.IntegerField(default=0)
    word_count = models.IntegerField(default=0)
    image_count = models.IntegerField(default=0)
    nsfw_count = models.IntegerField(default=0)

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
    channel_id = models.CharField(max_length=24, unique=True)
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE)