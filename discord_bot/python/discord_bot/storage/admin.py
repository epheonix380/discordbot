from django.contrib import admin
from .models import Guild, Member, GuildMemberMap, TimeZone, MemberTimeZoneMap, BotIgnoreChannels

# Register your models here.
class GuildAdmin(admin.ModelAdmin):
    list_display = ('guild_id', 'nsfw_channel')

class MemberAdmin(admin.ModelAdmin):
    list_display = ('member_id', 'time_zone')

class GuildMemberMapAdmin(admin.ModelAdmin):
    list_display = ('guild', 'member')

class TimeZoneAdmin(admin.ModelAdmin):
    list_display = ('time_zone',)

class MemberTimeZoneMapAdmin(admin.ModelAdmin):
    list_display = ('member', 'time_zone')

class BotIgnoreChannelsAdmin(admin.ModelAdmin):
    list_display = ('channel_id', 'guild')

admin.site.register(Guild,GuildAdmin)
admin.site.register(Member,MemberAdmin)
admin.site.register(GuildMemberMap,GuildMemberMapAdmin)
admin.site.register(TimeZone,TimeZoneAdmin)
admin.site.register(MemberTimeZoneMap,MemberTimeZoneMapAdmin)
admin.site.register(BotIgnoreChannels,BotIgnoreChannelsAdmin)




