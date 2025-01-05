import io
import subprocess
import discord
from asyncio import run, sleep
from dotenv import load_dotenv
import time
load_dotenv()
 # init command
def play(vc: discord.VoiceClient):

    ffmpegCommand = f'cd spotify && node src/app.js | ffmpeg -f webm -i pipe: -acodec pcm_s16le -ac 2 -ar 48000 -f s16le pipe:'
    ffmpegPipe = subprocess.Popen(ffmpegCommand,
                                  shell=True,
                                  stdout=subprocess.PIPE,
                                  bufsize=2097152) # 10 seconds of audio @1600kbit/s as buffer
    test = io.BufferedReader(ffmpegPipe.stdout)
    source = discord.PCMVolumeTransformer(discord.PCMAudio(stream=test))
    vc.play(source=source, after=lambda e: run(vc.disconnect()))
    return ffmpegPipe