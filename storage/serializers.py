from rest_framework import serializers
from .models import Channel,GameVersionSubscriptions,GameVersion,Member,MemberGymDay,MemberReminder, MemberTimeZoneMap, TimeZone, Item, GuildActivity, MemberGuildActivity, WeightedGuildActivity, SpotifyToken, Guild, GuessTheHero, ListOfChoices, BotIgnoreChannels, MemberPlaylist, PlaylistElement, ComplexFrequecy, MemberGymDay

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ['name']

class TimezoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeZone
        fields = ['time_zone']

class TimeMapSerializer(serializers.ModelSerializer):
    time_zone = serializers.SerializerMethodField()
    class Meta:
        model = MemberTimeZoneMap
        fields = ['time_zone']
    def get_time_zone(self, obj):
        return str(obj.time_zone.time_zone)
    
class GameSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameVersion
        fields = '__all__'


class GuildActivitySerializer(serializers.ModelSerializer):

    class Meta:
        model = GuildActivity
        fields = '__all__'

class MemberGuildActivitySerializer(serializers.ModelSerializer):

    class Meta:
        model = MemberGuildActivity
        fields = '__all__'

class WeightedGuildActivitySerializer(serializers.ModelSerializer):
    dateTime = serializers.SerializerMethodField()
    def get_dateTime(self, obj):
        return obj.dateTime

    class Meta:
        model = WeightedGuildActivity
        fields = ['dateTime','channel_id','startingMessage']
        
class MemberSerializer(serializers.ModelSerializer):
    time_zone= serializers.SlugRelatedField(slug_field="time_zone", read_only=True)
    class Meta:
        model=Member
        fields = ['member_id',"isGym", "gymCheckinTime", "lastGymCheckinDate","time_zone"]

class MemberReminderSerializer(serializers.ModelSerializer):
    member = MemberSerializer(read_only=True)
    time = serializers.DateTimeField
    frequency = serializers.DurationField
    class Meta:
        model=MemberReminder
        fields = "__all__"

class MemberGymDaySerializer(serializers.ModelSerializer):
    member = MemberSerializer(read_only=True)
    date = serializers.DateField(read_only=True)
    class Meta:
        model=MemberGymDay
        fields = ["member","date","isGym"]

class ChannelSerializer(serializers.ModelSerializer):
    guild = serializers.SlugRelatedField(slug_field="guild_id", read_only=True)
    class Meta:
        model = Channel
        fields = ["channel_id", "guild"]

class GameSubscriptionSerializer(serializers.ModelSerializer):
    game = GameSerializer(read_only=True)
    channel = ChannelSerializer(read_only=True)
    class Meta:
        model = GameVersionSubscriptions
        fields = ['game', 'channel']

class SpotifyTokenSerializer(serializers.ModelSerializer):
    member = MemberSerializer(read_only=True)
    class Meta:
        model = SpotifyToken
        fields = ['member', 'access_token', 'refresh_token', 'expires_at', 'scope', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class GuildSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guild
        fields = ['guild_id', 'guess_the_hero', 'nsfw_channel']

class GuessTheHeroSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuessTheHero
        fields = '__all__'

class ListOfChoicesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListOfChoices
        fields = '__all__'

class BotIgnoreChannelsSerializer(serializers.ModelSerializer):
    guild = GuildSerializer(read_only=True)
    class Meta:
        model = BotIgnoreChannels
        fields = ['channel_id', 'guild']

class MemberPlaylistSerializer(serializers.ModelSerializer):
    member = MemberSerializer(read_only=True)
    class Meta:
        model = MemberPlaylist
        fields = '__all__'

class PlaylistElementSerializer(serializers.ModelSerializer):
    playlist_id = MemberPlaylistSerializer(read_only=True)
    class Meta:
        model = PlaylistElement
        fields = '__all__'

class ComplexFrequecySerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplexFrequecy
        fields = '__all__'
