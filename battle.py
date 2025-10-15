import discord
from discord.ext import commands
from discord.ui import View, Button
import asyncio

class BattleChallengeView(View):
    def __init__(self, challenger_id, challenged_id, format_count, timeout=60):
        super().__init__(timeout=timeout)
        self.challenger_id = challenger_id
        self.challenged_id = challenged_id
        self.format_count = format_count
        self.accepted = False
        self.timed_out = False

    async def on_timeout(self):
        self.clear_items()
        self.timed_out = True
        if hasattr(self, 'message'):
            await self.message.edit(content='The request to battle has timed out.', view=None)

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.challenged_id:
            await interaction.response.send_message('Only the challenged user can accept.', ephemeral=True)
            return
        self.accepted = True
        self.clear_items()
        # Start party selection
        party_view = PartySelectView(self.challenger_id, self.challenged_id, self.format_count)
        msg = await interaction.response.edit_message(
            content=None,
            embed=create_party_embed(self.challenger_id, self.challenged_id, self.format_count),
            view=party_view
        )
        party_view.message = msg
        battle_active[(self.challenger_id, self.challenged_id)] = party_view

    @discord.ui.button(label='Reject', style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.challenged_id:
            await interaction.response.send_message('Only the challenged user can reject.', ephemeral=True)
            return
        self.clear_items()
        await interaction.response.edit_message(content='Battle request rejected.', view=None)

def create_party_embed(user1_id, user2_id, format_count, party1=None, party2=None, ready=False):
    embed = discord.Embed(
        title='Choose your party' if not ready else '💥 Ready to battle!',
        description=(
            f'Choose **{format_count}** pokémon to fight in the battle. The battle will begin once both trainers have chosen their party.'
            if not ready else 'The battle will begin in 5 seconds.'
        ),
        color=0xFFD700
    )
    def party_text(party):
        if not party:
            return 'None'
        return '\n'.join([
            f"Lvl.{p['level']} {p['iv']}% {p['name']}{p['gender']} (#{p['order']})" for p in party
        ])
    embed.add_field(name=f"<@{user1_id}>'s Party", value=party_text(party1), inline=False)
    embed.add_field(name=f"<@{user2_id}>'s Party", value=party_text(party2), inline=False)
    embed.set_footer(text="Use `@Pokékiro battle add <order_number>` to add a pokémon to the party!")
    return embed

class PartySelectView(View):
    def __init__(self, user1_id, user2_id, format_count):
        super().__init__(timeout=None)
        self.user1_id = user1_id
        self.user2_id = user2_id
        self.format_count = format_count
        self.parties = {user1_id: [], user2_id: []}
        self.ready = False
        self.message = None

    async def add_pokemon(self, user_id, pokemon):
        if len(self.parties[user_id]) < self.format_count:
            self.parties[user_id].append(pokemon)
        await self.update_embed()
        # Check if both users have added the complete party
        if all(len(p) == self.format_count for p in self.parties.values()):
            self.ready = True
            await self.update_embed(ready=True)
            await asyncio.sleep(5)
            await self.start_battle()

    async def update_embed(self, ready=False):
        if self.message:
            await self.message.edit(
                embed=create_party_embed(
                    self.user1_id,
                    self.user2_id,
                    self.format_count,
                    self.parties[self.user1_id],
                    self.parties[self.user2_id],
                    ready=ready
                ),
                view=(self if not ready else None)
            )

    async def start_battle(self):
        embed = discord.Embed(
            title=f"Battle between <@{self.user1_id}> and <@{self.user2_id}>.",
            description="Choose your moves in DMs. After both players have chosen, the move will be executed.",
            color=0xFFD700
        )
        def party_text(party):
            return '\n'.join([
                f"Lvl.{p['level']} {p['iv']}% {p['name']}{p['gender']} (#{p['order']})" for p in party
            ])
        embed.add_field(name=f"<@{self.user1_id}>", value=party_text(self.parties[self.user1_id]), inline=True)
        embed.add_field(name=f"<@{self.user2_id}>", value=party_text(self.parties[self.user2_id]), inline=True)
        file = discord.File("battle_field.png", filename="battle_field.png")
        embed.set_image(url="attachment://battle_field.png")
        await self.message.edit(embed=embed, view=None, attachments=[file])

battle_active = {} # {(challenger_id, challenged_id): PartySelectView}

def setup(bot):
    @bot.command()
    async def challenge(ctx, format_count: int, user: discord.Member):
        if format_count not in [1,2,3,4,5,6]:
            await ctx.send("Invalid format! Only 1v1 to 6v6 allowed.")
            return
        challenger_id = ctx.author.id
        challenged_id = user.id
        view = BattleChallengeView(challenger_id, challenged_id, format_count)
        msg = await ctx.send(f"Challenging <@{challenged_id}> to a battle. Click the accept button to accept!", view=view)
        view.message = msg

    @bot.command()
    async def battle_add(ctx, order_number: int):
        # This function should validate and fetch the user's pokémon. Example stub:
        # Replace this logic with real pokémon fetch from your user/trainer system
        user_id = ctx.author.id
        for key, party_view in battle_active.items():
            if user_id in key:
                # Example: fake pokemon data, replace with actual
                pokemon = {'level': 50, 'iv': 90, 'name': 'Pikachu', 'gender': '♂', 'order': order_number}
                await party_view.add_pokemon(user_id, pokemon)
                await ctx.send(f"Added pokémon #{order_number} to your party.")
                return
        await ctx.send("You are not in an active battle party selection.")

# Usage in main.py:
# from battle import setup
# setup(bot)