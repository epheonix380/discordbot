import discord
from asyncio import sleep
from helpers.audio import play
from helpers.spotifyStore import getToken, setToken

async def handlePlay(interaction: discord.Interaction):
    with open('spotify/.token.json', 'w') as file:
        token = await getToken(uid=interaction.user.id)
        file.write(str(token))
    if (interaction.user.voice is not None):
        vc = await interaction.user.voice.channel.connect()
        if (token == "{}"):
            await interaction.response.send_message("Please login at ", ephemeral=True)
        else:
            await interaction.response.send_message("Logged in", ephemeral=True)
        play(vc=vc, uid=interaction.user.id)
        breakout = False
        for i in range(3):
            if breakout:
                break
            else:
                await sleep(30)
                with open('spotify/.token.json', 'r') as file:
                    print("test\n\ntest\n\n")
                    print(file.read())
                    if len(file.read()) < 10:
                        continue
                    else:
                        await setToken(uid=interaction.user.id, token=file.read())
                        breakout = True
                        break
    else:
        await interaction.response.send_message("You aren't in a voice channel", ephemeral=True)