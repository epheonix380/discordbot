from rest_framework import serializers
from .models import MemberTimeZoneMap, TimeZone, Item

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