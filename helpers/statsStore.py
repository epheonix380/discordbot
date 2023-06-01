from storage.models import Guild, GuildActivity
from storage.serializers import GuildActivitySerializer
from asgiref.sync import sync_to_async
import datetime
from django.db import transaction
import xlsxwriter
import pathlib
import discord

@sync_to_async
def addGuildActivity(guild_id):
    qs = Guild.objects.filter(guild_id=guild_id) 
    if (qs.count() > 0):
        guild = qs[0]
        date = datetime.datetime.now()
        with transaction.atomic():
            [ga, isCreated] = GuildActivity.objects.get_or_create(guild=guild, date=date)
            activity = ga.activity
            ga.activity = activity + 1
            ga.save() 
        return isCreated
    else:
        return None
    
@sync_to_async
def getGuildActivity(guild_id, message:discord.Message):
    qs = GuildActivity.objects.filter(guild__guild_id=guild_id).order_by("date")
    serializer = GuildActivitySerializer(qs, many=True).data
    workbook = xlsxwriter.Workbook('GuildActivity.xlsx')
    worksheet = workbook.add_worksheet()
    row = 0
    worksheet.write_string(row, 0, "Date")
    worksheet.write_string(row, 1, "Messages Sent")
    for day in serializer:
        row+=1
        worksheet.write_string(row,0,str(day["date"]))
        worksheet.write_string(row,1,str(day["activity"]))
    workbook.close()
    return "GuildActivity.xlsx"
    




    
    