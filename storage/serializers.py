from rest_framework import serializers
from .models import Member,MemberGymDay,MemberReminder, MemberTimeZoneMap, TimeZone, Item, GuildActivity, MemberGuildActivity, WeightedGuildActivity

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
        fields = ["id",'member',"reminder_text", "time", "frequency","isComplete", "target"]

class MemberGymDaySerializer(serializers.ModelSerializer):
    member = MemberSerializer(read_only=True)
    date = serializers.DateField(read_only=True)
    class Meta:
        model=MemberGymDay
        fields = ["member","date","isGym"]
