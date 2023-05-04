import io
import subprocess
import discord
import os
from dotenv import load_dotenv
load_dotenv()
USERNAME = os.getenv("SPOTIFY_USERNAME")
PASSWORD = os.getenv("SPOTIFY_PASSWORD")
 # init command
def play(vc: discord.VoiceClient, message: discord.Message):
    instruction = str(message.content).strip().split(" ")
    command = ["target/release/librespot", "-n","Nyan's Waifu","-b","320","-B","pipe","--username",USERNAME,"--password",PASSWORD,"--disable-discovery","--cache","./cache","--system-cache","./systemCache"]
    print("starting")
    # excute ffmpeg command
    pipe = subprocess.Popen(command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        bufsize=10**8)
    print("recording")
    # debug
    
    test = io.BufferedReader(pipe.stdout)
    source = None
    if (instruction[1]=="ff"):
        source = discord.FFmpegPCMAudio(source=test,pipe=True,before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5")
    else:
        source = discord.PCMAudio(stream=test)
    vc.play(source=source)
    
    # read signal as numpy array and assign sampling rate