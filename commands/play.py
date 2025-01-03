import discord
from helpers.audio import play

async def handlePlay(interaction: discord.Interaction):
    if (interaction.user.voice is not None):
        vc = await interaction.user.voice.channel.connect()
        await interaction.response.send_message("Joined", ephemeral=True)
        play(vc=vc)
    else:
        await interaction.response.send_message("You aren't in a voice channel", ephemeral=True)