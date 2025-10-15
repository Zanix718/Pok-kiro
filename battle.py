import discord
from discord.ext import commands
from discord.ui import Button, View
import asyncio

active_battles = {}


class BattleData:
    def __init__(self, challenger, opponent, format_):
        self.challenger = challenger
        self.opponent = opponent
        self.format_ = format_
        self.challenger_party = []
        self.opponent_party = []
        self.message = None


class BattleView(View):
    def __init__(self, battle_data):
        super().__init__(timeout=60)
        self.battle_data = battle_data

        accept_button = Button(label="Accept", style=discord.ButtonStyle.green)
        reject_button = Button(label="Reject", style=discord.ButtonStyle.red)

        accept_button.callback = self.accept
        reject_button.callback = self.reject

        self.add_item(accept_button)
        self.add_item(reject_button)

    async def accept(self, interaction: discord.Interaction):
        if interaction.user != self.battle_data.opponent:
            await interaction.response.send_message("You cannot accept this battle!", ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(content="Battle request accepted!", view=None)
        await start_party_selection(interaction, self.battle_data)

    async def reject(self, interaction: discord.Interaction):
        if interaction.user != self.battle_data.opponent:
            await interaction.response.send_message("You cannot reject this battle!", ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(content="Battle request rejected.", view=None)


async def start_party_selection(interaction, battle_data: BattleData):
    embed = discord.Embed(
        title="Choose your party",
        description=f"Choose **{battle_data.format_}** pokémon to fight in the battle. "
                    f"The battle will begin once both trainers have chosen their party.\n\n"
                    f"{battle_data.challenger.mention}'s Party\nNone\n\n"
                    f"{battle_data.opponent.mention}'s Party\nNone\n\n"
                    "Use `@Pokékiro battle add <order_number>` to add a pokémon to the party!",
        color=discord.Color.gold()
    )
    battle_data.message = await interaction.channel.send(embed=embed)
    active_battles[interaction.channel.id] = battle_data

def setup_commands(bot: commands.Bot):
    @bot.command(name="challenge")
    async def challenge(ctx, format_: str, opponent: discord.Member):
        if ctx.author == opponent:
            await ctx.send("You cannot challenge yourself!")
            return

        battle_data = BattleData(ctx.author, opponent, format_)
        view = BattleView(battle_data)
        msg = await ctx.send(
            f"Challenging {opponent.mention} to a battle. Click the accept button to accept!",
            view=view
        )

        await asyncio.sleep(60)
        if view.is_finished():
            return  # Already accepted or rejected
        await msg.edit(content="The request to battle has timed out.", view=None)