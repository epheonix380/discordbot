import io
import subprocess
import discord
from asyncio import run
from dotenv import load_dotenv
from .spotifyStore import setToken
load_dotenv()
 # init command

async def cleanUp(vc: discord.VoiceClient, uid:int, sub:subprocess.Popen):
    sub.terminate()
    with open('spotify/.token.json', 'r') as file:
        await setToken(uid=uid, token=file.read())
    print("Successfully Cleaned")
    try:
        await vc.disconnect()
    except:
        print("Already Disconnected")
    return True

def play(vc: discord.VoiceClient, uid:int):

    ffmpegCommand = f'cd spotify && node src/app.js | ffmpeg -f webm -i pipe: -acodec pcm_s16le -ac 2 -ar 48000 -f s16le pipe:'
    ffmpegPipe = subprocess.Popen(ffmpegCommand,
                                  shell=True,
                                  stdout=subprocess.PIPE,
                                  bufsize=2097152) # 10 seconds of audio @1600kbit/s as buffer
    test = io.BufferedReader(ffmpegPipe.stdout)
    source = discord.PCMVolumeTransformer(discord.PCMAudio(stream=test))
    vc.play(source=source, after=lambda e: run(cleanUp(vc=vc, uid=uid, sub=ffmpegPipe)))
    return ffmpegPipe