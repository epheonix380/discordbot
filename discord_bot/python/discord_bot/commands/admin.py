from helpers.guildStore import getNSFWChannel, setNSFWChannel, getGuessTheHeroChannel, setGuessTheHeroChannel


async def admin(message):
    instruction = str(message.content).strip().split(" ")
    if (instruction[1] == "nsfw"):
        if (len(instruction)==2):
            default = await getNSFWChannel(message.guild.id)
            if default is None:
                default = "No nsfw channel found, please use ,admin nsfw <channel id> to set the channel"
            await message.channel.send(default)
        else:
            channelID = instruction[2]
            await setNSFWChannel(message.guild.id, channelID) 
    if (instruction[1] == "guessTheHero"):
        if (len(instruction)==2):
            default = await getGuessTheHeroChannel(message.guild.id)
            if default is None:
                default = "No guessTheHero channel found, please use ,admin guessTheHero <channel id> to set the channel"
            await message.channel.send(default)
        else:
            channelID = instruction[2]
            await setGuessTheHeroChannel(message.guild.id, channelID) 