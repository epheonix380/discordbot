import discord
import os
from dotenv import load_dotenv
import time
from helpers.credentialsStore import getSpotifyUsernameAndToken
from helpers.spotify import play
from urllib.parse import urlencode
load_dotenv()

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
URL = os.getenv("CLIENT_URL")

async def handlePlay(interaction:discord.Interaction):
    credentials = await getSpotifyUsernameAndToken(interaction.user.id)
    if (credentials["username"] != "" and credentials["token"] != ""):
        if (interaction.user.voice is not None):
            vc = await interaction.user.voice.channel.connect()
            play(vc=vc, USERNAME=credentials["username"], PASSWORD=credentials["token"])
            await interaction.response.send_message("Joined", ephemeral=True)
        else:
            await interaction.response.send_message("You aren't in a voice channel", ephemeral=True)
    else:
        state = interaction.user.id
        redirect_url = f"{URL}utils/callback"
        scope = 'streaming user-read-private user-read-email'
        query = {
            "response_type": 'code',
            "client_id": CLIENT_ID,
            "scope": scope,
            "redirect_uri": redirect_url,
            "state": state
            }
        end = urlencode(query=query)
        await interaction.response.send_message(f"Visit this link to login: https://accounts.spotify.com/authorize?{end}", ephemeral=True)
        

