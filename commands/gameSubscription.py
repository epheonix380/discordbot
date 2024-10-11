from discord import Message, Client, Thread
import discord
from helpers.gamesStore import getOrCreate, updateCurrentVersion, getAllGames, getAllChannelsForGame
import requests
import time
import re
import asyncio

def fetchPatchNotes(appid):
    res = requests.get(f"https://store.steampowered.com/events/ajaxgetadjacentpartnerevents/?appid={appid}&count_before=0&count_after=1")
    if (res.status_code == 200):
        test = res.json()
        return test
    else:
        return None

def fetchGameVersionAndName(appid):
    res = requests.get(f"https://api.steamcmd.net/v1/info/{appid}")
    if (res.status_code == 200):
        test = res.json()
        return test
    else:
        return None


async def subscribe(message: Message):
    commands = message.content.split(" ")
    if (len(commands) == 2):
        await message.channel.send("We got your request, we are working on it!")
        appID = commands[1]
        game, wasCreated = await getOrCreate(appid=appID, channelid=message.channel.id, guildid=message.guild.id)
        if (wasCreated):
            res = fetchGameVersionAndName(appid=appID)
            patch = fetchPatchNotes(appid=appID)
            if (res is not None and patch is not None and patch['success'] == 1):
                buildid = res["data"][appID]["depots"]["branches"]["public"]["buildid"]
                gameName = res["data"][appID]["common"]["name"]
                patchVersion = patch['events'][0]['gid']
                await updateCurrentVersion(appid=appID, version=buildid, name=gameName, patchVersion=patchVersion)
                await message.channel.send(f"Successfully subscribed to game {gameName} , latest build id was {buildid}")
            else:
                await message.channel.send("Something bad happened")
        else:
            await message.channel.send(f"Successfully subscribed to game {game['name']} , latest build id was {game['version']}")
    else:
        await message.channel.send("Malformed message, please use ,subscribe appid")

async def checkGameVersions(client: Client):
    games = await getAllGames()
    await asyncio.sleep(0)
    for game in games:
        await asyncio.sleep(0)
        print(f"Start with game: {game['name']}")
        appid = game["appid"]
        if appid is not None and appid != "":
            await asyncio.sleep(0)
            res = fetchGameVersionAndName(appid=appid)
            await asyncio.sleep(0)
            patch = fetchPatchNotes(appid=appid)
            await asyncio.sleep(0)
            patchNoteData = None
            patchNotes = ""
            if (patch is not None and patch['success'] == 1):
                patchNoteData = patch['events'][0]['gid']
                patchNotes = f"{patch['events'][0]['event_name']}\n\n{patch['events'][0]['announcement_body']['body']}"
            await asyncio.sleep(0)
            buildid = None
            if (res is not None and
                "data" in res and
                appid in res["data"] and
                "depots" in res["data"][appid] and
                "branches" in res["data"][appid]["depots"] and 
                "public" in res["data"][appid]["depots"]["branches"] and
                "buildid" in res["data"][appid]["depots"]["branches"]["public"]):
                buildid = res["data"][appid]["depots"]["branches"]["public"]["buildid"]
            if (buildid is not None and game["version"] != buildid) or (patchNoteData is not None and game['patchVersion'] != patchNoteData):
                await asyncio.sleep(0)
                await updateCurrentVersion(appid=appid, version=buildid, patchVersion=patchNoteData)
                await asyncio.sleep(0)
                channels = await getAllChannelsForGame(appid=appid)
                await asyncio.sleep(0)
                for channel in channels:
                    await asyncio.sleep(0)
                    channel_id = channel["channel"]["channel_id"]
                    guild_id = channel["channel"]["guild"]
                    guild: discord.Guild = await client.fetch_guild(guild_id)
                    textChannel: discord.TextChannel = await guild.fetch_channel(channel_id)
                    sentMessage: Message = await textChannel.send(
                        f"New Game Update for game {game['name']}, with build number {buildid}"
                    )
                    if (patchNoteData is not None and game['patchVersion'] != patchNoteData):
                        await asyncio.sleep(0)
                        def urlFunction(matchobj: re.Match):
                            matchStr:str = matchobj.group(0)
                            if matchStr is not None and matchStr != "":
                                formattedStr:str = matchStr[5:-6]
                                url = formattedStr.split("]")[0]
                                text = formattedStr.split("]")[1]
                                return f"[{text}]({url})"
                            else:
                                return ""
                        def imgFunction(matchobj: re.Match):
                            return ""
                        if (patchNotes != ""):
                            await asyncio.sleep(0)
                            patchNotes = patchNotes.replace(
                                    "[b]", "*"
                                ).replace(
                                    "[/b]", "*"
                                ).replace(
                                    "[i]", "**"
                                ).replace(
                                    "[/i]", "**"
                                )
                            await asyncio.sleep(0)
                            patchNotes = re.sub(
                                "\[url=[\s\S]+?\[\/url\]",
                                urlFunction,
                                patchNotes
                            )
                            await asyncio.sleep(0)
                            patchNotes = re.sub(
                                "\[img\][\s\S]+?\[\/img\]",
                                imgFunction,
                                patchNotes
                            )
                        await asyncio.sleep(0)
                        patchLength = len(patchNotes)
                        thread: Thread = await sentMessage.create_thread(name=f"Patch Notes for Game: {game['name']} with buildId: {buildid}")
                        await asyncio.sleep(0)
                        while patchLength != 0:
                            if (patchLength < 1999):
                                chunk = patchNotes
                            else: 
                                chunk = patchNotes[0:1999]
                            patchNotes = patchNotes[1999::]
                            patchLength = len(patchNotes)
                            await thread.send(chunk)
                            await asyncio.sleep(0)

