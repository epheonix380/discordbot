import discord
import random
from helpers.mealPrepStore import createForAllMembers, getMemberMealPrepInGuild, addMemberToGuildMealPrep, removeMemberFromGuildMealPrep, setGuildMealPrep

# Status Check

async def statusCheck(message: discord.Message):
    guild_id = message.channel.guild_id
    member_id = message.author.id
    res = await getMemberMealPrepInGuild(member_id=member_id, guild_id=guild_id)
    print(res)
    await message.channel.send("Hello")

# Subscribe

async def subscribeToMealPrep(message:discord.Message):
    guild_id = message.channel.guild_id
    member_id = message.author.id
    res = await addMemberToGuildMealPrep(member_id=member_id, guild_id=guild_id)
    if res:
        await message.channel.send("Success")
    else:
        await message.channel.send("Failure")



async def unsubscribeFromMealPrep(message:discord.Message):
    guild_id = message.channel.guild_id
    member_id = message.author.id
    res = await removeMemberFromGuildMealPrep(member_id=member_id, guild_id=guild_id)
    if res:
        await message.channel.send("Success")
    else:
        await message.channel.send("Failure")

# Create

async def createGuildMealPlan(message:discord.Message):
    guild_id = message.channel.guild_id
    channel_id = message.channel.id
    res = await setGuildMealPrep(guild_id, channel_id)
    if res:
        await message.channel.send("Success")
    else:
        await message.channel.send("Failure")

# Force

async def doRoll(guild_id):
    used_carb = []
    used_protein = []
    used_bad = []
    def createFunc(week, retries, carb, protein, bad):
        main = [carb, protein, bad]
        used = [used_carb, used_protein, used_bad]
        final = ["", "", ""]
        for i in range(3):
            mainSet = set(main[i])
            usedSet = set(used[i])
            unusedSet = mainSet - usedSet
            unusedList = list(unusedSet)
            choice = random.choice(unusedList)
            final[i] = choice
            used.append(choice)
        return [week, retries, final[0], final[1], final[2]]
    res = await createForAllMembers(guild_id=guild_id, createFunc=createFunc)
    return res

async def forceDoRoll(message: discord.Message):
    res = await doRoll(message.guild.id)
    if res:
        await message.channel.send("Success")
    else:
        await message.channel.send("Failure")