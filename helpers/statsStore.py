from api_client import api_client
from asgiref.sync import sync_to_async
import datetime
import asyncio
import xlsxwriter
import pathlib
import discord

total_msg = 25

@sync_to_async
def addGuildActivity(guild_id, message:discord.Message, is_nsfw):
    async def _add_guild_activity():
        async with api_client as client:
            # Ensure guild exists
            await client.create_or_update_guild(str(guild_id), {})
            
            # Ensure member exists
            await client.create_or_update_member(str(message.author.id), {})
            
            # Prepare activity data
            date = datetime.datetime.now()
            word_count = len(message.content.split())
            
            activity_data = {
                'guild': guild_id,
                'date': date.isoformat(),
                'activity': 1,
                'word_count': word_count,
                'image_count': len(message.attachments),
                'nsfw_count': is_nsfw if is_nsfw > 0 else 0
            }
            
            # Add guild activity
            await client.add_guild_activity(str(guild_id), activity_data)
            
            # Add member guild activity
            member_activity_data = {
                'guild': guild_id,
                'member': str(message.author.id),
                'date': date.isoformat(),
                'activity': 1,
                'word_count': word_count,
                'image_count': len(message.attachments),
                'nsfw_count': is_nsfw if is_nsfw > 0 else 0
            }
            
            await client.add_member_guild_activity(member_activity_data)
            
            # Handle weighted guild activity
            weighted_data = {
                'guild': guild_id,
                'channel_id': str(message.channel.id),
                'startingMessage': str(message.id),
                'activity': 1
            }
            
            await client.create_weighted_activity(weighted_data)
            
            return True
    
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(_add_guild_activity())
    except RuntimeError:
        # No event loop running, create a new one
        return asyncio.run(_add_guild_activity())

@sync_to_async
def getGuildActivity(guild_id, message:discord.Message):
    async def _get_guild_activity():
        async with api_client as client:
            result = await client.get_guild_activities(str(guild_id))
            if 'error' in result:
                return None
            
            # Create Excel file
            workbook = xlsxwriter.Workbook('GuildActivity.xlsx')
            worksheet = workbook.add_worksheet()
            row = 0
            worksheet.write_string(row, 0, "Date")
            worksheet.write_string(row, 1, "Messages Sent")
            worksheet.write_string(row, 2, "Words used")
            worksheet.write_string(row, 3, "Images Posted")
            worksheet.write_string(row, 4, "NSFW Images")
            
            for day in result:
                row += 1
                arr = str(day["date"]).split('-')
                year = int(arr[0])
                month = int(arr[1])
                d = int(arr[2])
                worksheet.write_string(row, 0, f"{d}/{month}/{year}")
                worksheet.write_number(row, 1, day["activity"])
                worksheet.write_number(row, 2, day["word_count"])
                worksheet.write_number(row, 3, day["image_count"])
                worksheet.write_number(row, 4, day["nsfw_count"])
            
            workbook.close()
            return "GuildActivity.xlsx"
    
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(_get_guild_activity())
    except RuntimeError:
        # No event loop running, create a new one
        return asyncio.run(_get_guild_activity())

@sync_to_async
def getIndividualGuildID(guild_id, member_id, message:discord.Message):
    async def _get_individual_activity():
        async with api_client as client:
            result = await client.get_member_guild_activities(str(guild_id), str(member_id))
            if 'error' in result:
                return None
            
            # Create Excel file
            workbook = xlsxwriter.Workbook('MemberActivity.xlsx')
            worksheet = workbook.add_worksheet()
            row = 0
            worksheet.write_string(row, 0, "Date")
            worksheet.write_string(row, 1, "Messages Sent")
            worksheet.write_string(row, 2, "Words used")
            worksheet.write_string(row, 3, "Images Posted")
            worksheet.write_string(row, 4, "NSFW Images")
            
            for day in result:
                row += 1
                arr = str(day["date"]).split('-')
                year = int(arr[0])
                month = int(arr[1])
                d = int(arr[2])
                worksheet.write_string(row, 0, f"{d}/{month}/{year}")
                worksheet.write_number(row, 1, day["activity"])
                worksheet.write_number(row, 2, day["word_count"])
                worksheet.write_number(row, 3, day["image_count"])
                worksheet.write_number(row, 4, day["nsfw_count"])
            
            workbook.close()
            return "MemberActivity.xlsx"
    
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(_get_individual_activity())
    except RuntimeError:
        # No event loop running, create a new one
        return asyncio.run(_get_individual_activity())

@sync_to_async
def getEvents(guild_id, quantity):
    async def _get_events():
        async with api_client as client:
            result = await client.get_weighted_activities(str(guild_id), total_msg)
            if 'error' in result:
                return None
            
            # Limit to requested quantity
            return result[:quantity] if result else None
    
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(_get_events())
    except RuntimeError:
        # No event loop running, create a new one
        return asyncio.run(_get_events())


    
    