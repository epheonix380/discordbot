import io
import subprocess
import numpy as np
import discord
import os
from dotenv import load_dotenv
load_dotenv()
USERNAME = os.getenv("SPOTIFY_USERNAME")
PASSWORD = os.getenv("SPOTIFY_PASSWORD")

class DiscordReadableStream(discord.PCMAudio):

    def __init__(self, stream) -> None:
        super().__init__(stream)
    
    def read(self):
        return self.stream.stdout.read(n=3840)
 # init command
def record(vc: discord.VoiceClient):
    command = ["librespot", "-n","Nyan's Waifu","-b","320","-B","pipe","--username",USERNAME,"--password",PASSWORD]
    print("starting")
    # excute ffmpeg command
    pipe = subprocess.Popen(command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        bufsize=10**8)
    print("recording")
    # debug
    
    test = io.BufferedReader(pipe.stdout)
    source = discord.FFmpegPCMAudio(source=test,pipe=True,before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", options="-ar 48000")
    vc.play(source=source)
    
    # read signal as numpy array and assign sampling rate