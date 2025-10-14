import discord
from discord import app_commands
from discord.ext import commands
import random
import string

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

def generate_trainer_id():
    length = random.randint(1, 10)
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(chars) for _ in range(length))

@bot.tree.command(name="register", description="Register yourself as a Pokémon trainer!")
async def register(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Welcome to the world of Pokémon!",
        description="Choose your gender by clicking on Male or Female.",
        color=discord.Color.yellow()
    )
  
    class GenderSelect(discord.ui.View):
        @discord.ui.button(label="Male", style=discord.ButtonStyle.primary)
        async def male(self, interaction: discord.Interaction, button: discord.ui.Button):
            trainer_id = generate_trainer_id()
            embed = discord.Embed(
                title="🎉 Congratulations!",
                description=f"You have been registered in Pokékiro!\n**Trainer ID:** `{trainer_id}`",
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=None)

        @discord.ui.button(label="Female", style=discord.ButtonStyle.danger)
        async def female(self, interaction: discord.Interaction, button: discord.ui.Button):
            trainer_id = generate_trainer_id()
            embed = discord.Embed(
                title="🎉 Congratulations!",
                description=f"You have been registered in Pokékiro!\n**Trainer ID:** `{trainer_id}`",
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=None)

    await interaction.response.send_message(embed=embed, view=GenderSelect(), ephemeral=True)
  
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

# Run your bot
bot.run("YOUR_BOT_TOKEN")
