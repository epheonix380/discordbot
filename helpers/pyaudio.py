import io
import subprocess
import numpy as np
import discord


class DiscordReadableStream(discord.PCMAudio):

    def __init__(self, stream) -> None:
        super().__init__(stream)
    
    def read(self):
        return self.stream.stdout.read(n=3840)
 # init command
def record(vc: discord.VoiceClient):
    command = ["librespot", "-n","Librespot Speaker","-b","320","-B","pipe"]
    print("starting")
    # excute ffmpeg command
    pipe = subprocess.Popen(command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        bufsize=10**8)
    print("recording")
    # debug
    
    test = io.BufferedReader(pipe.stdout)
    source = discord.PCMAudio(stream=test)
    vc.play(source=source)
    
    # read signal as numpy array and assign sampling rate