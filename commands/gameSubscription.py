from discord import Message, Client
import discord
from helpers.gamesStore import getOrCreate, updateCurrentVersion, getAllGames, getAllChannelsForGame
import requests
import time

def fetch(appid):
    res = requests.get(f"https://api.steamcmd.net/v1/info/{appid}")
    if (res.status_code == 200):
        test = res.json()
        return test
    else:
        print("here3")
        return None


async def subscribe(message: Message):
    commands = message.content.split(" ")
    if (len(commands) == 2):
        await message.channel.send("We got your request, we are working on it!")
        appID = commands[1]
        game, wasCreated = await getOrCreate(appid=appID, channelid=message.channel.id, guildid=message.guild.id)
        if (wasCreated):
            res = fetch(appid=appID)
            if (res is not None):
                buildid = res["data"][appID]["depots"]["branches"]["public"]["buildid"]
                gameName = res["data"][appID]["common"]["name"]
                await updateCurrentVersion(appid=appID, version=buildid, name=gameName)
                await message.channel.send(f"Successfully subscribed to game {gameName} , latest build id was {buildid}")
            else:
                await message.channel.send("Something bad happened")
        else:
            await message.channel.send(f"Successfully subscribed to game {game['name']} , latest build id was {game['version']}")
    else:
        await message.channel.send("Malformed message, please use ,subscribe appid")

async def checkGameVersions(client: Client):
    games = await getAllGames()
    time.sleep(0)
    for game in games:
        time.sleep(0)
        appid = game["appid"]
        if appid is not None and appid != "":
            time.sleep(0)
            res = fetch(appid=appid)
            time.sleep(0)
            buildid = res["data"][appid]["depots"]["branches"]["public"]["buildid"]
            if game["version"] != buildid:
                time.sleep(0)
                await updateCurrentVersion(appid=appid, version=buildid)
                channels = await getAllChannelsForGame(appid=appid)
                for channel in channels:
                    time.sleep(0)
                    channel_id = channel["channel"]["channel_id"]
                    guild_id = channel["channel"]["guild"]
                    guild: discord.Guild = await client.fetch_guild(guild_id)
                    textChannel: discord.TextChannel = await guild.fetch_channel(channel_id)
                    await textChannel.send(
                        f"New Game Update for game {game['name']}, with build number {buildid}"
                    )


