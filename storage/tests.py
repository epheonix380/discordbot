from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from storage.models import Guild, TimeZone, Member



# Create your tests here.

class GuildTestCase(TestCase):
    '''Class represents GuildTestCases'''
    def setUp(self):
        Guild.objects.create(guild_id="123456789123456789")# pylint: disable=maybe-no-member

    def test_guild_success_create(self):
        '''Takes in Object self, returns None'''
        guild = Guild.objects.create(guild_id="987654321987654321")# pylint: disable=maybe-no-member
        self.assertEqual(str(guild.guild_id), "987654321987654321")

    def test_guild_failure_create(self):
        '''Takes in Object self, returns None'''
        with self.assertRaises(IntegrityError):
            guild = Guild.objects.create(guild_id="123456789123456789")# pylint: disable=maybe-no-member
            Guild.full_clean(guild)

class TimeZoneTestCase(TestCase):
    '''Class represents TimeZoneTestCase'''
    def setUp(self):
        TimeZone.objects.create(time_zone="America/Vancouver")# pylint: disable=maybe-no-member

    def test_timezone_success_create(self):
        '''Takes in Object self, returns None'''
        time_zone = TimeZone.objects.create(time_zone="Asia/Bangkok")# pylint: disable=maybe-no-member
        self.assertEqual(str(time_zone.time_zone), "Asia/Bangkok")

    def test_timezone_failure_create(self):
        '''Takes in Object self, returns None'''
        time_zone = TimeZone.objects.create(time_zone="ClearlyWrong/ThisDoesntExist")# pylint: disable=maybe-no-member
        with self.assertRaises(ValidationError):
            TimeZone.full_clean(time_zone)

class MemberTestCase(TestCase):
    '''Class represents MemberTestCase'''
    def setUp(self):
        Member.objects.create(member_id="123456789123456789")# pylint: disable=maybe-no-member

    def test_member_success_create(self):
        '''Takes in Object self, returns None'''
        tz = Member.objects.create(member_id="987654321987654321")# pylint: disable=maybe-no-member
        self.assertEqual(str(tz.member_id), "987654321987654321")

    def test_member_failure_create(self):
        '''Takes in Object self, returns None'''
        with self.assertRaises(IntegrityError):
            tz = Member.objects.create(member_id="123456789123456789")# pylint: disable=maybe-no-member
            Member.full_clean(tz)