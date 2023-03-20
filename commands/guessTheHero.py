import re
import discord
from discord import ui
from discord import ButtonStyle
from discord.ui.text_input import TextStyle
from helpers.gthStore import setHeroImage, setHeroName, getHeroName

class GuessTheHeroInput(ui.Modal, title='Guess The Hero Name'):
    name = ui.TextInput(label='Name')

    def __init__(self, *,custom_id: str) -> None:
        super().__init__(title="Guess The Hero Name", timeout=None, custom_id=f"{custom_id}___input")
        self.pk = custom_id

    async def on_submit(self, interaction: discord.Interaction):
        await setHeroName(self.pk, self.name)
        await interaction.response.send_message(f'Thanks for your response, {self.name} has been recorded as the hero name', ephemeral=True)

class SuccessButton(ui.Button):

    def __init__(self, *, style: ButtonStyle = ButtonStyle.success, custom_id:str = None):
        super().__init__(style=style, label="Yes", disabled=False, custom_id=custom_id,)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GuessTheHeroInput(custom_id=self.custom_id))
        return await super().callback(interaction)
    
class FailureButton(ui.Button):

    def __init__(self, *, style: ButtonStyle = ButtonStyle.danger, custom_id:str = None):
        super().__init__(style=style, label="No", disabled=False, custom_id=custom_id,)

    async def callback(self, interaction: discord.Interaction):
        await interaction.message.delete()
    


class VerificationView(ui.View):

    def __init__(self, *, pk:str):
        super().__init__(timeout=None)
        self.pk = pk
        self.label = "A guess the hero image was detected, do you wish to input the hero name?"
        self.add_item(FailureButton())
        self.add_item(SuccessButton(custom_id=pk))


async def guessTheHeroHandler(message):
    arr = []
    for match in re.finditer("https?\:\S+\.(png)|https?\:\S+\.(jpg)|https?\:\S+\.(jpeg)|https?\:\S+\.(gif)", message.content):
        if match.group(0) is not None:
            arr.append(match.group(0))
    if message.attachments or len(arr) > 0:
        url = ""
        if message.attachments:
            url = message.attachments[0].url
        else:
            url = arr[0]
        guild_id = message.guild.id
        pk = await setHeroImage(guild_id, url)
        view = VerificationView(pk=pk)
        channel = await message.author.create_dm()
        await channel.send(f"A guess the hero image was detected, do you wish to input the hero name?\n{url}", view=view)
    else:
        name = await getHeroName(message.guild.id)
        arr = []
        for match in re.finditer(f"{str(name).lower()}", str(message.content).lower()):
            if match.group(0) is not None:
                arr.append(match.group(0))
        if (len(arr)>0):
            await message.reply(f"Correct the hero was {name}")
        else:
            await message.reply(f"Incorrect")

