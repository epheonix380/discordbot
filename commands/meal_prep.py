import discord
import random
import datetime
from helpers.mealPrepStore import createForAllMembers, getMemberMealPrepInGuild, addMemberToGuildMealPrep, removeMemberFromGuildMealPrep, setGuildMealPrep

# Status Check

async def forceStatusCheck(guild_id, member_id, channel):
    res = await getMemberMealPrepInGuild(member_id=member_id, guild_id=guild_id)
    content = f"## For Meal Prep for <@{member_id}>:\n"
    mmpm = res["mmpm"]
    for i in range(min(len(mmpm), 5)):
        week = mmpm[i]
        dt = datetime.datetime.fromisoformat(week["week"])
        temp = f"""
        ### For week starting on date: <t:{str(dt.timestamp())[0:10]}:D>\n
            **Carb:** {week["carb"]}\n
            **Protein:** {week["protein"]}\n
            **Challenge:** {week["bad"]}\n
        \n\n
        """
        content+=temp
    await channel.send(content=content)

async def statusCheck(message: discord.Message):
    guild_id = message.guild.id
    member_id = message.author.id
    res = await getMemberMealPrepInGuild(member_id=member_id, guild_id=guild_id)
    content = f"## For Meal Prep for <@{message.author.id}>:\n"
    mmpm = res["mmpm"]
    for i in range(min(len(mmpm), 5)):
        week = mmpm[i]
        dt = datetime.datetime.fromisoformat(week["week"])
        temp = f"""
        ### For week starting on date: <t:{str(dt.timestamp())[0:10]}:D>\n
            **Carb:** {week["carb"]}\n
            **Protein:** {week["protein"]}\n
            **Challenge:** {week["bad"]}\n
        \n
        """
        content+=temp
    await message.channel.send(content)

# Subscribe

async def subscribeToMealPrep(message:discord.Message):
    guild_id = message.guild.id
    member_id = message.author.id
    res = await addMemberToGuildMealPrep(member_id=member_id, guild_id=guild_id)
    if res:
        await message.channel.send("Success")
    else:
        await message.channel.send("Failure")



async def unsubscribeFromMealPrep(message:discord.Message):
    guild_id = message.guild.id
    member_id = message.author.id
    res = await removeMemberFromGuildMealPrep(member_id=member_id, guild_id=guild_id)
    if res:
        await message.channel.send("Success")
    else:
        await message.channel.send("Failure")

# Create

async def createGuildMealPlan(message:discord.Message):
    guild_id = message.guild.id
    channel_id = message.channel.id
    res = await setGuildMealPrep(guild_id, channel_id)
    if res:
        await message.channel.send("Success")
    else:
        await message.channel.send("Failure")

# Force

async def doRoll(guild_id, context: discord.Client):
    used = [[],[],[]]
    def createFunc(week, retries, carb:str, protein:str, bad:str):
        main = [carb.split(","), protein.split(","), bad.split(",")]
        final = ["", "", ""]
        date = datetime.date.today()
        for i in range(3):
            mainSet = set(main[i])
            usedSet = set(used[i])
            unusedSet = mainSet - usedSet
            unusedList = list(unusedSet)
            choice = random.choice(unusedList)
            final[i] = choice
            used[i].append(choice)
        return [date, retries, final[0], final[1], final[2]]
    guild_id, channel_id, res = await createForAllMembers(guild_id=guild_id, createFunc=createFunc)
    if len(res) > 0:
        channel:discord.TextChannel = await context.fetch_channel(int(channel_id))
        for member in res:
            await forceStatusCheck(guild_id, member.member_id, channel=channel)
        return True
    else:
        return False

async def forceDoRoll(message: discord.Message, context: discord.Client):
    res = await doRoll(message.guild.id, context)
    if res:
        await message.channel.send("Success")
    else:
        await message.channel.send("Failure")