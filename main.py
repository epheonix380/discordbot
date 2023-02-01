import discord
from commands.nsfw import handle_nsfw

TOKEN = "ODQ1NjY4NTE0MzQxMTkxNzUw.GaqZCO.FuZ9F6hr32-9nXuyKA9DO5A4sNBzlluQJde58w"
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message):
    if message.content.startswith(','):
        await message.channel.send("That is our prefix!")
    elif message.attachments:
        await handle_nsfw(message)
    
    

client.run(TOKEN)