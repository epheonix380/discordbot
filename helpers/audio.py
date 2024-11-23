import discord
import os
import io
import time
import subprocess

# Specify the path and name of the named pipe
pipe_path = "./spotify-headless-client/WPIPE"


class Test(io.RawIOBase):

    # The following methods can return None if the file is in non-blocking mode
    # and no data is available.
    def read(self, size: int = -1, /) -> bytes:
       with open(pipe_path, 'rb') as f:
          return f.read(size)

   

# Read data from the named pipe

def play(vc: discord.VoiceClient):
    # Create "named pipes".
    
    # Open FFmpeg as sub-process
    # Use two audio input streams:
    # 1. Named pipe: "audio_pipe1"
    # 2. Named pipe: "audio_pipe2"
    # Merge the two audio streams using amix audio filter.
    # Store the result to output file: output.mp3
    pipe = Test()
    #test = io.BufferedReader(pipe)
     # 5 seconds of audio as buffer
    test = io.open(pipe_path, "rb") #io.BufferedReader(pipe)
    source = discord.PCMVolumeTransformer(discord.PCMAudio(stream=test))
    print("3")

    vc.play(source=source)
    print("4")


def close_audio(pa, s):
  print ("close_audio: Closing stream")
  s.close()
  print ("close_audio: Terminating PyAudio Object")
  pa.terminate()