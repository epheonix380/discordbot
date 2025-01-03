import io
import subprocess
import discord
import os
from dotenv import load_dotenv
import time
load_dotenv()
 # init command
def play(vc: discord.VoiceClient):

    ffmpegCommand = f'cd spotify && npm start | ffmpeg -re -i pipe:0 -ac 2 -ar 48000 -f s16le -acodec pcm_s16le pipe:1'
    ffmpegPipe = subprocess.Popen(ffmpegCommand,
                                  shell=True,
                                  stdout=subprocess.PIPE,
                                  bufsize=2097152) # 10 seconds of audio @1600kbit/s as buffer
    test = io.BufferedReader(ffmpegPipe.stdout)
    time.sleep(5) # 5 seconds of audio as buffer
    source = discord.PCMVolumeTransformer(discord.PCMAudio(stream=test))
    vc.play(source=source)
    return ffmpegPipe