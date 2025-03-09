import discord
from helpers.mealPrepStore import getMemberMealPrepInGuild

# Status Check

async def statusCheck(message: discord.Message):
    guild_id = message.channel.guild_id
    member_id = message.author.id
    res = getMemberMealPrepInGuild(member_id=member_id, guild_id=guild_id)
    print(res)
    await message.channel.send("Hello")

# Subscribe
# Create
# Force