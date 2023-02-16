from rest_framework import serializers
from .models import MemberTimeZoneMap, TimeZone

class TimezoneSerializer(serializers.ModelSerializer):
    '''Class represents TimezoneSerializer'''
    class Meta: # pylint: disable=too-few-public-methods
        '''Class represents Meta'''
        model = TimeZone
        fields = ['time_zone']

class TimeMapSerializer(serializers.ModelSerializer):
    '''Class represents TimezoneSerializer'''
    time_zone = serializers.SerializerMethodField()
    class Meta: # pylint: disable=too-few-public-methods
        '''Class represents Meta'''
        model = MemberTimeZoneMap
        fields = ['time_zone']
    def get_time_zone(self, obj):
        '''Takes in Object self and Object obj, returns None'''
        return str(obj.time_zone.time_zone)
