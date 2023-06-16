from storage.models import Guild, GuildActivity, MemberGuildActivity, Member, WeightedGuildActivity
from storage.serializers import GuildActivitySerializer, MemberGuildActivitySerializer, WeightedGuildActivitySerializer
from asgiref.sync import sync_to_async
import datetime
from django.db import transaction
import xlsxwriter
import pathlib
import discord

@sync_to_async
def addGuildActivity(guild_id, message:discord.Message, is_nsfw):
    qs = Guild.objects.filter(guild_id=guild_id) 
    if (qs.count() > 0):
        guild = qs[0]
        date = datetime.datetime.now()
        word_count = len(message.content.split())
        [ga, isCreated] = GuildActivity.objects.get_or_create(guild=guild, date=date)
        [member, temp] = Member.objects.get_or_create(member_id=message.author.id)
        [gma, isGMACreated] = MemberGuildActivity.objects.get_or_create(guild=guild, member=member, date=date)
        with transaction.atomic():
            activity = ga.activity
            ga.activity = activity + 1
            gma.activity = gma.activity + 1
            ga.word_count = ga.word_count + word_count
            gma.word_count = gma.word_count + word_count
            ga.image_count = ga.image_count + len(message.attachments)
            gma.image_count = gma.image_count + len(message.attachments)
            if (is_nsfw > 0):
                ga.nsfw_count = ga.nsfw_count + is_nsfw
                gma.nsfw_count = gma.nsfw_count + is_nsfw
            ga.save()
            gma.save()
        wga = WeightedGuildActivity.objects.filter(guild=guild, channel_id=message.channel.id).order_by("-dateTime")
        if (wga.count() == 0):
            wga = WeightedGuildActivity(guild=guild, startingMessage=message.id,channel_id=message.channel.id, activity=1)
            wga.save()
        else:
            wga = wga[0]
            timeDelta = datetime.datetime.now(tz=datetime.timezone.utc) - wga.dateTime
            timeDelta = timeDelta.total_seconds()/60
            if (abs(timeDelta*5) > wga.activity):   
                if (wga.activity<40): 
                    wga.delete()
                wga = WeightedGuildActivity(guild=guild, startingMessage=message.id, activity=0, channel_id=message.channel.id)
            
            with transaction.atomic():
                wga.activity  = wga.activity + 1
                wga.save()
            

        return isCreated
    else:
        return None
    
@sync_to_async
def getGuildActivity(guild_id, message:discord.Message):
    qs = GuildActivity.objects.filter(guild__guild_id=guild_id).order_by("-date")
    serializer = GuildActivitySerializer(qs, many=True).data
    workbook = xlsxwriter.Workbook('GuildActivity.xlsx')
    worksheet = workbook.add_worksheet()
    row = 0
    worksheet.write_string(row, 0, "Date")
    worksheet.write_string(row, 1, "Messages Sent")
    worksheet.write_string(row, 2, "Words used")
    worksheet.write_string(row, 3, "Images Posted")
    worksheet.write_string(row, 4, "NSFW Images")
    for day in serializer:
        row+=1
        worksheet.write_string(row,0,str(day["date"]))
        worksheet.write_string(row,1,str(day["activity"]))
        worksheet.write_string(row,2,str(day["word_count"]))
        worksheet.write_string(row,3,str(day["image_count"]))
        worksheet.write_string(row,4,str(day["nsfw_count"]))
    workbook.close()
    return "GuildActivity.xlsx"

@sync_to_async
def getIndividualGuildID(guild_id, member_id,message:discord.Message):
    qs = MemberGuildActivity.objects.filter(guild__guild_id=guild_id, member__member_id=member_id).order_by("-date")
    serializer = MemberGuildActivitySerializer(qs, many=True).data
    workbook = xlsxwriter.Workbook('MemberActivity.xlsx')
    worksheet = workbook.add_worksheet()
    row = 0
    worksheet.write_string(row, 0, "Date")
    worksheet.write_string(row, 1, "Messages Sent")
    worksheet.write_string(row, 2, "Words used")
    worksheet.write_string(row, 3, "Images Posted")
    worksheet.write_string(row, 4, "NSFW Images")
    for day in serializer:
        row+=1
        worksheet.write_string(row,0,str(day["date"]))
        worksheet.write_string(row,1,str(day["activity"]))
        worksheet.write_string(row,2,str(day["word_count"]))
        worksheet.write_string(row,3,str(day["image_count"]))
        worksheet.write_string(row,4,str(day["nsfw_count"]))
    workbook.close()
    return "MemberActivity.xlsx"

@sync_to_async
def getEvents(guild_id, quantity):
    qs = WeightedGuildActivity.objects.filter(guild__guild_id=guild_id).order_by("-dateTime")[1:quantity+1]
    if (qs.count() > 0):
        data = WeightedGuildActivitySerializer(qs, many=True).data
        return data
    else:
        return None
    


    




    
    