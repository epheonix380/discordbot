import discord

async def helpHandler(message:discord.Message):
    instructions = message.content.split(" ")
    if (len(instructions) > 1):
        if (instructions[1] == "nsfw"):
            await message.channel.send("""
                You can use ```,nsfw``` by replying to a message with it. That message will then be turned into an nsfw message.
            """)
        elif (instructions[1] == "time"):
            await message.channel.send("""
            ```,time``` in order to get the current time in your 
            ```,time add [CITY NAME]``` to add a timezone to your list. This list is associate to your discord profile and will follow you to any server!
            ```,time remove [CITY NAME]``` to remove a timezone from your list
            ```,time format [FORMAT]``` to use a custom time format. You can do ,time format to get more information about formattingn
            ```,time @user``` to get the current time for the user. Please note that this only works if the user has set a DEFAUT_TIMEZONE
            ```,time default [CITY NAME]``` to register your default timezone, this can always be changed later
            ```,time [CITY NAME]``` to get the current time in the specified city
            ```,time convert [CITY_1_NAME] [TIME] to [CITY_2_NAME]``` to convert a time in city 1 to a time in city 2. Time needs to be in format hh:mm
            ```,time convert [TIME] to [CITY_NAME]``` to convert time in your default timezone to time in city
            """)
        elif (instructions[1] == "admin"):
            await message.channel.send("""
            ```,admin nsfw [CHANNEL]``` to set the nsfw channel of the server
            ```,admin guessTheHero [Channel]``` to set the guess the hero channel of the server
            """)
        elif (instructions[1] == "activity"):
            await message.channel.send("""
            ```,activity``` get the activity on this server
            ```,admin @user``` get the activity of user on this server
            """)
    else:
        await message.channel.send("""
        Welcome to Big Tiddy goth GF
        Here are our commands do ,help [command] for more specific command help\n
        NSFW: Hides any nsfw image/text/video/gif:
        ,nsfw\n
        TIME: Time related command do ,help time for more info
        ,time\n
        CHOOSE: Let the bot randomoly decide between a few options, seperate options with commas
        ,choose\n
        ADMIN: Admin commands that help with Guess The Hero and NSFW Channels do ,help admin for more details
        ,admin\n
        SERVER STATS: These command shows server stats for individuals and the server as a whole. Use ,help activity for more info
        ,activity\n
        """)
    await message.delete()