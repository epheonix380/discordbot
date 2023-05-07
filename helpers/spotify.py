import io
import subprocess
import discord
import os
from dotenv import load_dotenv
import time
load_dotenv()
 # init command
def play(vc: discord.VoiceClient, USERNAME:str, PASSWORD:str):

    ffmpegCommand = f'librespot -b 320 -n Waifu --username {USERNAME} --disable-discovery --cache ./cache --system-cache ./systemCache -B pipe --passthrough | ffmpeg -i pipe: -ac 2 -ar 48000 -f s16le pipe:1'
    ffmpegPipe = subprocess.Popen(ffmpegCommand,
                                  shell=True,
                                  stdout=subprocess.PIPE,
                                  bufsize=2097152) # 10 seconds of audio @1600kbit/s as buffer
    test = io.BufferedReader(ffmpegPipe.stdout)
    time.sleep(5) # 5 seconds of audio as buffer
    source = discord.PCMVolumeTransformer(discord.PCMAudio(stream=test))
    vc.play(source=source)
    return ffmpegPipe
    # read signal as numpy array and assign sampling rate