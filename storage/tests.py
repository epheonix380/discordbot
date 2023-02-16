from django.test import TestCase
from storage.models import Guild, TimeZone, Member, GuildMemberMap, MemberTimeZoneMap, BotIgnoreChannels
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

# Create your tests here.

class GuildTestCase(TestCase):
    def setUp(self):
        Guild.objects.create(guild_id="123456789123456789")

    def test_guild_success_create(self):
        tz = Guild.objects.create(guild_id="987654321987654321")
        self.assertEqual(str(tz.guild_id), "987654321987654321")

    def test_guild_failure_create(self):
        with self.assertRaises(IntegrityError):
            tz = Guild.objects.create(guild_id="123456789123456789")
            Guild.full_clean(tz)

class TimeZoneTestCase(TestCase):
    def setUp(self):
        TimeZone.objects.create(time_zone="America/Vancouver")

    def test_timezone_success_create(self):
        tz = TimeZone.objects.create(time_zone="Asia/Bangkok")
        self.assertEqual(str(tz.time_zone), "Asia/Bangkok")

    def test_timezone_failure_create(self):
        tz = TimeZone.objects.create(time_zone="ClearlyWrong/ThisDoesntExist")
        with self.assertRaises(ValidationError):
            TimeZone.full_clean(tz)

class MemberTestCase(TestCase):
    def setUp(self):
        Member.objects.create(member_id="123456789123456789")

    def test_member_success_create(self):
        tz = Member.objects.create(member_id="987654321987654321")
        self.assertEqual(str(tz.member_id), "987654321987654321")

    def test_member_failure_create(self):
        with self.assertRaises(IntegrityError):
            tz = Member.objects.create(member_id="123456789123456789")
            Member.full_clean(tz)