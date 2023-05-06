import io
import subprocess
import discord
import os
from dotenv import load_dotenv
import time
load_dotenv()
 # init command
def play(vc: discord.VoiceClient, USERNAME:str, PASSWORD:str):

    ffmpegCommand = f"librespot -b 320 -n Waifu --username {USERNAME} --password {PASSWORD} --disable-discovery --cache ./cache --system-cache ./systemCache -B pipe --passthrough | ffmpeg -i pipe: -ac 2 -ar 48000 -f s16le pipe:1"
    ffmpegPipe = subprocess.Popen(ffmpegCommand,
                                  shell=True,
                                  stdout=subprocess.PIPE,
                                  bufsize=10**8)
    test = io.BufferedReader(ffmpegPipe.stdout)
    time.sleep(5)
    source = discord.PCMVolumeTransformer(discord.PCMAudio(stream=test))
    vc.play(source=source)
    return ffmpegPipe
    # read signal as numpy array and assign sampling rate