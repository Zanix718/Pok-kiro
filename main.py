import discord
from discord.ext import commands
from pokémon import (
    get_nature_multipliers,
    POKEMON_GEN1,
    POKEMON_GEN2,
    POKEMON_GEN3,
    POKEMON_GEN4,
    POKEMON_GEN5,
    POKEMON_GEN6,
    POKEMON_GEN7,
    POKEMON_GEN8,
    POKEMON_GEN9,
    NATURES,
    NATURE_EFFECTS,
    get_pokemon_by_name,
    get_all_pokemon,
    assign_gender
)
from stats_iv_calculation import (
    calculate_official_stats,
    generate_pokemon_ivs,
    calculate_iv_percentage
)
from moves import POKEMON_MOVES, get_move_by_name
from type_effectiveness import get_type_effectiveness, get_effectiveness_text
from movesets_scraper import get_all_moves_comprehensive
from pokedex import pokedex
from battle import setup
setup(bot)
import random
import json
import string
import os
import math
import requests
from bs4 import BeautifulSoup
import asyncio
import time
import re
from datetime import datetime
from discord.ui import View, Button
from PIL import Image, ImageDraw, ImageFont
import io
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(
    command_prefix=commands.when_mentioned,
    intents=intents
)

# Global state variables (moved from bot attributes)
message_count = 0
current_spawn = None
SHOP_ITEMS = {
    "rare candy": {
        "name": "Rare Candy",
        "price": 50,
        "currency": "pokécoins",
        "emoji": "<:rare_candy:1403486543477473521>",
        "description": "A candy that is packed with energy. It raises the level of a Pokémon by one."
    },
    "summoning stone": {
        "name": "Summoning Stone",
        "price": 200,
        "currency": "gems",
        "emoji": "<:Summoning_stone:1405194343056408747>",
        "description": "An ancient stone filled with powerful energy that can summon any pokémon."
    }
}
class PurchaseConfirmationView(View):
    def __init__(self, user_id, item_name, amount, total_cost, currency, is_gems=False):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.item_name = item_name
        self.amount = amount
        self.total_cost = total_cost
        self.currency = currency
        self.is_gems = is_gems
    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.green, emoji='✅')
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your purchase confirmation.", ephemeral=True)
            return
        trainer_data = get_trainer_data(self.user_id)
        if not trainer_data:
            await interaction.response.send_message("You are not registered as a trainer.", ephemeral=True)
            return
        if self.is_gems:
            current_coins = get_user_pokecoins(trainer_data)
            if current_coins < self.total_cost:
                await interaction.response.edit_message(
                    content=f"Not enough pokécoins! You have {current_coins} pokécoins but need {self.total_cost} pokécoins to buy {self.amount} gems.",
                    view=None
                )
                return
            if deduct_pokecoins(trainer_data, self.total_cost):
                current_gems = trainer_data.get("Shards", 0)
                trainer_data["Shards"] = current_gems + self.amount
                if update_trainer_data(str(self.user_id), trainer_data):
                    await interaction.response.edit_message(
                        content=f"You purchased {self.amount} Gems type @Pokékiro#8400 inventory to see your items.",
                        view=None
                    )
                else:
                    await interaction.response.edit_message(
                        content="Purchase failed. Please try again later.",
                        view=None
                    )
            else:
                await interaction.response.edit_message(
                    content="Purchase failed. Please try again later.",
                    view=None
                )
        else:
            if self.currency == "gems":
                current_balance = trainer_data.get("Shards", 0)
                if current_balance < self.total_cost:
                    await interaction.response.edit_message(
                        content="You not have enough Gems to buy Summoning Stone.",
                        view=None
                    )
                    return
                trainer_data["Shards"] -= self.total_cost
            else:
                if not deduct_pokecoins(trainer_data, self.total_cost):
                    await interaction.response.edit_message(
                        content="You don't have enough pokécoins to complete this purchase.",
                        view=None
                    )
                    return
            add_item_to_inventory(trainer_data, self.item_name, self.amount)
            if update_trainer_data(str(self.user_id), trainer_data):
                await interaction.response.edit_message(
                    content=f"You purchased {self.amount} {self.item_name} type @Pokékiro#8400 inventory to see your items.",
                    view=None
                )
            else:
                await interaction.response.edit_message(
                    content="Purchase failed. Please try again later.",
                    view=None
                )
    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.red, emoji='❌')
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your purchase confirmation.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Aborted.", view=None)
def load_trainers():
    try:
        if os.path.exists("trainers.json"):
            with open("trainers.json", "r") as f:
                return json.load(f)
        return {}
    except (json.JSONDecodeError, FileNotFoundError):
        return {}
def save_trainers(trainers_data):
    try:
        with open("trainers.json", "w") as f:
            json.dump(trainers_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving trainers data: {e}")
        return False
def load_market():
    try:
        if os.path.exists("market.json"):
            with open("market.json", "r") as f:
                return json.load(f)
        return {"listings": [], "next_id": 1}
    except (json.JSONDecodeError, FileNotFoundError):
        return {"listings": [], "next_id": 1}
def save_market(market_data):
    try:
        with open("market.json", "w") as f:
            json.dump(market_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving market data: {e}")
        return False
def generate_trainer_id():
    length = random.randint(5, 10)
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))
def is_trainer_registered(user_id):
    trainers = load_trainers()
    return str(user_id) in trainers
def register_trainer(user_id, gender):
    trainers = load_trainers()
    if str(user_id) in trainers:
        return None, "You are already registered."
    trainer_id = generate_trainer_id()
    registered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trainer_data = {
        "UserID": str(user_id),
        "Gender": gender,
        "TrainerID": trainer_id,
        "RegisteredAt": registered_at,
        "StarterPokemon": None,
        "HasChosenStarter": False,
        "TotalMessages": 0,
        "LastLevelUp": 1,
        "pokécoins": 0,
        "Shards": 0,
        "BattlePasses": 0,
        "inventory": {},
        "SelectedPokemon": None
    }
    trainers[str(user_id)] = trainer_data
    if save_trainers(trainers):
        return trainer_data, None
    else:
        return None, "Failed to save registration. Please try again."
def get_trainer_data(user_id):
    trainers = load_trainers()
    trainer_data = trainers.get(str(user_id))
    if trainer_data:
        if "inventory" not in trainer_data:
            trainer_data["inventory"] = {}
        if "pokécoins" not in trainer_data and "pokecoins" not in trainer_data:
            trainer_data["pokécoins"] = 0
        if "SelectedPokemon" not in trainer_data:
            trainer_data["SelectedPokemon"] = None
        if "Shards" not in trainer_data:
            trainer_data["Shards"] = 0
        if "HasChosenStarter" not in trainer_data:
            trainer_data["HasChosenStarter"] = trainer_data.get("StarterPokemon") is not None
    return trainer_data
def update_trainer_data(user_id, trainer_data):
    trainers = load_trainers()
    trainers[str(user_id)] = trainer_data
    return save_trainers(trainers)
def get_user_pokecoins(trainer_data):
    if "pokécoins" in trainer_data:
        pokecoins = trainer_data["pokécoins"]
        if isinstance(pokecoins, list):
            return sum(pokecoins)
        return pokecoins
    elif "pokecoins" in trainer_data:
        return trainer_data["pokecoins"]
    return 0
def deduct_pokecoins(trainer_data, amount):
    current_coins = get_user_pokecoins(trainer_data)
    if current_coins < amount:
        return False
    new_amount = current_coins - amount
    if "pokécoins" in trainer_data:
        trainer_data["pokécoins"] = new_amount
    else:
        trainer_data["pokécoins"] = new_amount
    return True
def add_item_to_inventory(trainer_data, item_name, amount):
    if "inventory" not in trainer_data:
        trainer_data["inventory"] = {}
    if item_name in trainer_data["inventory"]:
        trainer_data["inventory"][item_name] += amount
    else:
        trainer_data["inventory"][item_name] = amount
def calculate_official_stats(base_stats, ivs, level, nature, evs=None):
    if evs is None:
        evs = {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
    nature_lower = nature.lower()
    nature_multipliers = NATURE_EFFECTS.get(nature_lower, {})
    calculated_stats = {}
    for stat_name in ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]:
        base = base_stats.get(stat_name, 50)
        iv = ivs.get(stat_name, 0)
        ev = evs.get(stat_name, 0)
        if stat_name == "hp":
            stat_value = math.floor(((2 * base + iv + math.floor(ev / 4)) * level) / 100) + level + 10
        else:
            stat_value = math.floor(((2 * base + iv + math.floor(ev / 4)) * level) / 100) + 5
            if stat_name in nature_multipliers:
                stat_value = math.floor(stat_value * nature_multipliers[stat_name])
        calculated_stats[stat_name] = stat_value
    return calculated_stats
def calculate_iv_percentage(ivs):
    total_ivs = sum(ivs.values())
    iv_percentage = round((total_ivs / 186) * 100, 2)
    return iv_percentage
def generate_pokemon_ivs():
    return {
        "hp": random.randint(0, 31),
        "attack": random.randint(0, 31),
        "defense": random.randint(0, 31),
        "sp_attack": random.randint(0, 31),
        "sp_defense": random.randint(0, 31),
        "speed": random.randint(0, 31)
    }
def migrate_pokemon_stats():
    print("Starting Pokémon stats migration...")
    trainers = load_trainers()
    updated_count = 0
    for user_id, trainer_data in trainers.items():
        if trainer_data.get("StarterPokemon"):
            starter = trainer_data["StarterPokemon"]
            if update_pokemon_data(starter):
                updated_count += 1
                print(f"Updated starter {starter['name']} for user {user_id}")
        if "CaughtPokemons" in trainer_data:
            for i, pokemon in enumerate(trainer_data["CaughtPokemons"]):
                if update_pokemon_data(pokemon):
                    updated_count += 1
                    print(f"Updated caught {pokemon['name']} for user {user_id}")
    if save_trainers(trainers):
        print(f"Migration completed successfully! Updated {updated_count} Pokémon.")
        return True
    else:
        print("Migration failed - could not save updated data.")
        return False
def update_pokemon_data(pokemon):
    try:
        if "ivs" not in pokemon or "base_stats" not in pokemon:
            print(f"Skipping {pokemon.get('name', 'Unknown')} - missing required data")
            return False
        level = pokemon.get("level", 1)
        nature = pokemon.get("nature", "hardy").lower()
        evs = pokemon.get("evs", {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0})
        new_stats = calculate_official_stats(pokemon["base_stats"], pokemon["ivs"], level, nature, evs)
        new_iv_percentage = calculate_iv_percentage(pokemon["ivs"])
        pokemon["calculated_stats"] = new_stats
        pokemon["iv_percentage"] = new_iv_percentage
        if "evs" not in pokemon:
            pokemon["evs"] = evs
        return True
    except Exception as e:
        print(f"Error updating Pokémon {pokemon.get('name', 'Unknown')}: {e}")
        return False
def convert_text_gender_to_emoji(gender):
    if isinstance(gender, str):
        gender_lower = gender.lower().strip()
        if gender_lower == "male" or gender_lower == "m":
            return "<:male:1400956267979214971>"
        elif gender_lower == "female" or gender_lower == "f":
            return "<:female:1400956073573224520>"
        elif gender_lower == "unknown" or gender_lower == "genderless" or gender_lower == "":
            return "<:unknown:1401145566863560755>"
        elif gender.startswith("<:") and gender.endswith(">"):
            return gender
    return "<:unknown:1401145566863560755>"
def assign_pokemon_gender(pokemon_name):
    pokemon_data = get_pokemon_by_name(pokemon_name)
    if not pokemon_data or "gender_ratio" not in pokemon_data:
        gender_ratio = {"male": 87.5, "female": 12.5}
    else:
        gender_ratio = pokemon_data["gender_ratio"]
    gender_result = assign_gender(gender_ratio)
    if gender_result is None:
        return "<:unknown:1401145566863560755>"
    return gender_result
def create_spawned_pokemon(pokemon_data, level=None):
    if level is None:
        level = random.randint(1, 50)
    ivs = generate_pokemon_ivs()
    nature = random.choice(NATURES).lower()
    evs = {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
    base_stats = pokemon_data["base_stats"]
    iv_percentage = calculate_iv_percentage(ivs)
    calculated_stats = calculate_official_stats(base_stats, ivs, level, nature, evs)
    ability = pokemon_data.get("abilities", ["Unknown"])[0] if pokemon_data.get("abilities") else "Unknown"
    gender = assign_pokemon_gender(pokemon_data["name"])
    spawned_pokemon = {
        "dex": pokemon_data.get("dex", 0),
        "name": pokemon_data["name"].lower(),
        "gender": gender,
        "level": level,
        "iv_percentage": iv_percentage,
        "ivs": ivs,
        "nature": nature,
        "ability": ability,
        "base_stats": base_stats.copy(),
        "calculated_stats": calculated_stats,
        "evs": evs.copy(),
        "current_hp": calculated_stats.get("hp", 0)
    }
    return spawned_pokemon
def fix_existing_pokemon_genders():
    trainers = load_trainers()
    updated = False
    for user_id, trainer_data in trainers.items():
        if trainer_data.get("StarterPokemon"):
            starter = trainer_data["StarterPokemon"]
            old_gender = starter.get("gender", "")
            pokemon_name = starter["name"]
            new_gender = assign_pokemon_gender(pokemon_name)
            if old_gender != new_gender:
                trainer_data["StarterPokemon"]["gender"] = new_gender
                updated = True
                print(f"Fixed starter {pokemon_name} gender for user {user_id}: {old_gender} -> {new_gender}")
        if "CaughtPokemons" in trainer_data:
            for i, pokemon in enumerate(trainer_data["CaughtPokemons"]):
                old_gender = pokemon.get("gender", "")
                pokemon_name = pokemon["name"]
                new_gender = assign_pokemon_gender(pokemon_name)
                if old_gender != new_gender:
                    trainer_data["CaughtPokemons"][i]["gender"] = new_gender
                    updated = True
                    print(f"Fixed caught {pokemon_name} gender for user {user_id}: {old_gender} -> {new_gender}")
    if updated:
        save_trainers(trainers)
        return True
    return False
def fix_market_listings_genders():
    market_data = load_market()
    updated = False
    for listing in market_data.get("listings", []):
        pokemon = listing.get("pokemon", {})
        old_gender = pokemon.get("gender", "")
        pokemon_name = pokemon.get("name", "")
        if pokemon_name:
            new_gender = assign_pokemon_gender(pokemon_name)
            if old_gender != new_gender:
                listing["pokemon"]["gender"] = new_gender
                updated = True
                print(f"Fixed market listing {listing.get('market_id', 'unknown')} {pokemon_name} gender: {old_gender} -> {new_gender}")
    if updated:
        save_market(market_data)
        return True
    return False
def get_user_pokemon_list(trainer_data):
    pokemon_list = []
    starter = trainer_data.get("StarterPokemon")
    if starter:
        pokemon_list.append({
            "order": 1,
            "name": starter["name"],
            "level": starter.get("level", 1),
            "type": "starter",
            "data": starter
        })
    if "CaughtPokemons" in trainer_data:
        order = 2 if starter else 1
        for caught_pokemon in trainer_data["CaughtPokemons"]:
            pokemon_list.append({
                "order": order,
                "name": caught_pokemon["name"],
                "level": caught_pokemon.get("level", 1),
                "type": "caught",
                "data": caught_pokemon
            })
            order += 1
    return pokemon_list
def get_pokemon_by_order(trainer_data, order_number):
    pokemon_list = get_user_pokemon_list(trainer_data)
    for pokemon in pokemon_list:
        if pokemon["order"] == order_number:
            return pokemon
    return None
def get_starter_pokemon_list():
    return {
        "bulbasaur": {"name": "Bulbasaur", "emoji": "<:bulbasaur:1390604553321189406>", "generation": "I (Kanto)"},
        "charmander": {"name": "Charmander", "emoji": "<:charmander:1390604778584801320>", "generation": "I (Kanto)"},
        "squirtle": {"name": "Squirtle", "emoji": "<:squirtle:1390604851091607564>", "generation": "I (Kanto)"},
        "chikorita": {"name": "Chikorita", "emoji": "<:grass_type:1406552601415122945>", "generation": "II (Johto)"},
        "cyndaquil": {"name": "Cyndaquil", "emoji": "<:fire_type:1406552697653559336>", "generation": "II (Johto)"},
        "totodile": {"name": "Totodile", "emoji": "<:water_type:1406552467319029860>", "generation": "II (Johto)"},
        "treecko": {"name": "Treecko", "emoji": "<:grass_type:1406552601415122945>", "generation": "III (Hoenn)"},
        "torchic": {"name": "Torchic", "emoji": "<:fire_type:1406552697653559336>", "generation": "III (Hoenn)"},
        "mudkip": {"name": "Mudkip", "emoji": "<:water_type:1406552467319029860>", "generation": "III (Hoenn)"},
        "turtwig": {"name": "Turtwig", "emoji": "<:grass_type:1406552601415122945>", "generation": "IV (Sinnoh)"},
        "chimchar": {"name": "Chimchar", "emoji": "<:fire_type:1406552697653559336>", "generation": "IV (Sinnoh)"},
        "piplup": {"name": "Piplup", "emoji": "<:water_type:1406552467319029860>", "generation": "IV (Sinnoh)"},
        "snivy": {"name": "Snivy", "emoji": "<:grass_type:1406552601415122945>", "generation": "V (Unova)"},
        "tepig": {"name": "Tepig", "emoji": "<:fire_type:1406552697653559336>", "generation": "V (Unova)"},
        "oshawott": {"name": "Oshawott", "emoji": "<:water_type:1406552467319029860>", "generation": "V (Unova)"},
        "chespin": {"name": "Chespin", "emoji": "<:grass_type:1406552601415122945>", "generation": "VI (Kalos)"},
        "fennekin": {"name": "Fennekin", "emoji": "<:fire_type:1406552697653559336>", "generation": "VI (Kalos)"},
        "froakie": {"name": "Froakie", "emoji": "<:water_type:1406552467319029860>", "generation": "VI (Kalos)"},
        "rowlet": {"name": "Rowlet", "emoji": "<:grass_type:1406552601415122945>", "generation": "VII (Alola)"},
        "litten": {"name": "Litten", "emoji": "<:fire_type:1406552697653559336>", "generation": "VII (Alola)"},
        "popplio": {"name": "Popplio", "emoji": "<:water_type:1406552467319029860>", "generation": "VII (Alola)"},
        "grookey": {"name": "Grookey", "emoji": "<:grass_type:1406552601415122945>", "generation": "VIII (Galar)"},
        "scorbunny": {"name": "Scorbunny", "emoji": "<:fire_type:1406552697653559336>", "generation": "VIII (Galar)"},
        "sobble": {"name": "Sobble", "emoji": "<:water_type:1406552467319029860>", "generation": "VIII (Galar)"},
        "sprigatito": {"name": "Sprigatito", "emoji": "<:sprigatito:1390607793266102302>", "generation": "IX (Paldea)"},
        "fuecoco": {"name": "Fuecoco", "emoji": "<:fuecoco:1390607859049435221>", "generation": "IX (Paldea)"},
        "quaxly": {"name": "Quaxly", "emoji": "<:quaxly:1390607905115602944>", "generation": "IX (Paldea)"}
    }
def get_pokemon_database():
    return {
        "bulbasaur": {
            "dex": 1, "name": "Bulbasaur", "emoji": "<:bulbasaur:1390604553321189406>",
            "base_stats": {"hp": 45, "attack": 49, "defense": 49, "sp_attack": 65, "sp_defense": 65, "speed": 45},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Grass", "Poison"]
        },
        "charmander": {
            "dex": 4, "name": "Charmander", "emoji": "<:charmander:1390604778584801320>",
            "base_stats": {"hp": 39, "attack": 52, "defense": 43, "sp_attack": 60, "sp_defense": 50, "speed": 65},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Fire"]
        },
        "squirtle": {
            "dex": 7, "name": "Squirtle", "emoji": "<:squirtle:1390604851091607564>",
            "base_stats": {"hp": 44, "attack": 48, "defense": 65, "sp_attack": 50, "sp_defense": 64, "speed": 43},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Water"]
        },
        "chikorita": {
            "dex": 152, "name": "Chikorita", "emoji": "<:grass_type:1406552601415122945>",
            "base_stats": {"hp": 45, "attack": 49, "defense": 65, "sp_attack": 49, "sp_defense": 65, "speed": 45},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Grass"]
        },
        "cyndaquil": {
            "dex": 155, "name": "Cyndaquil", "emoji": "<:fire_type:1406552697653559336>",
            "base_stats": {"hp": 39, "attack": 52, "defense": 43, "sp_attack": 60, "sp_defense": 50, "speed": 65},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Fire"]
        },
        "totodile": {
            "dex": 158, "name": "Totodile", "emoji": "<:water_type:1406552467319029860>",
            "base_stats": {"hp": 50, "attack": 65, "defense": 64, "sp_attack": 44, "sp_defense": 48, "speed": 43},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Water"]
        },
        "treecko": {
            "dex": 252, "name": "Treecko", "emoji": "<:grass_type:1406552601415122945>",
            "base_stats": {"hp": 40, "attack": 45, "defense": 35, "sp_attack": 65, "sp_defense": 55, "speed": 70},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Grass"]
        },
        "torchic": {
            "dex": 255, "name": "Torchic", "emoji": "<:fire_type:1406552697653559336>",
            "base_stats": {"hp": 45, "attack": 60, "defense": 40, "sp_attack": 70, "sp_defense": 50, "speed": 45},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Fire"]
        },
        "mudkip": {
            "dex": 258, "name": "Mudkip", "emoji": "<:water_type:1406552467319029860>",
            "base_stats": {"hp": 50, "attack": 70, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 40},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Water"]
        },
        "turtwig": {
            "dex": 387, "name": "Turtwig", "emoji": "<:grass_type:1406552601415122945>",
            "base_stats": {"hp": 55, "attack": 68, "defense": 64, "sp_attack": 45, "sp_defense": 55, "speed": 31},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Grass"]
        },
        "chimchar": {
            "dex": 390, "name": "Chimchar", "emoji": "<:fire_type:1406552697653559336>",
            "base_stats": {"hp": 44, "attack": 58, "defense": 44, "sp_attack": 58, "sp_defense": 44, "speed": 61},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Fire"]
        },
        "piplup": {
            "dex": 393, "name": "Piplup", "emoji": "<:water_type:1406552467319029860>",
            "base_stats": {"hp": 53, "attack": 51, "defense": 53, "sp_attack": 61, "sp_defense": 56, "speed": 40},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Water"]
        },
        "snivy": {
            "dex": 495, "name": "Snivy", "emoji": "<:grass_type:1406552601415122945>",
            "base_stats": {"hp": 45, "attack": 45, "defense": 55, "sp_attack": 45, "sp_defense": 55, "speed": 63},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Grass"]
        },
        "tepig": {
            "dex": 498, "name": "Tepig", "emoji": "<:fire_type:1406552697653559336>",
            "base_stats": {"hp": 65, "attack": 63, "defense": 45, "sp_attack": 45, "sp_defense": 45, "speed": 45},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Fire"]
        },
        "oshawott": {
            "dex": 501, "name": "Oshawott", "emoji": "<:water_type:1406552467319029860>",
            "base_stats": {"hp": 55, "attack": 55, "defense": 45, "sp_attack": 63, "sp_defense": 45, "speed": 45},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Water"]
        },
        "chespin": {
            "dex": 650, "name": "Chespin", "emoji": "<:grass_type:1406552601415122945>",
            "base_stats": {"hp": 56, "attack": 61, "defense": 65, "sp_attack": 48, "sp_defense": 45, "speed": 38},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Grass"]
        },
        "fennekin": {
            "dex": 653, "name": "Fennekin", "emoji": "<:fire_type:1406552697653559336>",
            "base_stats": {"hp": 40, "attack": 45, "defense": 40, "sp_attack": 62, "sp_defense": 60, "speed": 60},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Fire"]
        },
        "froakie": {
            "dex": 656, "name": "Froakie", "emoji": "<:water_type:1406552467319029860>",
            "base_stats": {"hp": 41, "attack": 56, "defense": 40, "sp_attack": 62, "sp_defense": 44, "speed": 71},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Water"]
        },
        "rowlet": {
            "dex": 722, "name": "Rowlet", "emoji": "<:grass_type:1406552601415122945>",
            "base_stats": {"hp": 68, "attack": 55, "defense": 55, "sp_attack": 50, "sp_defense": 50, "speed": 42},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Grass", "Flying"]
        },
        "litten": {
            "dex": 725, "name": "Litten", "emoji": "<:fire_type:1406552697653559336>",
            "base_stats": {"hp": 45, "attack": 65, "defense": 40, "sp_attack": 60, "sp_defense": 40, "speed": 70},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Fire"]
        },
        "popplio": {
            "dex": 728, "name": "Popplio", "emoji": "<:water_type:1406552467319029860>",
            "base_stats": {"hp": 50, "attack": 54, "defense": 54, "sp_attack": 66, "sp_defense": 56, "speed": 40},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Water"]
        },
        "grookey": {
            "dex": 810, "name": "Grookey", "emoji": "<:grass_type:1406552601415122945>",
            "base_stats": {"hp": 50, "attack": 65, "defense": 50, "sp_attack": 40, "sp_defense": 40, "speed": 65},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Grass"]
        },
        "scorbunny": {
            "dex": 813, "name": "Scorbunny", "emoji": "<:fire_type:1406552697653559336>",
            "base_stats": {"hp": 50, "attack": 71, "defense": 40, "sp_attack": 40, "sp_defense": 40, "speed": 69},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Fire"]
        },
        "sobble": {
            "dex": 816, "name": "Sobble", "emoji": "<:water_type:1406552467319029860>",
            "base_stats": {"hp": 50, "attack": 40, "defense": 40, "sp_attack": 70, "sp_defense": 40, "speed": 70},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Water"]
        },
        "sprigatito": {
            "dex": 906, "name": "Sprigatito", "emoji": "<:sprigatito:1390607793266102302>",
            "base_stats": {"hp": 40, "attack": 61, "defense": 54, "sp_attack": 45, "sp_defense": 45, "speed": 65},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Grass"]
        },
        "fuecoco": {
            "dex": 909, "name": "Fuecoco", "emoji": "<:fuecoco:1390607859049435221>",
            "base_stats": {"hp": 67, "attack": 45, "defense": 59, "sp_attack": 63, "sp_defense": 40, "speed": 36},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Fire"]
        },
        "quaxly": {
            "dex": 912, "name": "Quaxly", "emoji": "<:quaxly:1390607905115602944>",
            "base_stats": {"hp": 55, "attack": 65, "defense": 45, "sp_attack": 50, "sp_defense": 45, "speed": 50},
            "gender_ratio": {"male": 87.5, "female": 12.5}, "type": ["Water"]
        }
    }
def get_nature_database():
    return {
        "adamant": {"name": "Adamant", "increased": "attack", "decreased": "sp_attack"},
        "bashful": {"name": "Bashful", "increased": None, "decreased": None},
        "bold": {"name": "Bold", "increased": "defense", "decreased": "attack"},
        "brave": {"name": "Brave", "increased": "attack", "decreased": "speed"},
        "calm": {"name": "Calm", "increased": "sp_defense", "decreased": "attack"},
        "careful": {"name": "Careful", "increased": "sp_defense", "decreased": "sp_attack"},
        "docile": {"name": "Docile", "increased": None, "decreased": None},
        "gentle": {"name": "Gentle", "increased": "sp_defense", "decreased": "defense"},
        "hardy": {"name": "Hardy", "increased": None, "decreased": None},
        "hasty": {"name": "Hasty", "increased": "speed", "decreased": "defense"},
        "impish": {"name": "Impish", "increased": "defense", "decreased": "sp_attack"},
        "jolly": {"name": "Jolly", "increased": "speed", "decreased": "sp_attack"},
        "lax": {"name": "Lax", "increased": "defense", "decreased": "sp_defense"},
        "lonely": {"name": "Lonely", "increased": "attack", "decreased": "defense"},
        "mild": {"name": "Mild", "increased": "sp_attack", "decreased": "defense"},
        "modest": {"name": "Modest", "increased": "sp_attack", "decreased": "attack"},
        "naive": {"name": "Naive", "increased": "speed", "decreased": "sp_defense"},
        "naughty": {"name": "Naughty", "increased": "attack", "decreased": "sp_defense"},
        "quiet": {"name": "Quiet", "increased": "sp_attack", "decreased": "speed"},
        "quirky": {"name": "Quirky", "increased": None, "decreased": None},
        "rash": {"name": "Rash", "increased": "sp_attack", "decreased": "sp_defense"},
        "relaxed": {"name": "Relaxed", "increased": "defense", "decreased": "speed"},
        "sassy": {"name": "Sassy", "increased": "sp_defense", "decreased": "speed"},
        "serious": {"name": "Serious", "increased": None, "decreased": None},
        "timid": {"name": "Timid", "increased": "speed", "decreased": "attack"}
    }
def get_abilities_database():
    return {
        "bulbasaur": {"normal": "Overgrow", "hidden": "Chlorophyll"},
        "charmander": {"normal": "Blaze", "hidden": "Solar Power"},
        "squirtle": {"normal": "Torrent", "hidden": "Rain Dish"},
        "chikorita": {"normal": "Overgrow", "hidden": "Leaf Guard"},
        "cyndaquil": {"normal": "Blaze", "hidden": "Flash Fire"},
        "totodile": {"normal": "Torrent", "hidden": "Sheer Force"},
        "treecko": {"normal": "Overgrow", "hidden": "Unburden"},
        "torchic": {"normal": "Blaze", "hidden": "Speed Boost"},
        "mudkip": {"normal": "Torrent", "hidden": "Damp"},
        "turtwig": {"normal": "Overgrow", "hidden": "Shell Armor"},
        "chimchar": {"normal": "Blaze", "hidden": "Iron Fist"},
        "piplup": {"normal": "Torrent", "hidden": "Defiant"},
        "snivy": {"normal": "Overgrow", "hidden": "Contrary"},
        "tepig": {"normal": "Blaze", "hidden": "Reckless"},
        "oshawott": {"normal": "Torrent", "hidden": "Shell Armor"},
        "chespin": {"normal": "Overgrow", "hidden": "Bulletproof"},
        "fennekin": {"normal": "Blaze", "hidden": "Magician"},
        "froakie": {"normal": "Torrent", "hidden": "Protean"},
        "rowlet": {"normal": "Overgrow", "hidden": "Long Reach"},
        "litten": {"normal": "Blaze", "hidden": "Intimidate"},
        "popplio": {"normal": "Torrent", "hidden": "Liquid Voice"},
        "grookey": {"normal": "Overgrow", "hidden": "Grassy Surge"},
        "scorbunny": {"normal": "Blaze", "hidden": "Libero"},
        "sobble": {"normal": "Torrent", "hidden": "Sniper"},
        "sprigatito": {"normal": "Overgrow", "hidden": "Protean"},
        "fuecoco": {"normal": "Blaze", "hidden": "Unaware"},
        "quaxly": {"normal": "Torrent", "hidden": "Moxie"}
    }
def calculate_xp_required(level):
    if level >= 100:
        return 0
    return level * 50
def calculate_level_from_messages(total_xp):
    # Level N requires N × 50 XP total
    # Level 1 = 50 XP, Level 2 = 100 XP, Level 3 = 150 XP, etc.
    level = 1
    remaining_xp = total_xp
    
    while level < 100:
        xp_needed_for_next_level = level * 50  # XP needed to reach next level
        if remaining_xp >= xp_needed_for_next_level:
            remaining_xp -= xp_needed_for_next_level
            level += 1
        else:
            break
    
    
    return level, remaining_xp
def update_trainer_xp(user_id):
    trainers = load_trainers()
    if str(user_id) not in trainers:
        return False, None
    trainer = trainers[str(user_id)]
    trainer["TotalMessages"] = trainer.get("TotalMessages", 0) + 1
    level_up_info = None
    selected_pokemon = trainer.get("SelectedPokemon")
    if selected_pokemon is not None:
        pokemon_data = None
        if selected_pokemon["type"] == "starter" and trainer["StarterPokemon"] is not None:
            pokemon_data = trainer["StarterPokemon"]
        elif selected_pokemon["type"] == "caught" and "CaughtPokemons" in trainer:
            caught_index = selected_pokemon["order"] - 2
            if 0 <= caught_index < len(trainer["CaughtPokemons"]):
                pokemon_data = trainer["CaughtPokemons"][caught_index]
        if pokemon_data is not None:
            # Add individual Pokemon XP tracking
            if "xp" not in pokemon_data:
                pokemon_data["xp"] = 0
            
            old_xp = pokemon_data["xp"]
            # Add 1 XP per message
            pokemon_data["xp"] += 1
            total_xp = pokemon_data["xp"]
            
            
            # Calculate what level this Pokemon should be
            target_level, remaining_xp = calculate_level_from_messages(total_xp)
            current_level = pokemon_data.get("level", 1)
            
            # Only level up if target level is higher
            if target_level > current_level:
                # Level up one level at a time for proper move learning
                new_level = current_level + 1
                pokemon_data["level"] = new_level
                trainer["LastLevelUp"] = new_level
                
                moves_to_learn = []
                try:
                    movesets = get_all_moves_comprehensive(pokemon_data["name"])
                    if "level_up" in movesets and movesets["level_up"]:
                        for level in range(current_level + 1, new_level + 1):
                            for move_info in movesets["level_up"]:
                                if move_info.get("level") and move_info["level"].isdigit():
                                    move_level = int(move_info["level"])
                                    if move_level == level:
                                        moves_to_learn.append(move_info["move"])
                except:
                    pass
                if moves_to_learn:
                    if "learned_moves" not in pokemon_data:
                        pokemon_data["learned_moves"] = []
                    for move in moves_to_learn:
                        if move not in pokemon_data["learned_moves"]:
                            pokemon_data["learned_moves"].append(move)
                level_up_info = {
                    "pokemon_name": pokemon_data["name"],
                    "new_level": new_level,
                    "old_level": current_level,
                    "moves_learned": moves_to_learn,
                    "total_xp": total_xp,
                    "xp_for_next_level": (new_level + 1) * 50 - total_xp
                }
    trainers[str(user_id)] = trainer
    save_success = save_trainers(trainers)
    return save_success, level_up_info
def get_gender_emoji(pokemon_name):
    return assign_pokemon_gender(pokemon_name)
def pick_starter_pokemon(user_id, pokemon_name):
    trainers = load_trainers()
    user_id_str = str(user_id)
    if user_id_str not in trainers:
        return None, "You need to register first! Use the register command."
    if trainers[user_id_str].get("HasChosenStarter", False):
        return None, "You already have chosen a starter Pokemon! You cannot choose another one."
    starters = get_starter_pokemon_list()
    pokemon_key = pokemon_name.lower()
    if pokemon_key not in starters:
        return None, f"'{pokemon_name}' is not a valid starter Pokemon!"
    pokemon_data = get_pokemon_database()[pokemon_key]
    abilities_db = get_abilities_database()
    ivs = generate_pokemon_ivs()
    iv_percentage = calculate_iv_percentage(ivs)
    gender = get_gender_emoji(pokemon_key)
    nature_keys = list(get_nature_database().keys())
    random_nature = random.choice(nature_keys)
    ability_roll = random.random()
    if ability_roll <= 0.3:
        chosen_ability = abilities_db[pokemon_key]["hidden"]
    else:
        chosen_ability = abilities_db[pokemon_key]["normal"]
    trainers[user_id_str]["StarterPokemon"] = {
        "name": starters[pokemon_key]["name"],
        "emoji": starters[pokemon_key]["emoji"],
        "pickedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dex": pokemon_data["dex"],
        "level": 1,
        "ivs": ivs,
        "iv_percentage": iv_percentage,
        "gender": gender,
        "base_stats": pokemon_data["base_stats"],
        "nature": random_nature,
        "ability": chosen_ability
    }
    trainers[user_id_str]["HasChosenStarter"] = True
    if save_trainers(trainers):
        return starters[pokemon_key], None
    else:
        return None, "Failed to save your starter Pokemon. Please try again."
class GenderSelect(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Male", style=discord.ButtonStyle.blurple)
    async def male(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_gender_selection(interaction, "Male")
    @discord.ui.button(label="Female", style=discord.ButtonStyle.danger)
    async def female(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_gender_selection(interaction, "Female")
    async def handle_gender_selection(self, interaction: discord.Interaction, gender: str):
        user_id = interaction.user.id
        if is_trainer_registered(user_id):
            await interaction.response.send_message("You are already registered in Pokékiro", ephemeral=True)
            return
        trainer_data, error_message = register_trainer(user_id, gender)
        if error_message:
            await interaction.response.send_message(error_message, ephemeral=True)
        elif trainer_data:
            success_message = (
                f"✅ You selected **{gender}**!\n"
                f"🆔 Trainer ID: {trainer_data['TrainerID']}\n"
                f"📅 Registered at: {trainer_data['RegisteredAt']}"
            )
            await interaction.response.send_message(success_message, ephemeral=True)
        else:
            await interaction.response.send_message("An unexpected error occurred. Please try again.", ephemeral=True)
class PokemonCollectionView(discord.ui.View):
    def __init__(self, user_id, pokemon_list, page=0):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.pokemon_list = pokemon_list
        self.page = page
        self.per_page = 20
        self.total_pages = max(1, (len(pokemon_list) + self.per_page - 1) // self.per_page)
        self.update_buttons()
    def update_buttons(self):
        if len(self.children) >= 2:
            self.children[0].disabled = (self.page <= 0)
            self.children[1].disabled = (self.page >= self.total_pages - 1)
    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your Pokemon collection!", ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your Pokemon collection!", ephemeral=True)
            return
        if self.page < self.total_pages - 1:
            self.page += 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    def create_embed(self):
        embed = discord.Embed(
            title="Your pokémon",
            color=0xFFD700
        )
        start_idx = self.page * self.per_page
        end_idx = min(start_idx + self.per_page, len(self.pokemon_list))
        page_pokemon = self.pokemon_list[start_idx:end_idx]
        pokemon_text = ""
        for i, pokemon in enumerate(page_pokemon):
            collection_number = pokemon['caught_order']
            pokemon_text += f"{collection_number}　**{pokemon['name']}**{pokemon['gender']}　•　Lvl. {pokemon['level']}　•　{pokemon['iv_percentage']}%\n"
        if pokemon_text:
            embed.description = pokemon_text
        else:
            embed.description = "No Pokémon found."
        if self.total_pages > 1:
            start_showing = start_idx + 1
            end_showing = end_idx
            total_pokemon = len(self.pokemon_list)
            current_page = self.page + 1
            embed.set_footer(text=f"Showing entries {start_showing}–{end_showing} out of {total_pokemon}. Page {current_page} of {self.total_pages}.")
        return embed
class MarketConfirmationView(View):
    def __init__(self, user_id, pokemon_data, order_number, amount, timeout=300):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.pokemon_data = pokemon_data
        self.order_number = order_number
        self.amount = amount
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm_listing(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your confirmation dialog.", ephemeral=True)
            return
        market_data = load_market()
        market_id = market_data["next_id"]
        listing = {
            "market_id": market_id,
            "user_id": str(self.user_id),
            "order_number": self.order_number,
            "amount": self.amount,
            "pokemon": self.pokemon_data["data"].copy(),
            "listed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        market_data["listings"].append(listing)
        market_data["next_id"] += 1
        if save_market(market_data):
            trainer_data = get_trainer_data(str(self.user_id))
            if trainer_data:
                caught_pokemon = trainer_data.get("CaughtPokemons", [])
                updated_pokemon = []
                for i, pokemon in enumerate(caught_pokemon):
                    if i != (self.order_number - 2):
                        updated_pokemon.append(pokemon)
                trainer_data["CaughtPokemons"] = updated_pokemon
                update_trainer_data(str(self.user_id), trainer_data)
            pokemon = self.pokemon_data["data"]
            gender_emoji = convert_text_gender_to_emoji(pokemon.get('gender', 'Unknown'))
            success_message = (f"Listed your Level {pokemon['level']} {pokemon['name'].title()}{gender_emoji} "
                             f"({pokemon['iv_percentage']}%) No. {self.order_number} on "
                             f"the market for {self.amount} Pokécoins (Listing #{market_id}).")
            await interaction.response.edit_message(view=None)
            await interaction.followup.send(success_message)
        else:
            error_message = "Failed to list Pokemon on the market. Please try again."
            await interaction.response.edit_message(view=None)
            await interaction.followup.send(error_message)
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_listing(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your confirmation dialog.", ephemeral=True)
            return
        await interaction.response.edit_message(view=None)
        await interaction.followup.send("Listing cancelled.")
class MarketplacePagination(View):
    def __init__(self, listings, page=0, per_page=20, timeout=300):
        super().__init__(timeout=timeout)
        self.listings = listings
        self.page = page
        self.per_page = per_page
        self.max_pages = max(1, math.ceil(len(listings) / per_page))
        self.update_buttons()
    def update_buttons(self):
        if len(self.children) >= 2:
            self.children[0].disabled = (self.page <= 0)
            self.children[1].disabled = (self.page >= self.max_pages - 1)
    def get_current_page_listings(self):
        start_idx = self.page * self.per_page
        end_idx = start_idx + self.per_page
        return self.listings[start_idx:end_idx]
    def create_embed(self):
        embed = discord.Embed(
            title="Pokétwo Marketplace",
            color=0xFFD700
        )
        if not self.listings:
            embed.description = "No Pokémon available in the marketplace."
            return embed
        page_listings = self.get_current_page_listings()
        description_lines = []
        for listing in page_listings:
            pokemon = listing["pokemon"]
            gender_emoji = convert_text_gender_to_emoji(pokemon.get('gender', 'Unknown'))
            line = f"{listing['market_id']}　**{pokemon['name'].title()}**{gender_emoji}　•　Lvl. {pokemon['level']}　•　{pokemon['iv_percentage']}%　•　{listing['amount']} Pokécoins"
            description_lines.append(line)
        embed.description = "\n".join(description_lines)
        if self.max_pages > 1:
            embed.set_footer(text=f"Page {self.page + 1}/{self.max_pages}")
        return embed
    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if self.page < self.max_pages - 1:
            self.page += 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
@bot.command()
async def register(ctx):
    embed = discord.Embed(
        title="Welcome to the world of Pokémon!",
        description="Choose your character by clicking on **Male** or **Female**.",
        color=discord.Color.gold()
    )
    embed.set_image(url="https://static.wikia.nocookie.net/ultimate-pokemon-fanon/images/c/c5/Ivy-Rye.jpg/revision/latest?cb=20201212225708")
    await ctx.send(embed=embed, view=GenderSelect())
@bot.command(name="starter")
async def starter_selection(ctx):
    embed = discord.Embed(
        title="Welcome to the world of Pokémon!",
        description="To start, choose one of the starter Pokémon using the\n@Pokékiro#8400 pick <pokemon> command.",
        color=discord.Color.gold()
    )
    embed.add_field(
        name="**Generation I (Kanto)**",
        value="<:bulbasaur:1390604553321189406>  Bulbasaur  ·  <:charmander:1390604778584801320>  Charmander  ·  <:squirtle:1390604851091607564>  Squirtle",
        inline=False
    )
    embed.add_field(
        name="**Generation II (Johto)**",
        value="<:chikorita:1390605119489577053>  Chikorita  ·  <:cyndaquil:1390605148664889344>  Cyndaquil  ·  <:totodile:1390605177123246144>  Totodile",
        inline=False
    )
    embed.add_field(
        name="**Generation III (Hoenn)**",
        value="<:treecko:1390605513892429897>  Treecko  ·  <:torchic:1390605536558452826>  Torchic  ·  <:mudkip:1390605558347989064>  Mudkip",
        inline=False
    )
    embed.add_field(
        name="**Generation IV (Sinnoh)**",
        value="<:grotle:1390605781271052298>  Turtwig  ·  <:chimchar:1390605819296485376>  Chimchar  ·  <:piplup:1390605848023400550>  Piplup",
        inline=False
    )
    embed.add_field(
        name="**Generation V (Unova)**",
        value="<:snivy:1390606080958009384>  Snivy  ·  <:tepig:1390606123068952666>  Tepig  ·  <:oshawott:1390606151527301121>  Oshawott",
        inline=False
    )
    embed.add_field(
        name="**Generation VI (Kalos)**",
        value="<:chespin:1390606464179240961>  Chespin  ·  <:fennekin:1390606541740314675>  Fennekin  ·  <:froakie:1390606610644336800>  Froakie",
        inline=False
    )
    embed.add_field(
        name="**Generation VII (Alola)**",
        value="<:rowlet:1390606834905256047>  Rowlet  ·  <:litten:1390606869290029157>   Litten  ·  <:popplio:1390606900533526591>  Popplio",
        inline=False
    )
    embed.add_field(
        name="**Generation VIII (Galar)**",
        value="<:grookey:1390607074689286315>  Grookey  ·  <:scorbunny:1390607113080016956>  Scorbunny  ·  <:sobble:1390607161671024721>  Sobble",
        inline=False
    )
    embed.add_field(
        name="**Generation IX (Paldea)**",
        value="<:sprigatito:1390607793266102302>  Sprigatito  ·  <:fuecoco:1390607859049435221>  Fuecoco  ·  <:quaxly:1390607905115602944>  Quaxly",
        inline=False
    )
    await ctx.send(embed=embed)
@bot.command()
async def pick(ctx, *, pokemon_name: str = ""):
    if not pokemon_name:
        await ctx.send("Please specify a Pokemon! Example: `@Pokékiro#8400 pick charmander`")
        return
    pokemon_data, error_message = pick_starter_pokemon(ctx.author.id, pokemon_name)
    if error_message:
        await ctx.send(error_message)
    elif pokemon_data:
        success_message = (
            f"🎉 Congratulations on entering the world of pokémon!\n"
            f"{pokemon_data['emoji']} **{pokemon_data['name']}** is your first pokémon.\n"
            f"Type @Pokékiro#8400 info to view it!"
        )
        await ctx.send(success_message)
    else:
        await ctx.send("An unexpected error occurred. Please try again.")
def generate_missing_pokemon_data(pokemon_data, pokemon_name=None):
    from pokémon import NATURES
    if "ivs" not in pokemon_data or not pokemon_data["ivs"]:
        pokemon_data["ivs"] = generate_pokemon_ivs()
    if "iv_percentage" not in pokemon_data:
        pokemon_data["iv_percentage"] = calculate_iv_percentage(pokemon_data["ivs"])
    if "nature" not in pokemon_data or not pokemon_data["nature"]:
        pokemon_data["nature"] = random.choice(NATURES).lower()
    if "ability" not in pokemon_data or not pokemon_data["ability"]:
        pokemon_name = pokemon_data.get("name", "").lower()
        found_pokemon = get_pokemon_by_name(pokemon_name)
        if found_pokemon:
            correct_abilities = found_pokemon.get("abilities", ["Unknown"])
        else:
            correct_abilities = ["Unknown"]
        pokemon_data["ability"] = random.choice(correct_abilities)
    if "gender" not in pokemon_data or not pokemon_data["gender"]:
        pokemon_data["gender"] = assign_pokemon_gender(pokemon_data["name"])
    if "base_stats" not in pokemon_data or not pokemon_data["base_stats"]:
        pokemon_data["base_stats"] = {
            "hp": 45, "attack": 49, "defense": 49,
            "sp_attack": 65, "sp_defense": 65, "speed": 45
        }
    if "evs" not in pokemon_data:
        pokemon_data["evs"] = {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
    level = pokemon_data.get("level", 1)
    nature = pokemon_data.get("nature", "hardy")
    pokemon_data["calculated_stats"] = calculate_official_stats(
        pokemon_data["base_stats"],
        pokemon_data["ivs"],
        level,
        nature,
        pokemon_data["evs"]
    )
    return pokemon_data
def enhance_caught_pokemon_data(caught_pokemon, pokemon_db):
    pokemon_name = caught_pokemon.get("name", "").lower()
    base_data = None
    for pokemon in pokemon_db:
        if pokemon["name"].lower() == pokemon_name:
            base_data = pokemon
            break
    if not base_data:
        starter_db = get_starter_pokemon_list()
        if pokemon_name in starter_db:
            starter_info = starter_db[pokemon_name]
            comp_db = get_pokemon_database()
            if pokemon_name in comp_db:
                base_data = comp_db[pokemon_name]
    enhanced_data = caught_pokemon.copy()
    if "ivs" not in enhanced_data:
        enhanced_data["ivs"] = generate_pokemon_ivs()
    if "iv_percentage" not in enhanced_data:
        enhanced_data["iv_percentage"] = calculate_iv_percentage(enhanced_data["ivs"])
    if "nature" not in enhanced_data:
        from pokémon import NATURES
        enhanced_data["nature"] = random.choice(NATURES).lower()
    if "ability" not in enhanced_data and base_data:
        abilities = base_data.get("abilities", ["Unknown"])
        enhanced_data["ability"] = random.choice(abilities)
    if "base_stats" not in enhanced_data and base_data:
        enhanced_data["base_stats"] = base_data.get("base_stats", {})
    if "dex" not in enhanced_data and base_data:
        enhanced_data["dex"] = base_data.get("dex", 0)
    if "evs" not in enhanced_data:
        enhanced_data["evs"] = {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
    if "calculated_stats" not in enhanced_data and "base_stats" in enhanced_data:
        level = enhanced_data.get("level", 1)
        nature = enhanced_data.get("nature", "hardy")
        enhanced_data["calculated_stats"] = calculate_official_stats(
            enhanced_data["base_stats"],
            enhanced_data["ivs"],
            level,
            nature,
            enhanced_data["evs"]
        )
    # Initialize current_hp to max HP if not already set
    if "current_hp" not in enhanced_data and "calculated_stats" in enhanced_data:
        enhanced_data["current_hp"] = enhanced_data["calculated_stats"].get("hp", 0)
    return enhanced_data
@bot.command()
async def info(ctx, order_number: int = 0):
    if order_number == 0:
        embed = discord.Embed(
            title="Missing Order Number",
            description="Please specify which Pokemon you want to view!\n\nUse: `@Pokékiro info [order_number]`\nExample: `@Pokékiro info 1`",
            color=0xe74c3c
        )
        await ctx.send(embed=embed)
        return
    if not is_trainer_registered(ctx.author.id):
        embed = discord.Embed(
            title="Not Registered",
            description="You need to register first!\n\nUse: `@Pokékiro register [Male/Female]`",
            color=0xe74c3c
        )
        await ctx.send(embed=embed)
        return
    trainer_data = get_trainer_data(ctx.author.id)
    if not trainer_data:
        await ctx.send("Unable to retrieve trainer data.")
        return
    pokemon_info = get_pokemon_by_order(trainer_data, order_number)
    if not pokemon_info:
        embed = discord.Embed(
            title="Pokemon Not Found",
            description=f"You don't have a Pokemon at position #{order_number}.\n\nUse `@Pokékiro pokémons` to see your collection.",
            color=0xe74c3c
        )
        await ctx.send(embed=embed)
        return
    pokemon = pokemon_info["data"]
    pokemon_type = pokemon_info["type"]
    if pokemon_type == "caught":
        pokemon = generate_missing_pokemon_data(pokemon, pokemon.get("name"))
        for i, p in enumerate(trainer_data.get("CaughtPokemons", [])):
            if p["name"] == pokemon["name"] and i == (order_number - 2):
                trainer_data["CaughtPokemons"][i] = pokemon
                update_trainer_data(ctx.author.id, trainer_data)
                break
    current_level = pokemon.get("level", 1)
    if pokemon_type == "starter":
        total_messages = trainer_data.get("TotalMessages", 0)
        calculated_level = max(1, total_messages // 100 + 1)
        if calculated_level > current_level:
            current_level = calculated_level
            pokemon["level"] = current_level
            trainer_data["StarterPokemon"] = pokemon
            update_trainer_data(ctx.author.id, trainer_data)
        # Calculate XP display using TOTAL XP values from user's table
        pokemon_xp = pokemon.get("xp", 0)  # XP within current level
        if current_level >= 100:
            xp_display = "MAX LEVEL"
            xp_to_next = 0
        else:
            # Show XP progress: within-level XP / current level requirement  
            current_level_requirement = current_level * 50         # XP requirement for current level
            # XP to next level = remaining XP to complete current level requirement
            xp_to_next = max(0, current_level_requirement - pokemon_xp)
            
            # Format: within-level XP / current level requirement
            xp_display = f"{pokemon_xp}/{current_level_requirement}"
    else:
        # For caught Pokemon, use TOTAL XP values from user's table
        pokemon_xp = pokemon.get("xp", 0)  # XP within current level
        if current_level >= 100:
            xp_display = "MAX LEVEL"
            xp_to_next = 0
        else:
            # Show XP progress: within-level XP / current level requirement  
            current_level_requirement = current_level * 50         # XP requirement for current level
            # XP to next level = remaining XP to complete current level requirement
            xp_to_next = max(0, current_level_requirement - pokemon_xp)
            
            # Format: within-level XP / current level requirement
            xp_display = f"{pokemon_xp}/{current_level_requirement}"
    base_stats = pokemon.get("base_stats", {})
    ivs = pokemon.get("ivs", {})
    nature = pokemon.get("nature", "hardy")
    evs = pokemon.get("evs", {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0})
    current_stats = calculate_official_stats(base_stats, ivs, current_level, nature, evs)
    embed = discord.Embed(
        title=f"Level {current_level} {pokemon['name']}",
        color=0xFFD700
    )
    embed.set_image(url=get_pokemon_image_url(pokemon['name']))
    nature_name = pokemon.get("nature", "Hardy").title()
    ability_name = pokemon.get("ability", "Unknown")
    gender_emoji = pokemon.get('gender', '<:unknown:1401145566863560755>')
    if gender_emoji == '<:male:1400956267979214971>':
        gender_display = gender_emoji
    elif gender_emoji == '<:female:1400956073573224520>':
        gender_display = gender_emoji
    elif gender_emoji == '<:unknown:1401145566863560755>':
        gender_display = gender_emoji
    else:
        gender_display = convert_text_gender_to_emoji(str(gender_emoji))
    details_value = f"**XP:** {xp_display}"
    if pokemon_type == "starter" and current_level < 100:
        details_value += f" ({xp_to_next} XP to next level)"
    elif pokemon_type == "caught":
        details_value += f" ({xp_to_next} XP to next level)"
    details_value += f"\n**Nature:** {nature_name}\n**Ability:** {ability_name}\n**Gender:** {gender_display}"
    embed.add_field(
        name="📋 Details",
        value=details_value,
        inline=False
    )
    stats_value = ""
    stat_names = {
        "hp": "HP",
        "attack": "Attack",
        "defense": "Defense",
        "sp_attack": "Sp. Atk",
        "sp_defense": "Sp. Def",
        "speed": "Speed"
    }
    for stat_key, stat_name in stat_names.items():
        stat_value = current_stats.get(stat_key, 50)
        iv_value = pokemon.get("ivs", {}).get(stat_key, 15)
        stats_value += f"**{stat_name}:** {stat_value} – IV: {iv_value}/31\n"
    total_iv = pokemon.get("iv_percentage", 50.0)
    stats_value += f"**Total IV:** {total_iv}%"
    embed.add_field(
        name="📊 Stats",
        value=stats_value,
        inline=False
    )
    embed.set_footer(text="Official Pokémon Artwork")
    await ctx.send(embed=embed)
@bot.command(name="pokémons", aliases=["pokemon", "pokemons"])
async def pokemon_collection(ctx):
    trainers = load_trainers()
    user_id = str(ctx.author.id)
    if user_id not in trainers:
        await ctx.send("You are not registered yet. Use the register command first!")
        return
    trainer = trainers[user_id]
    pokemon_list = []
    starter = trainer.get("StarterPokemon")
    if starter:
        if "dex" not in starter:
            save_trainers(trainers)
        pokemon_list.append({
            "dex": starter.get("dex", 0),
            "name": starter["name"],
            "gender": starter.get("gender", "?"),
            "level": starter.get("level", 1),
            "iv_percentage": starter.get("iv_percentage", 0.0),
            "caught_order": 1
        })
    caught_pokemons = trainer.get("CaughtPokemons", [])
    order = 2 if starter else 1
    for poke in caught_pokemons:
        pokemon_list.append({
            "dex": poke.get("dex", 0),
            "name": poke["name"],
            "gender": poke.get("gender", "?"),
            "level": poke.get("level", 1),
            "iv_percentage": poke.get("iv_percentage", 0.0),
            "caught_order": order
        })
        order += 1
    if not pokemon_list:
        embed = discord.Embed(
            title="Your pokémon",
            description="You don't have any Pokémon yet! Use `@Pokékiro#8400 starter` to choose your first Pokémon.",
            color=0xFFD700
        )
        await ctx.send(embed=embed)
        return
    pokemon_list.sort(key=lambda x: x["caught_order"])
    view = PokemonCollectionView(ctx.author.id, pokemon_list)
    embed = view.create_embed()
    await ctx.send(embed=embed, view=view)
class ShopPageSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Page 1",
                description="XP Boosters & Candies",
                value="1"
            ),
            discord.SelectOption(
                label="Page 2",
                description="Evolution Stones & Fossils",
                value="2"
            ),
            discord.SelectOption(
                label="Page 3",
                description="Form Change Items",
                value="3"
            ),
            discord.SelectOption(
                label="Page 4",
                description="Held Items & Battle Items",
                value="4"
            ),
            discord.SelectOption(
                label="Page 5",
                description="Nature Mints & Healing Items",
                value="5"
            ),
            discord.SelectOption(
                label="Page 6",
                description="Key Items & Valuable Items",
                value="6"
            ),
            discord.SelectOption(
                label="Page 7",
                description="TM/HM & Berries",
                value="7"
            ),
            discord.SelectOption(
                label="Page 8",
                description="Currency Exchange & Currency Buy",
                value="8"
            ),
            discord.SelectOption(
                label="Page 9",
                description="Passes & Chests",
                value="9"
            ),
            discord.SelectOption(
                label="Page 10",
                description="Energy",
                value="10"
            )
        ]
        super().__init__(placeholder="Open a page", options=options)
    async def callback(self, interaction: discord.Interaction):
        page_num = int(self.values[0])
        if page_num == 1:
            embed = discord.Embed(
                title=f"Pokékiro Shop — Page {page_num} (XP Boosters & Candies)",
                description=(
                    "Welcome to the Pokékiro Shop!\n"
                    "Here, you can purchase any item you want. Just type `@Pokékiro#8400 buy <item> <amount>` to purchase it.\n\n"
                ),
                color=0xFFD700
            )
            if "rare candy" in SHOP_ITEMS:
                item = SHOP_ITEMS["rare candy"]
                embed.description += f"**{item['emoji']} {item['name']} - {item['price']} pokécoins each**\n{item['description']}\n\n"
        elif page_num == 4:
            embed = discord.Embed(
                title=f"Pokékiro Shop — Page {page_num} (Held Items & Battle Items)",
                description=(
                    "Welcome to the Pokékiro Shop!\n"
                    "Here, you can purchase any item you want. Just type `@Pokékiro#8400 buy <item> <amount>` to purchase it.\n\n"
                ),
                color=0xFFD700
            )
            for item_key, item in SHOP_ITEMS.items():
                currency = item.get("currency", "pokécoins")
                embed.description += f"**{item['emoji']} {item['name']} - {item['price']} {currency} each**\n{item['description']}\n\n"
        elif page_num == 8:
            embed = discord.Embed(
                title=f"Pokékiro Shop — Page {page_num} (Currency Exchange & Currency Buy)",
                description=(
                    "Welcome to the Pokékiro Shop!\n"
                    "Here, you can purchase any item you want. Just type `@Pokékiro#8400 buy <item> <amount>` to purchase it.\n\n"
                    "**<:gems:1390696438383509555> Gems - 400 pokécoins each**\n"
                    "Gems is currency with which you can buy expensive items\n\n"
                ),
                color=0xFFD700
            )
        elif page_num == 10:
            embed = discord.Embed(
                title=f"Pokékiro Shop — Page {page_num} (Energy)",
                description=(
                    "Welcome to the Pokékiro Shop!\n"
                    "Here, you can purchase any item you want. Just type `@Pokékiro#8400 buy <item> <amount>` to purchase it.\n\n"
                ),
                color=0xFFD700
            )
            if "summoning stone" in SHOP_ITEMS:
                item = SHOP_ITEMS["summoning stone"]
                currency = item.get("currency", "pokécoins")
                embed.description += f"**{item['emoji']} {item['name']} - {item['price']} {currency} each**\n{item['description']}\n\n"
        else:
            embed = discord.Embed(
                title=f"Pokékiro Shop — Page {page_num}",
                description=f"This is page {page_num} content. (Feature coming soon!)",
                color=0xFFD700
            )
        await interaction.response.edit_message(embed=embed, view=None)
class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(ShopPageSelect())
def get_trainer_pokécoins(user_id):
    trainers = load_trainers()
    trainer = trainers.get(str(user_id))
    if trainer:
        return get_user_pokecoins(trainer)
    return 0
def get_trainer_gems(user_id):
    trainers = load_trainers()
    trainer = trainers.get(str(user_id))
    if trainer:
        return trainer.get("Shards", 0)
    return 0
@bot.command()
async def shop(ctx, page: int = None):
    if not is_trainer_registered(ctx.author.id):
        embed = discord.Embed(
            title="Not Registered",
            description="You need to register first!\n\nUse: `@Pokékiro register [Male/Female]`",
            color=0xe74c3c
        )
        await ctx.send(embed=embed)
        return
    pokécoins_balance = get_trainer_pokécoins(ctx.author.id)
    gems_balance = get_trainer_gems(ctx.author.id)
    if page == 1:
        embed = discord.Embed(
            title=f"Pokékiro Shop — Page {page} (XP Boosters & Candies)",
            description=(
                "Welcome to the Pokékiro Shop!\n"
                "Here, you can purchase any item you want. Just type `@Pokékiro#8400 buy <item> <amount>` to purchase it.\n\n"
            ),
            color=0xFFD700
        )
        if "rare candy" in SHOP_ITEMS:
            item = SHOP_ITEMS["rare candy"]
            currency = item.get("currency", "pokécoins")
            embed.description += f"**{item['emoji']} {item['name']} - {item['price']} {currency} each**\n{item['description']}\n\n"
        await ctx.send(embed=embed)
        return
    if page == 4:
        embed = discord.Embed(
            title=f"Pokékiro Shop — Page {page} (Held Items & Battle Items)",
            description=(
                "Welcome to the Pokékiro Shop!\n"
                "Here, you can purchase any item you want. Just type `@Pokékiro#8400 buy <item> <amount>` to purchase it.\n\n"
            ),
            color=0xFFD700
        )
        for item_key, item in SHOP_ITEMS.items():
            currency = item.get("currency", "pokécoins")
            embed.description += f"**{item['emoji']} {item['name']} - {item['price']} {currency} each**\n{item['description']}\n\n"
        await ctx.send(embed=embed)
        return
    if page == 8:
        embed = discord.Embed(
            title=f"Pokékiro Shop — Page {page} (Currency Exchange & Currency Buy)",
            description=(
                "Welcome to the Pokékiro Shop!\n"
                "Here, you can purchase any item you want. Just type `@Pokékiro#8400 buy <item> <amount>` to purchase it.\n\n"
                "**<:gems:1390696438383509555> Gems - 400 pokécoins each**\n"
                "Gems is currency with which you can buy expensive items\n\n"
            ),
            color=0xFFD700
        )
        await ctx.send(embed=embed)
        return
    if page == 10:
        embed = discord.Embed(
            title=f"Pokékiro Shop — Page {page} (Energy)",
            description=(
                "Welcome to the Pokékiro Shop!\n"
                "Here, you can purchase any item you want. Just type `@Pokékiro#8400 buy <item> <amount>` to purchase it.\n\n"
            ),
            color=0xFFD700
        )
        if "summoning stone" in SHOP_ITEMS:
            item = SHOP_ITEMS["summoning stone"]
            currency = item.get("currency", "pokécoins")
            embed.description += f"**{item['emoji']} {item['name']} - {item['price']} {currency} each**\n{item['description']}\n\n"
        await ctx.send(embed=embed)
        return
    embed = discord.Embed(
        title=f"Pokékiro Shop — {pokécoins_balance} pokécoins | {gems_balance} gems",
        description=(
            "Welcome to the Pokékiro Shop!\n"
            "Here, you can purchase any item you want. Just type `@Pokékiro#8400 buy <item> <amount>` to purchase it.\n\n"
            "Use `@Pokékiro shop <page>` to view different pages.\n\n"
            "**Page 1** — XP Boosters & Candies\n"
            "**Page 2** — Evolution Stones & Fossils\n"
            "**Page 3** — Form Change Items\n"
            "**Page 4** — Held Items & Battle Items\n"
            "**Page 5** — Nature Mints & Healing Items\n"
            "**Page 6** — Key Items & Valuable Items\n"
            "**Page 7** — TM/HM & Berries\n"
            "**Page 8** — Currency Exchange & Currency Buy\n"
            "**Page 9** — Passes & Chests\n"
            "**Page 10** — Energy"
        ),
        color=0xFFD700
    )
    view = ShopView()
    await ctx.send(embed=embed, view=view)
class InventoryDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Hunting Items",
                description="Total Items = 0",
                value="hunting"
            ),
            discord.SelectOption(
                label="Stones & Fossils",
                description="Total Items = 0",
                value="stones"
            ),
            discord.SelectOption(
                label="Held Items & Battle Items",
                description="Total Items = 0",
                value="held"
            ),
            discord.SelectOption(
                label="Nature Mints & Healing Items",
                description="Total Items = 0",
                value="nature"
            ),
            discord.SelectOption(
                label="Key Items & Valuable Items",
                description="Total Items = 0",
                value="key"
            ),
            discord.SelectOption(
                label="TM/HM & Barriers",
                description="Total Items = 0",
                value="tm"
            ),
            discord.SelectOption(
                label="Wallet & Passes",
                description="Total Items = 0",
                value="wallet"
            ),
            discord.SelectOption(
                label="Energy Capsule & Chest",
                description="Total Items = 0",
                value="energy"
            )
        ]
        super().__init__(placeholder="Open a page", options=options, row=1)
    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        if category == "wallet":
            trainers = load_trainers()
            user_id = str(interaction.user.id)
            if user_id not in trainers:
                await interaction.response.send_message("You need to register first!", ephemeral=True)
                return
            trainer = trainers[user_id]
            user_name = interaction.user.display_name
            user_avatar = interaction.user.display_avatar.url
            pokécoins = trainer.get("pokécoins", 0)
            shards = trainer.get("Shards", 0)
            battle_passes = trainer.get("BattlePasses", 0)
            embed = discord.Embed(
                title=f"{user_name}'s balance",
                color=0xFFD700
            )
            balance_text = (
                f"**<:pokecoins:1403472605620732099> pokécoins**\n{pokécoins}\n\n"
                f"**<:gems:1390696438383509555> Gems**\n{shards}\n\n"
                f"**<:battle_pass:1390698653215363082> Battle Passes**\n{battle_passes}"
            )
            embed.add_field(name="", value=balance_text, inline=False)
            embed.set_thumbnail(url=user_avatar)
            await interaction.response.edit_message(embed=embed, view=None)
        elif category == "hunting":
            trainers = load_trainers()
            user_id = str(interaction.user.id)
            trainer = trainers.get(user_id, {})
            inventory = trainer.get("inventory", {})
            hunting_items = {}
            hunting_item_names = ["Summoning Stone"]
            for item_name, quantity in inventory.items():
                if item_name in hunting_item_names:
                    hunting_items[item_name] = quantity
            total_items = sum(hunting_items.values())
            embed = discord.Embed(
                title="🎯 Hunting Items",
                description=f"Total Items = {total_items}",
                color=0xFFD700
            )
            if hunting_items:
                items_text = ""
                for item_name, quantity in hunting_items.items():
                    item_emoji = "🎯"
                    for shop_item in SHOP_ITEMS.values():
                        if shop_item["name"] == item_name:
                            item_emoji = shop_item["emoji"]
                            break
                    items_text += f"{item_emoji} **{item_name}** x{quantity}\n"
                embed.add_field(
                    name="📋 Items",
                    value=items_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="📋 Items",
                    value="No hunting items found. Visit the shop to purchase hunting items!",
                    inline=False
                )
            await interaction.response.edit_message(embed=embed)
        elif category == "held":
            trainers = load_trainers()
            user_id = str(interaction.user.id)
            trainer = trainers.get(user_id, {})
            inventory = trainer.get("inventory", {})
            held_items = {}
            shop_item_names = [item["name"] for item in SHOP_ITEMS.values()]
            hunting_item_names = ["Summoning Stone"]
            for item_name, quantity in inventory.items():
                if item_name in shop_item_names and item_name not in hunting_item_names:
                    held_items[item_name] = quantity
            total_items = sum(held_items.values())
            embed = discord.Embed(
                title="📦 Held Items & Battle Items",
                description=f"Total Items = {total_items}",
                color=0xFFD700
            )
            if held_items:
                items_text = ""
                for item_name, quantity in held_items.items():
                    item_emoji = "📦"
                    for shop_item in SHOP_ITEMS.values():
                        if shop_item["name"] == item_name:
                            item_emoji = shop_item["emoji"]
                            break
                    items_text += f"{item_emoji} **{item_name}** x{quantity}\n"
                embed.add_field(
                    name="📋 Items",
                    value=items_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="📋 Items",
                    value="No items found. Visit the shop to purchase items!",
                    inline=False
                )
            await interaction.response.edit_message(embed=embed)
        else:
            await interaction.response.send_message(f"Selected category: {category} (Feature coming soon!)", ephemeral=True)
class InventoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(InventoryDropdown())


@bot.command()
async def inventory(ctx):
    if not is_trainer_registered(ctx.author.id):
        embed = discord.Embed(
            title="Not Registered",
            description="You need to register first!\n\nUse: `@Pokékiro register`",
            color=0xe74c3c
        )
        await ctx.send(embed=embed)
        return
    trainers = load_trainers()
    user_id = str(ctx.author.id)
    if "pokécoins" not in trainers[user_id]:
        trainers[user_id]["pokécoins"] = 0
        save_trainers(trainers)
    trainer = trainers[user_id]
    trainer_id = trainer.get("TrainerID", "Unknown")
    pokécoins_amount = trainer.get("pokécoins", 0)
    embed = discord.Embed(
        title="📦 Your Inventory",
        description="Select a category from the dropdown below to view your items.",
        color=0xFFD700
    )
    categories_text = (
        "📋 **Categories**\n\n"
        "**Hunting Items**\n"
        "Total Items = 0\n\n"
        "**Stones & Fossils**\n"
        "Total Items = 0\n\n"
        "**Held Items & Battle Items**\n"
        "Total Items = 0\n\n"
        "**Nature Mints & Healing Items**\n"
        "Total Items = 0\n\n"
        "**Key Items & Valuable Items**\n"
        "Total Items = 0\n\n"
        "**TM/HM & Barriers**\n"
        "Total Items = 0\n\n"
        f"**Wallet & Passes**\n"
        f"pokécoins = {pokécoins_amount}\n\n"
        "**Energy Capsule & Chest**\n"
        "Total Items = 0\n\n"
        "📊 **Summary**\n\n"
        "**Total Items Across All Categories: 53**"
    )
    embed.add_field(name="", value=categories_text, inline=False)
    embed.set_footer(text=f"Trainer ID: {trainer_id} • Use the dropdown to explore categories")
    view = InventoryView()
    await ctx.send(embed=embed, view=view)
@bot.command()
async def catch(ctx, *, pokemon_name: str):
    global current_spawn
    if current_spawn is None:
        await ctx.send("❌ No Pokémon has spawned! Wait for one to appear.")
        return
    spawn_data = current_spawn
    if spawn_data["name"].lower() != pokemon_name.lower():
        await ctx.send(f"❌ That's not the right Pokémon! Try guessing again.")
        return
    if spawn_data.get("caught", False):
        await ctx.send("❌ This Pokémon has already been caught!")
        return
    trainers = load_trainers()
    user_id = str(ctx.author.id)
    if user_id not in trainers:
        await ctx.send("❌ You need to register first! Use `@Pokékiro register [Male/Female]` to get started.")
        return
    if "CaughtPokemons" not in trainers[user_id]:
        trainers[user_id]["CaughtPokemons"] = []
    matched = next((p for p in POKEMON_GEN1 if p["name"].lower() == spawn_data["name"].lower()), None)
    dex = matched["dex"] if matched and "dex" in matched else 0
    gender_symbol = {
        "male": "<:male:1400956267979214971>",
        "female": "<:female:1400956073573224520>",
        "genderless": "<:unknown:1401145566863560755>"
    }.get(spawn_data["gender"].lower(), "❔")
    if "full_data" in spawn_data:
        complete_pokemon = spawn_data["full_data"]
        trainers[user_id]["CaughtPokemons"].append(complete_pokemon)
    else:
        trainers[user_id]["CaughtPokemons"].append({
            "dex": dex,
            "name": spawn_data["name"],
            "gender": gender_symbol,
            "level": spawn_data["level"],
            "iv_percentage": spawn_data["total_iv"]
        })
    if "pokécoins" not in trainers[user_id]:
        trainers[user_id]["pokécoins"] = 0
    trainers[user_id]["pokécoins"] += 50
    save_trainers(trainers)
    spawn_data["caught"] = True
    current_spawn = None
    if "full_data" in spawn_data:
        pokemon_data = spawn_data["full_data"]
        success_message = f"Congratulations <@{ctx.author.id}>! You caught a Level {pokemon_data['level']} {pokemon_data['name'].title()}{pokemon_data['gender']} ({pokemon_data['iv_percentage']}%) you received 50 Pokécoins <:pokecoins:1403472605620732099>!"
        await ctx.send(success_message)
    else:
        await ctx.send(
            f"Congratulations <@{ctx.author.id}>! "
            f"You caught a Level {spawn_data['level']} {spawn_data['name']}{gender_symbol} "
            f"({spawn_data['total_iv']}%) you received 50 Pokécoins <:pokecoins:1403472605620732099>!"
        )
@bot.command()
async def release(ctx, order_number: int):
    trainers = load_trainers()
    user_id = str(ctx.author.id)
    if user_id not in trainers:
        await ctx.send("You are not registered yet.")
        return
    pokemon_list = get_user_pokemon_list(trainers[user_id])
    if not pokemon_list:
        await ctx.send("You have no Pokémon to release.")
        return
    selected_pokemon = None
    for pokemon in pokemon_list:
        if pokemon["order"] == order_number:
            selected_pokemon = pokemon
            break
    if not selected_pokemon:
        await ctx.send("Invalid Pokémon order number.")
        return
    trainer_data = trainers[user_id]
    currently_selected = trainer_data.get("SelectedPokemon")
    if currently_selected and currently_selected.get("order") == order_number:
        await ctx.send("You cannot release your selected pokémon!")
        return
    pokemon_data = selected_pokemon["data"]
    gender_emoji = pokemon_data.get("gender", "<:unknown:1401145566863560755>")
    if gender_emoji in ["<:male:1400956267979214971>", "<:female:1400956073573224520>", "<:unknown:1401145566863560755>"]:
        gender_symbol = gender_emoji
    else:
        gender_symbol = convert_text_gender_to_emoji(str(gender_emoji))
    msg_text = (
        f">>> Are you sure you want to **release** your Level {pokemon_data.get('level', 1)} "
        f"{pokemon_data['name']}{gender_symbol} ({pokemon_data.get('iv_percentage', 0)}%) "
        f"No. {order_number} for **1,000,000 pokécoins**?"
    )
    view = View()
    async def confirm_callback(interaction):
        trainers = load_trainers()
        if user_id in trainers:
            success = False
            if selected_pokemon["type"] == "starter":
                if trainers[user_id].get("StarterPokemon"):
                    trainers[user_id]["StarterPokemon"] = None
                    success = True
            elif selected_pokemon["type"] == "caught":
                if "CaughtPokemons" in trainers[user_id]:
                    caught_index = selected_pokemon["order"] - 2
                    if 0 <= caught_index < len(trainers[user_id]["CaughtPokemons"]):
                        trainers[user_id]["CaughtPokemons"].pop(caught_index)
                        success = True
            if success:
                current_coins = get_user_pokecoins(trainers[user_id])
                trainers[user_id]["pokécoins"] = current_coins + 1000000
                currently_selected = trainers[user_id].get("SelectedPokemon")
                if currently_selected and currently_selected.get("order") == selected_pokemon["order"]:
                    trainers[user_id]["SelectedPokemon"] = None
                save_trainers(trainers)
                view.clear_items()
                await interaction.response.edit_message(
                    content="✅ You released 1 Pokémon. You received **1,000,000 pokécoins!**",
                    view=None
                )
            else:
                await interaction.response.edit_message(
                    content="Release failed. Pokémon not found.",
                    view=None
                )
        else:
            await interaction.response.edit_message(
                content="Release failed. Pokémon not found.",
                view=None
            )
    async def cancel_callback(interaction):
        view.clear_items()
        await interaction.response.edit_message(
            content="Aborted.",
            view=None
        )
    confirm_btn = Button(label="Confirm", style=discord.ButtonStyle.green)
    confirm_btn.callback = confirm_callback
    cancel_btn = Button(label="Cancel", style=discord.ButtonStyle.red)
    cancel_btn.callback = cancel_callback
    view.add_item(confirm_btn)
    view.add_item(cancel_btn)
    await ctx.send(content=msg_text, view=view)
@bot.command(name="buy")
async def buy_command(ctx, *, args: str = None):
    user_id = str(ctx.author.id)
    if not is_trainer_registered(user_id):
        await ctx.send("You are not registered as a trainer. Use the register command first.")
        return
    if not args:
        await ctx.send("Please specify an item to buy. Examples:\n`@Pokékiro#8400 buy gems 5`\n`@Pokékiro#8400 buy summoning stone 1`\n`@Pokékiro#8400 buy rare candy 1`")
        return
    parts = args.strip().split()
    if len(parts) == 0:
        await ctx.send("Please specify an item to buy.")
        return
    amount = 1
    if len(parts) > 1 and parts[-1].isdigit():
        amount = int(parts[-1])
        item_name = " ".join(parts[:-1])
        if amount <= 0:
            await ctx.send("Amount must be a positive number.")
            return
    else:
        item_name = " ".join(parts)
    trainer_data = get_trainer_data(user_id)
    if not trainer_data:
        await ctx.send("Unable to retrieve trainer data.")
        return
    item_key = item_name.lower()
    if item_key == "gems" or item_key == "gem":
        gem_price = 400
        total_cost = gem_price * amount
        current_coins = get_user_pokecoins(trainer_data)
        if current_coins < total_cost:
            await ctx.send(f"Not enough pokécoins! You have {current_coins} pokécoins but need {total_cost} pokécoins to buy {amount} gems.")
            return
        confirmation_view = PurchaseConfirmationView(ctx.author.id, "Gems", amount, total_cost, "pokécoins", is_gems=True)
        await ctx.send(f"Are you sure you want to buy {amount} Gems?", view=confirmation_view)
        return
    if item_key not in SHOP_ITEMS:
        matched_item = None
        for shop_key, shop_item in SHOP_ITEMS.items():
            if item_key == shop_key or shop_item["name"].lower() == item_key:
                matched_item = shop_key
                break
            elif "summoning stone" in item_key and shop_key == "summoning stone":
                matched_item = shop_key
                break
        if matched_item:
            item_key = matched_item
        else:
            available_items = ", ".join([item["name"] for item in SHOP_ITEMS.values()])
            await ctx.send(f"Item not found in shop. Available items: {available_items}, gems")
            return
    item = SHOP_ITEMS[item_key]
    total_cost = item["price"] * amount
    currency = item.get("currency", "pokécoins")
    if currency == "gems":
        current_balance = trainer_data.get("Shards", 0)
        if current_balance < total_cost:
            await ctx.send("You not have enough Gems to buy Summoning Stone.")
            return
    else:
        current_coins = get_user_pokecoins(trainer_data)
        if current_coins < total_cost:
            await ctx.send(f"Not enough pokécoins! You have {current_coins} pokécoins but need {total_cost} pokécoins.")
            return
    if item_key == "summoning stone":
        confirmation_view = PurchaseConfirmationView(ctx.author.id, item["name"], amount, total_cost, currency)
        await ctx.send(f"Are you sure you want to buy {item['name']}?", view=confirmation_view)
        return
    if currency == "pokécoins":
        if deduct_pokecoins(trainer_data, total_cost):
            add_item_to_inventory(trainer_data, item["name"], amount)
            if update_trainer_data(user_id, trainer_data):
                await ctx.send(f"✅ You purchased {amount} {item['name']}! Use `@Pokékiro#8400 inventory` to check your item.")
            else:
                await ctx.send("Failed to save purchase. Please try again.")
        else:
            await ctx.send("Purchase failed. Please try again.")
@bot.command(name="select")
async def select_pokemon(ctx, order_number: int):
    user_id = str(ctx.author.id)
    if not is_trainer_registered(user_id):
        await ctx.send("You need to register first! Use `@Pokékiro#8400 register` to get started.")
        return
    trainer_data = get_trainer_data(user_id)
    if not trainer_data:
        await ctx.send("Unable to retrieve trainer data.")
        return
    selected_pokemon = get_pokemon_by_order(trainer_data, order_number)
    if not selected_pokemon:
        await ctx.send(f"No Pokemon found with order number {order_number}. Use `@Pokékiro#8400 pokémons` to see your collection.")
        return
    trainer_data["SelectedPokemon"] = {
        "order": selected_pokemon["order"],
        "name": selected_pokemon["name"],
        "type": selected_pokemon["type"]
    }
    if update_trainer_data(user_id, trainer_data):
        pokemon_data = selected_pokemon["data"]
        pokemon_level = pokemon_data.get("level", 1)
        embed = discord.Embed(
            title="🎯 Pokemon Selected!",
            description=f"You selected **{selected_pokemon['name']}** (Level {pokemon_level}) from your collection.\n\nThis Pokemon will now receive XP when you level up!",
            color=0xFFD700
        )
        if "emoji" in pokemon_data:
            embed.add_field(name="Pokemon", value=f"{pokemon_data['emoji']} {selected_pokemon['name']}", inline=True)
        else:
            embed.add_field(name="Pokemon", value=selected_pokemon['name'], inline=True)
        embed.add_field(name="Order #", value=f"#{order_number}", inline=True)
        embed.add_field(name="Level", value=pokemon_level, inline=True)
        if selected_pokemon["type"] == "starter":
            embed.set_footer(text="💡 This is your starter Pokemon!")
        else:
            embed.set_footer(text="💡 This is from your caught Pokemon collection!")
        await ctx.send(embed=embed)
    else:
        await ctx.send("Failed to select Pokemon. Please try again.")
valid_names = [p["name"].lower() for p in POKEMON_GEN1]
@bot.event
async def on_ready():
    if hasattr(bot, '_ready_called'):
        return
    bot._ready_called = True
    print(f"{bot.user} has connected to Discord!")
    if not os.path.exists("trainers.json"):
        with open("trainers.json", "w") as f:
            json.dump({}, f)
        print("📁 Created trainers.json file")
    print("🎮 Pokemon trainer registration system is ready!")
processed_messages = set()
@bot.event
async def on_message(message):
    global message_count, current_spawn
    if message.author.bot:
        return
    
    # Stronger duplicate detection using just message ID 
    message_id = str(message.id)
    if message_id in processed_messages:
        print(f"DUPLICATE MESSAGE DETECTED: {message_id} - SKIPPING")
        return
    processed_messages.add(message_id)
    
    # Keep only last 1000 processed messages for better duplicate detection
    if len(processed_messages) > 1000:
        old_messages = list(processed_messages)[:100]
        for old_msg in old_messages:
            processed_messages.discard(old_msg)
    
    
    await bot.process_commands(message)
    if is_trainer_registered(message.author.id):
        save_success, level_up_info = update_trainer_xp(message.author.id)
        if level_up_info is not None:
            embed = discord.Embed(
                title="🎉 Level Up!",
                description=f"Congratulations {message.author.display_name}\nYour {level_up_info['pokemon_name']} is now level {level_up_info['new_level']}!",
                color=0xFFD700
            )
            embed.set_thumbnail(url=get_pokemon_image_url(level_up_info['pokemon_name']))
            embed.set_footer(text="Keep chatting to level up more!")
            await message.channel.send(embed=embed)
    message_count += 1
    if message_count >= 10:
        message_count = 0
        spawn_roll = random.random()
        if spawn_roll < 0.90:
            all_pokemon = get_all_pokemon()
            pokemon_choice = random.choice(all_pokemon)
            spawned_pokemon = create_spawned_pokemon(pokemon_choice)
            current_spawn = {
                "name": spawned_pokemon["name"],
                "level": spawned_pokemon["level"],
                "gender": spawned_pokemon["gender"],
                "total_iv": spawned_pokemon["iv_percentage"],
                "caught": False,
                "full_data": spawned_pokemon
            }
            embed = discord.Embed(
                title="A wild pokémon has appeared!",
                description=f"Guess the pokémon and type `@Pokékiro catch <pokémon>` to catch it!",
                color=0xFFD700
            )
            embed.set_image(url=get_pokemon_image_url(spawned_pokemon['name']))
            await message.channel.send(embed=embed)
@bot.command(name='hint')
async def hint_command(ctx):
    global current_spawn
    if current_spawn is None:
        embed = discord.Embed(
            title="No Pokemon Spawned",
            description="There's no Pokemon currently spawned! Wait for one to appear or keep chatting.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    if current_spawn.get("caught", False):
        embed = discord.Embed(
            title="Pokemon Already Caught",
            description="The spawned Pokemon has already been caught! Wait for a new one to appear.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    pokemon_name = current_spawn["name"].title()
    embed = discord.Embed(
        title="🔍 Pokemon Hint",
        description=f"The pokémon is ||{pokemon_name}||",
        color=0x3498db
    )
    embed.set_footer(text="Click the spoiler to reveal the answer!")
    await ctx.send(embed=embed)
@bot.group(name='market', invoke_without_command=True)
async def market_command(ctx):
    market_data = load_market()
    listings = market_data.get("listings", [])
    view = MarketplacePagination(listings)
    embed = view.create_embed()
    await ctx.send(embed=embed, view=view)
@market_command.command(name='add')
async def market_add(ctx, order_number: str = None, amount: int = None):
    if order_number is None or amount is None:
        await ctx.send("Please specify both order number and amount. Example: `market add 1 500`")
        return
    trainer_data = get_trainer_data(ctx.author.id)
    if not trainer_data:
        await ctx.send("You need to register first using the `register` command.")
        return
    if amount <= 0:
        await ctx.send("Amount must be a positive number.")
        return
    try:
        order_int = int(order_number)
    except ValueError:
        await ctx.send("Order number must be a valid number.")
        return
    pokemon_data = get_pokemon_by_order(trainer_data, order_int)
    if not pokemon_data:
        await ctx.send("No Pokémon found with that order number. Use `pokémons` to see your collection.")
        return
    pokemon = pokemon_data["data"]
    confirmation_message = f"Are you sure you want to list your **Level {pokemon['level']} {pokemon['name'].title()}{pokemon['gender']} ({pokemon['iv_percentage']}%) No. {order_int}** for **{amount}** Pokécoins?"
    view = MarketConfirmationView(ctx.author.id, pokemon_data, order_int, amount)
    await ctx.reply(confirmation_message, view=view)
@market_command.command(name="remove")
async def market_remove(ctx, listing_id: int = None):
    if listing_id is None:
        await ctx.send("Please specify a listing ID. Example: `market remove 1`")
        return
    user_id = str(ctx.author.id)
    if not is_trainer_registered(user_id):
        await ctx.send("You need to register first! Use `register` to get started.")
        return
    market_data = load_market()
    listings = market_data.get("listings", [])
    listing_to_remove = None
    listing_index = None
    for i, listing in enumerate(listings):
        if listing["market_id"] == listing_id and listing["user_id"] == user_id:
            listing_to_remove = listing
            listing_index = i
            break
    if not listing_to_remove:
        await ctx.send("No listing found with that ID, or it's not your listing.")
        return
    pokemon = listing_to_remove["pokemon"]
    confirmation_message = f"Are you sure you want to remove your **Level {pokemon['level']} {pokemon['name'].title()}{pokemon['gender']} ({pokemon['iv_percentage']}%)** from the market?"
    view = MarketRemovalConfirmationView(ctx.author.id, listing_to_remove, listing_index)
    await ctx.reply(confirmation_message, view=view)
class MarketRemovalConfirmationView(View):
    def __init__(self, user_id: int, listing: dict, listing_index: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.listing = listing
        self.listing_index = listing_index
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm_removal(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your confirmation dialog.", ephemeral=True)
            return
        market_data = load_market()
        if self.listing_index < len(market_data["listings"]):
            removed_listing = market_data["listings"].pop(self.listing_index)
            if save_market(market_data):
                trainer_data = get_trainer_data(str(self.user_id))
                if trainer_data:
                    if "CaughtPokemons" not in trainer_data:
                        trainer_data["CaughtPokemons"] = []
                    trainer_data["CaughtPokemons"].append(self.listing["pokemon"])
                    if update_trainer_data(str(self.user_id), trainer_data):
                        pokemon = self.listing["pokemon"]
                        success_message = f"Removed your Level {pokemon['level']} {pokemon['name'].title()}{pokemon['gender']} ({pokemon['iv_percentage']}%) from the market."
                        await interaction.response.edit_message(view=None)
                        await interaction.followup.send(success_message)
                    else:
                        await interaction.response.edit_message(view=None)
                        await interaction.followup.send("Failed to return Pokemon to your collection. Please contact support.")
                else:
                    await interaction.response.edit_message(view=None)
                    await interaction.followup.send("Failed to retrieve your trainer data. Please try again.")
            else:
                await interaction.response.edit_message(view=None)
                await interaction.followup.send("Failed to remove listing from market. Please try again.")
        else:
            await interaction.response.edit_message(view=None)
            await interaction.followup.send("Listing no longer exists.")
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_removal(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your confirmation dialog.", ephemeral=True)
            return
        await interaction.response.edit_message(view=None)
        await interaction.followup.send("Removal cancelled.")
class MarketBuyConfirmView(View):
    def __init__(self, listing, buyer_id):
        super().__init__(timeout=60.0)
        self.listing = listing
        self.buyer_id = buyer_id
    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.green, emoji='✅')
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.buyer_id:
            await interaction.response.send_message("You can't interact with someone else's confirmation.", ephemeral=True)
            return
        market_data = load_market()
        listing_found = None
        listing_index = -1
        for i, listing in enumerate(market_data["listings"]):
            if listing["market_id"] == self.listing["market_id"]:
                listing_found = listing
                listing_index = i
                break
        if not listing_found:
            await interaction.response.send_message("This listing is no longer available.", ephemeral=True)
            return
        buyer_data = get_trainer_data(self.buyer_id)
        if not buyer_data:
            await interaction.response.send_message("You need to register first!", ephemeral=True)
            return
        buyer_coins = get_user_pokecoins(buyer_data)
        if buyer_coins < self.listing["amount"]:
            await interaction.response.send_message(f"You don't have enough Pokécoins! You need {self.listing['amount']:,} but only have {buyer_coins:,}.", ephemeral=True)
            return
        if not deduct_pokecoins(buyer_data, self.listing["amount"]):
            await interaction.response.send_message("Failed to deduct Pokécoins. Please try again.", ephemeral=True)
            return
        if "CaughtPokemons" not in buyer_data:
            buyer_data["CaughtPokemons"] = []
        buyer_data["CaughtPokemons"].append(self.listing["pokemon"])
        market_data["listings"].pop(listing_index)
        if update_trainer_data(self.buyer_id, buyer_data) and save_market(market_data):
            pokemon = self.listing["pokemon"]
            success_message = f"You purchased a Level {pokemon['level']} {pokemon['name']}{pokemon['gender']} ({pokemon['iv_percentage']}%) from the market (Listing #{self.listing['market_id']}) for {self.listing['amount']:,} Pokécoins. Do @Pokékiro#8400 info latest to view it!"
            await interaction.response.send_message(success_message)
        else:
            await interaction.response.send_message("Failed to complete the purchase. Please try again.", ephemeral=True)
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)
    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.buyer_id:
            await interaction.response.send_message("You can't interact with someone else's confirmation.", ephemeral=True)
            return
        await interaction.response.send_message("Aborted.")
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)
@market_command.command(name='buy')
async def market_buy(ctx, listing_id: int = None):
    if listing_id is None:
        embed = discord.Embed(
            title="Missing Parameters",
            description="Please specify a listing ID. Example: `market buy 1`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    if not is_trainer_registered(ctx.author.id):
        embed = discord.Embed(
            title="Not Registered",
            description="You need to register first!\n\nUse: `@Pokékiro register [Male/Female]`",
            color=0xe74c3c
        )
        await ctx.send(embed=embed)
        return
    market_data = load_market()
    listings = market_data.get("listings", [])
    listing_found = None
    for listing in listings:
        if listing["market_id"] == listing_id:
            listing_found = listing
            break
    if not listing_found:
        embed = discord.Embed(
            title="Listing Not Found",
            description=f"Listing #{listing_id} not found!",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    if listing_found["user_id"] == str(ctx.author.id):
        await ctx.send("You can't purchase your own listing!")
        return
    buyer_data = get_trainer_data(ctx.author.id)
    if not buyer_data:
        await ctx.send("Trainer data not found!")
        return
    buyer_coins = get_user_pokecoins(buyer_data)
    pokemon = listing_found["pokemon"]
    embed = discord.Embed(
        title="💰 Purchase Confirmation",
        description=f"Are you sure you want to buy this Level {pokemon['level']} {pokemon['name']}{pokemon['gender']} ({pokemon['iv_percentage']}%) (Listing #{listing_id}) for {listing_found['amount']:,} Pokécoins?",
        color=0x3498db
    )
    pokemon_info = f"**Level {pokemon['level']} {pokemon['name']}{pokemon['gender']}**\n"
    pokemon_info += f"IV: {pokemon['iv_percentage']}% | Nature: {pokemon['nature'].title()}\n"
    pokemon_info += f"**Price:** {listing_found['amount']:,} Pokécoins\n"
    pokemon_info += f"**Your Pokécoins:** {buyer_coins:,}"
    if buyer_coins < listing_found['amount']:
        pokemon_info += f"\n**You need {listing_found['amount'] - buyer_coins:,} more Pokécoins!**"
        embed.color = 0xe74c3c
    embed.add_field(name="Purchase Details", value=pokemon_info, inline=False)
    if buyer_coins >= listing_found['amount']:
        view = MarketBuyConfirmView(listing_found, ctx.author.id)
        await ctx.send(embed=embed, view=view)
    else:
        await ctx.send(embed=embed)
@market_command.command(name='info')
async def market_info(ctx, listing_id: int = None):
    if listing_id is None:
        embed = discord.Embed(
            title="Missing Parameters",
            description="Please specify a listing ID. Example: `@Pokékiro#8400 market info 38116209`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    market_data = load_market()
    listing_found = None
    for listing in market_data["listings"]:
        if listing["market_id"] == listing_id:
            listing_found = listing
            break
    if not listing_found:
        embed = discord.Embed(
            title="❌ Listing Not Found",
            description=f"No Pokemon found with market ID {listing_id}.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    pokemon = listing_found["pokemon"]
    seller_id = listing_found["user_id"]
    try:
        seller = await bot.fetch_user(int(seller_id))
        seller_name = seller.name
        seller_avatar = seller.avatar.url if seller.avatar else seller.default_avatar.url
    except:
        seller_name = "Unknown User"
        seller_avatar = None
    current_level = pokemon["level"]
    current_xp = pokemon.get("xp", 0)
    xp_required_for_current_level = current_level * 50
    pokemon_moves = ["None"]
    embed = discord.Embed(
        title=f"Level {pokemon['level']} {pokemon['name'].title()}",
        color=0xFFD700
    )
    embed.set_author(name=seller_name, icon_url=seller_avatar)
    xp_to_next_level = xp_required_for_current_level - current_xp
    details_text = f"**XP:** {current_xp}/{xp_required_for_current_level} ({xp_to_next_level} XP to next level)\n"
    details_text += f"**Nature:** {pokemon['nature'].title()}\n"
    details_text += f"**Ability:** {pokemon.get('ability', 'Unknown')}\n"
    gender_emoji = pokemon.get('gender', '<:unknown:1401145566863560755>')
    if gender_emoji == '<:male:1400956267979214971>':
        gender_display = gender_emoji
    elif gender_emoji == '<:female:1400956073573224520>':
        gender_display = gender_emoji
    elif gender_emoji == '<:unknown:1401145566863560755>':
        gender_display = gender_emoji
    else:
        gender_display = convert_text_gender_to_emoji(str(gender_emoji))
    details_text += f"**Gender:** {gender_display}\n"
    embed.add_field(name="Details", value=details_text, inline=False)
    stats_text = ""
    ivs = pokemon.get("ivs", {})
    calculated_stats = pokemon.get("calculated_stats", {})
    stat_names = [
        ("HP", "hp"),
        ("Attack", "attack"),
        ("Defense", "defense"),
        ("Sp. Atk", "sp_attack"),
        ("Sp. Def", "sp_defense"),
        ("Speed", "speed")
    ]
    for display_name, stat_key in stat_names:
        stat_value = calculated_stats.get(stat_key, 0)
        iv_value = ivs.get(stat_key, 0)
        stats_text += f"**{display_name}:** {stat_value} – IV: {iv_value}/31\n"
    total_ivs = sum(ivs.values()) if ivs else 0
    iv_percentage = pokemon.get("iv_percentage", (total_ivs / 186) * 100)
    stats_text += f"**Total IV:** {iv_percentage:.2f}%"
    embed.add_field(name="Stats", value=stats_text, inline=False)
    embed.add_field(name="Current Moves", value="None", inline=False)
    listing_text = f"**ID:** {listing_found['market_id']}\n"
    listing_text += f"**Price:** {listing_found['amount']:,} pc"
    embed.add_field(name="Market Listing", value=listing_text, inline=False)
    embed.set_image(url=get_pokemon_image_url(pokemon["name"]))
    await ctx.send(embed=embed)
active_trades = {}
class TradeRequestView(View):
    def __init__(self, requester_id: int, target_id: int):
        super().__init__(timeout=300)
        self.requester_id = requester_id
        self.target_id = target_id
        self.trade_accepted = False
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_trade(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.target_id:
            await interaction.response.send_message("This trade request is not for you!", ephemeral=True)
            return
        self.trade_accepted = True
        requester = interaction.guild.get_member(self.requester_id)
        target = interaction.guild.get_member(self.target_id)
        if not requester:
            try:
                requester = await interaction.client.fetch_user(self.requester_id)
            except:
                pass
        if not target:
            try:
                target = await interaction.client.fetch_user(self.target_id)
            except:
                pass
        if hasattr(requester, 'display_name'):
            requester_name = requester.display_name
        elif hasattr(requester, 'name'):
            requester_name = requester.name
        else:
            requester_name = "User"
        if hasattr(target, 'display_name'):
            target_name = target.display_name
        elif hasattr(target, 'name'):
            target_name = target.name
        else:
            target_name = "User"
        embed = discord.Embed(
            title=f"Trade between {requester_name} & {target_name}",
            color=0xFFD700
        )
        trade_key = f"{self.requester_id}_{self.target_id}"
        alt_trade_key = f"{self.target_id}_{self.requester_id}"
        trade_data = active_trades.get(trade_key, active_trades.get(alt_trade_key, {
            "requester_pokécoins": 0,
            "target_pokécoins": 0,
            "requester_pokemon": [],
            "target_pokemon": [],
            "requester_confirmed": False,
            "target_confirmed": False
        }))
        requester_display = "None"
        if trade_data.get("requester_pokécoins", 0) > 0:
            requester_display = f"{trade_data['requester_pokécoins']:,} Pokécoins <:pokecoins:1403472605620732099>"
        target_display = "None"
        if trade_data.get("target_pokécoins", 0) > 0:
            target_display = f"{trade_data['target_pokécoins']:,} Pokécoins <:pokecoins:1403472605620732099>"
        requester_dot = "🟢" if trade_data.get("requester_confirmed", False) else "🔴"
        target_dot = "🟢" if trade_data.get("target_confirmed", False) else "🔴"
        embed.add_field(
            name=f"{requester_dot} " + requester_name,
            value=requester_display,
            inline=False
        )
        embed.add_field(
            name=f"{target_dot} " + target_name,
            value=target_display,
            inline=False
        )
        embed.add_field(
            name="Page Info",
            value="Showing page 1 out of 1.",
            inline=False
        )
        embed.add_field(
            name="⚠️ Important Reminder",
            value="Trading Pokécoins or Pokémon for real-life currencies or items in other bots is prohibited and will result in the suspension of your Pokékiro account!",
            inline=False
        )
        trade_key = f"{self.requester_id}_{self.target_id}"
        alt_trade_key = f"{self.target_id}_{self.requester_id}"
        if trade_key in active_trades:
            active_trades[trade_key]["trade_embed"] = embed
            active_trades[trade_key]["trade_message"] = interaction.message
        elif alt_trade_key in active_trades:
            active_trades[alt_trade_key]["trade_embed"] = embed
            active_trades[alt_trade_key]["trade_message"] = interaction.message
        await interaction.response.edit_message(content="", embed=embed, view=None)
    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject_trade(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.target_id:
            await interaction.response.send_message("This trade request is not for you!", ephemeral=True)
            return
        await interaction.response.edit_message(content="Trade rejected.", view=None)
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(content="Trade request expired.", view=self)
        except:
            pass
@bot.group(invoke_without_command=True)
async def trade(ctx, *, arg=None):
    if arg is None:
        await ctx.send("Usage: `trade @user`")
        return
    try:
        user = await commands.MemberConverter().convert(ctx, arg.strip())
        if user.id == ctx.author.id:
            await ctx.send("You can't trade with yourself!")
            return
        if user.bot:
            await ctx.send("You can't trade with bots nigga !!! 🤡")
            return
        requester_data = get_trainer_data(ctx.author.id)
        if not requester_data:
            await ctx.send(f"<@{ctx.author.id}> You need to register first! Use `register [Male/Female]` to get started.")
            return
        target_data = get_trainer_data(user.id)
        if not target_data:
            await ctx.send(f"<@{user.id}> needs to register first before they can trade!")
            return
        user_id = ctx.author.id
        for trade_data in active_trades.values():
            if trade_data["requester_id"] == user_id or trade_data["target_id"] == user_id:
                await ctx.send("You are already in trade")
                return
        trade_key = f"{ctx.author.id}_{user.id}"
        active_trades[trade_key] = {
            "requester_pokécoins": 0,
            "target_pokécoins": 0,
            "requester_pokemon": [],
            "target_pokemon": [],
            "requester_id": ctx.author.id,
            "target_id": user.id,
            "trade_message": None,
            "trade_embed": None,
            "requester_confirmed": False,
            "target_confirmed": False
        }
        view = TradeRequestView(ctx.author.id, user.id)
        message = await ctx.send(
            f"Requesting a trade with <@{user.id}>. Click the accept button to accept!",
            view=view
        )
        view.message = message
    except commands.MemberNotFound:
        await ctx.send("User not found! Make sure to mention a valid user.")
    except Exception as e:
        await ctx.send("Invalid command. Use `trade @user`")
@trade.command(name="add")
async def trade_add(ctx, *args):
    if not args:
        await ctx.send("Usage: `trade add pokécoins <amount>` or `trade add <order_number(s)>`\nExamples:\n• `trade add pokécoins 1000`\n• `trade add 1` - Add one Pokemon\n• `trade add 1 2 3` - Add multiple Pokemon")
        return
    item_type = args[0]
    amount = args[1] if len(args) > 1 else None
    if item_type.lower() in ["pokécoins", "pokecoins"]:
        if amount is None:
            await ctx.send("Please specify the amount of pokécoins. Example: `trade add pokécoins 1000`")
            return
        try:
            amount_int = int(amount)
            if amount_int <= 0:
                await ctx.send("Amount must be positive!")
                return
        except ValueError:
            await ctx.send("Please enter a valid number for pokécoins amount.")
            return
        requester_data = get_trainer_data(ctx.author.id)
        if not requester_data:
            await ctx.send(f"<@{ctx.author.id}> You need to register first! Use `register [Male/Female]` to get started.")
            return
        user_coins = get_user_pokecoins(requester_data)
        if user_coins < amount_int:
            await ctx.send(f"You don't have enough pokécoins! You have {user_coins:,}, but need {amount_int:,}.")
            return
        user_id = ctx.author.id
        trade_found = None
        trade_key = None
        for key, trade_data in active_trades.items():
            if trade_data["requester_id"] == user_id or trade_data["target_id"] == user_id:
                trade_found = trade_data
                trade_key = key
                break
        if not trade_found:
            await ctx.send("You don't have an active trade! Start a trade first with `trade @user`")
            return
        if trade_found["requester_id"] == user_id:
            active_trades[trade_key]["requester_pokécoins"] += amount_int
        else:
            active_trades[trade_key]["target_pokécoins"] += amount_int
        trade_message = active_trades[trade_key].get("trade_message")
        if trade_message:
            trade_data = active_trades[trade_key]
            try:
                requester = ctx.guild.get_member(trade_data["requester_id"])
                target = ctx.guild.get_member(trade_data["target_id"])
                if not requester:
                    requester = await ctx.bot.fetch_user(trade_data["requester_id"])
                if not target:
                    target = await ctx.bot.fetch_user(trade_data["target_id"])
                requester_name = getattr(requester, 'display_name', getattr(requester, 'name', 'User'))
                target_name = getattr(target, 'display_name', getattr(target, 'name', 'User'))
                embed = discord.Embed(
                    title=f"Trade between {requester_name} & {target_name}",
                    color=0xFFD700
                )
                requester_display = []
                if trade_data.get("requester_pokécoins", 0) > 0:
                    requester_display.append(f"{trade_data['requester_pokécoins']:,} Pokécoins <:pokecoins:1403472605620732099>")
                requester_pokemon = trade_data.get("requester_pokemon", [])
                for pokemon_data in requester_pokemon:
                    requester_display.append(f"{pokemon_data['order']}    {pokemon_data['name']}    •    Lvl.{pokemon_data['level']}    {pokemon_data['iv_percent']}")
                target_display = []
                if trade_data.get("target_pokécoins", 0) > 0:
                    target_display.append(f"{trade_data['target_pokécoins']:,} Pokécoins <:pokecoins:1403472605620732099>")
                target_pokemon = trade_data.get("target_pokemon", [])
                for pokemon_data in target_pokemon:
                    target_display.append(f"{pokemon_data['order']}    {pokemon_data['name']}    •    Lvl.{pokemon_data['level']}    {pokemon_data['iv_percent']}")
                requester_display_text = "\n".join(requester_display) if requester_display else "None"
                target_display_text = "\n".join(target_display) if target_display else "None"
                requester_dot = "🟢" if trade_data.get("requester_confirmed", False) else "🔴"
                target_dot = "🟢" if trade_data.get("target_confirmed", False) else "🔴"
                embed.add_field(
                    name=f"{requester_dot} " + requester_name,
                    value=requester_display_text,
                    inline=False
                )
                embed.add_field(
                    name=f"{target_dot} " + target_name,
                    value=target_display_text,
                    inline=False
                )
                embed.add_field(
                    name="Page Info",
                    value="Showing page 1 out of 1.",
                    inline=False
                )
                embed.add_field(
                    name="⚠️ Important Reminder",
                    value="Trading Pokécoins or Pokémon for real-life currencies or items in other bots is prohibited and will result in the suspension of your Pokékiro account!",
                    inline=False
                )
                await trade_message.edit(embed=embed)
            except Exception as e:
                print(f"Error updating trade embed: {e}")
                await ctx.send(f"Added {amount_int:,} Pokécoins to your trade!")
        else:
            await ctx.send(f"Added {amount_int:,} Pokécoins to your trade!")
    else:
        try:
            order_numbers = [int(arg) for arg in args]
            for order_number in order_numbers:
                if order_number <= 0:
                    await ctx.send("All order numbers must be positive!")
                    return
        except ValueError:
            await ctx.send("Invalid item type. Use `trade add pokécoins <amount>` or `trade add <order_number(s)>`")
            return
        requester_data = get_trainer_data(ctx.author.id)
        if not requester_data:
            await ctx.send(f"<@{ctx.author.id}> You need to register first! Use `register [Male/Female]` to get started.")
            return
        pokemon_collection = []
        if requester_data.get("StarterPokemon"):
            pokemon_collection.append(requester_data["StarterPokemon"])
        if "CaughtPokemons" in requester_data and requester_data["CaughtPokemons"]:
            pokemon_collection.extend(requester_data["CaughtPokemons"])
        if not pokemon_collection:
            await ctx.send("You don't have any Pokémon to trade!")
            return
        user_id = ctx.author.id
        trade_found = None
        trade_key = None
        for key, trade_data in active_trades.items():
            if trade_data["requester_id"] == user_id or trade_data["target_id"] == user_id:
                trade_found = trade_data
                trade_key = key
                break
        if not trade_found:
            await ctx.send("You don't have an active trade! Start a trade first with `trade @user`")
            return
        added_pokemon = []
        skipped_pokemon = []
        for order_number in order_numbers:
            if order_number > len(pokemon_collection):
                skipped_pokemon.append(f"#{order_number} (invalid number)")
                continue
            pokemon_index = order_number - 1
            pokemon = pokemon_collection[pokemon_index]
            user_pokemon_list = []
            if trade_found["requester_id"] == user_id:
                user_pokemon_list = active_trades[trade_key]["requester_pokemon"]
            else:
                user_pokemon_list = active_trades[trade_key]["target_pokemon"]
            already_added = False
            for trade_pokemon in user_pokemon_list:
                if trade_pokemon.get("order") == order_number:
                    skipped_pokemon.append(f"#{order_number} (already added)")
                    already_added = True
                    break
            if already_added:
                continue
            iv_percent = f"{pokemon.get('iv_percentage', 0)}%"
            pokemon_trade_data = {
                "order": order_number,
                "name": pokemon.get("name", "Unknown"),
                "level": pokemon.get("level", 1),
                "iv_percent": iv_percent,
                "original_index": pokemon_index,
                "pokemon_data": pokemon
            }
            if trade_found["requester_id"] == user_id:
                active_trades[trade_key]["requester_pokemon"].append(pokemon_trade_data)
            else:
                active_trades[trade_key]["target_pokemon"].append(pokemon_trade_data)
            added_pokemon.append(f"#{order_number} {pokemon.get('name', 'Unknown')}")
        trade_message = active_trades[trade_key].get("trade_message")
        if trade_message:
            trade_data = active_trades[trade_key]
            try:
                requester = ctx.guild.get_member(trade_data["requester_id"])
                target = ctx.guild.get_member(trade_data["target_id"])
                if not requester:
                    requester = await ctx.bot.fetch_user(trade_data["requester_id"])
                if not target:
                    target = await ctx.bot.fetch_user(trade_data["target_id"])
                requester_name = getattr(requester, 'display_name', getattr(requester, 'name', 'User'))
                target_name = getattr(target, 'display_name', getattr(target, 'name', 'User'))
                embed = discord.Embed(
                    title=f"Trade between {requester_name} & {target_name}",
                    color=0xFFD700
                )
                requester_display = []
                if trade_data.get("requester_pokécoins", 0) > 0:
                    requester_display.append(f"{trade_data['requester_pokécoins']:,} Pokécoins <:pokecoins:1403472605620732099>")
                requester_pokemon = trade_data.get("requester_pokemon", [])
                for pokemon_data in requester_pokemon:
                    requester_display.append(f"{pokemon_data['order']}    {pokemon_data['name']}    •    Lvl.{pokemon_data['level']}    {pokemon_data['iv_percent']}")
                target_display = []
                if trade_data.get("target_pokécoins", 0) > 0:
                    target_display.append(f"{trade_data['target_pokécoins']:,} Pokécoins <:pokecoins:1403472605620732099>")
                target_pokemon = trade_data.get("target_pokemon", [])
                for pokemon_data in target_pokemon:
                    target_display.append(f"{pokemon_data['order']}    {pokemon_data['name']}    •    Lvl.{pokemon_data['level']}    {pokemon_data['iv_percent']}")
                requester_display_text = "\n".join(requester_display) if requester_display else "None"
                target_display_text = "\n".join(target_display) if target_display else "None"
                requester_dot = "🟢" if trade_data.get("requester_confirmed", False) else "🔴"
                target_dot = "🟢" if trade_data.get("target_confirmed", False) else "🔴"
                embed.add_field(
                    name=f"{requester_dot} " + requester_name,
                    value=requester_display_text,
                    inline=False
                )
                embed.add_field(
                    name=f"{target_dot} " + target_name,
                    value=target_display_text,
                    inline=False
                )
                embed.add_field(
                    name="Page Info",
                    value="Showing page 1 out of 1.",
                    inline=False
                )
                embed.add_field(
                    name="⚠️ Important Reminder",
                    value="Trading Pokécoins or Pokémon for real-life currencies or items in other bots is prohibited and will result in the suspension of your Pokékiro account!",
                    inline=False
                )
                await trade_message.edit(embed=embed)
            except Exception as e:
                print(f"Error updating trade embed: {e}")
                # Don't send feedback messages - trade embed update is enough
                pass
        # Don't send feedback messages for trade add - embed update is enough
@trade.command(name="cancel")
async def trade_cancel(ctx):
    user_id = ctx.author.id
    trade_found = None
    trade_key = None
    for key, trade_data in active_trades.items():
        if trade_data["requester_id"] == user_id or trade_data["target_id"] == user_id:
            trade_found = trade_data
            trade_key = key
            break
    if not trade_found:
        await ctx.send("You don't have an active trade to cancel!")
        return
    del active_trades[trade_key]
    await ctx.send("The trade has been cancelled")
@trade.command(name="confirm")
async def trade_confirm(ctx):
    user_id = ctx.author.id
    trade_found = None
    trade_key = None
    for key, trade_data in active_trades.items():
        if trade_data["requester_id"] == user_id or trade_data["target_id"] == user_id:
            trade_found = trade_data
            trade_key = key
            break
    if not trade_found:
        await ctx.send("You don't have an active trade to confirm!")
        return
    if trade_found["requester_id"] == user_id:
        active_trades[trade_key]["requester_confirmed"] = True
        confirmation_status = "You have confirmed the trade!"
    else:
        active_trades[trade_key]["target_confirmed"] = True
        confirmation_status = "You have confirmed the trade!"
    both_confirmed = (active_trades[trade_key]["requester_confirmed"] and
                     active_trades[trade_key]["target_confirmed"])
    await update_trade_embed(ctx, trade_key)
    if both_confirmed:
        await execute_pokécoin_trade(ctx, trade_key)
    else:
        await ctx.send(confirmation_status)
async def update_trade_embed(ctx, trade_key):
    trade_data = active_trades[trade_key]
    trade_message = trade_data.get("trade_message")
    if not trade_message:
        return
    try:
        requester = ctx.guild.get_member(trade_data["requester_id"])
        target = ctx.guild.get_member(trade_data["target_id"])
        if not requester:
            requester = await ctx.bot.fetch_user(trade_data["requester_id"])
        if not target:
            target = await ctx.bot.fetch_user(trade_data["target_id"])
        requester_name = getattr(requester, 'display_name', getattr(requester, 'name', 'User'))
        target_name = getattr(target, 'display_name', getattr(target, 'name', 'User'))
        embed = discord.Embed(
            title=f"Trade between {requester_name} & {target_name}",
            color=0xFFD700
        )
        requester_display = []
        if trade_data.get("requester_pokécoins", 0) > 0:
            requester_display.append(f"{trade_data['requester_pokécoins']:,} Pokécoins <:pokecoins:1403472605620732099>")
        requester_pokemon = trade_data.get("requester_pokemon", [])
        for pokemon_data in requester_pokemon:
            requester_display.append(f"{pokemon_data['order']}    {pokemon_data['name']}    •    Lvl.{pokemon_data['level']}    {pokemon_data['iv_percent']}")
        target_display = []
        if trade_data.get("target_pokécoins", 0) > 0:
            target_display.append(f"{trade_data['target_pokécoins']:,} Pokécoins <:pokecoins:1403472605620732099>")
        target_pokemon = trade_data.get("target_pokemon", [])
        for pokemon_data in target_pokemon:
            target_display.append(f"{pokemon_data['order']}    {pokemon_data['name']}    •    Lvl.{pokemon_data['level']}    {pokemon_data['iv_percent']}")
        requester_display_text = "\n".join(requester_display) if requester_display else "None"
        target_display_text = "\n".join(target_display) if target_display else "None"
        requester_dot = "🟢" if trade_data.get("requester_confirmed", False) else "🔴"
        target_dot = "🟢" if trade_data.get("target_confirmed", False) else "🔴"
        embed.add_field(
            name=f"{requester_dot} " + requester_name,
            value=requester_display_text,
            inline=False
        )
        embed.add_field(
            name=f"{target_dot} " + target_name,
            value=target_display_text,
            inline=False
        )
        embed.add_field(
            name="Page Info",
            value="Showing page 1 out of 1.",
            inline=False
        )
        embed.add_field(
            name="⚠️ Important Reminder",
            value="Trading Pokécoins or Pokémon for real-life currencies or items in other bots is prohibited and will result in the suspension of your Pokékiro account!",
            inline=False
        )
        await trade_message.edit(embed=embed)
    except Exception as e:
        print(f"Error updating trade embed: {e}")
async def execute_pokécoin_trade(ctx, trade_key):
    trade_data = active_trades[trade_key]
    try:
        requester_data = get_trainer_data(trade_data["requester_id"])
        target_data = get_trainer_data(trade_data["target_id"])
        if not requester_data or not target_data:
            await ctx.send("Error: Could not retrieve trainer data!")
            return
        requester_coins = get_user_pokecoins(requester_data)
        target_coins = get_user_pokecoins(target_data)
        if requester_coins < trade_data["requester_pokécoins"]:
            await ctx.send(f"Trade failed: Requester doesn't have enough pokécoins!")
            return
        if target_coins < trade_data["target_pokécoins"]:
            await ctx.send(f"Trade failed: Target user doesn't have enough pokécoins!")
            return
        new_requester_coins = requester_coins - trade_data["requester_pokécoins"] + trade_data["target_pokécoins"]
        new_target_coins = target_coins - trade_data["target_pokécoins"] + trade_data["requester_pokécoins"]
        requester_data["pokécoins"] = new_requester_coins
        target_data["pokécoins"] = new_target_coins
        requester_pokemon_collection = []
        if requester_data.get("StarterPokemon"):
            requester_pokemon_collection.append(requester_data["StarterPokemon"])
        if "CaughtPokemons" in requester_data and requester_data["CaughtPokemons"]:
            requester_pokemon_collection.extend(requester_data["CaughtPokemons"])
        target_pokemon_collection = []
        if target_data.get("StarterPokemon"):
            target_pokemon_collection.append(target_data["StarterPokemon"])
        if "CaughtPokemons" in target_data and target_data["CaughtPokemons"]:
            target_pokemon_collection.extend(target_data["CaughtPokemons"])
        requester_remove_indices = []
        target_remove_indices = []
        requester_traded_pokemon = []
        for pokemon_trade in trade_data.get("requester_pokemon", []):
            original_index = pokemon_trade["original_index"]
            requester_remove_indices.append(original_index)
            requester_traded_pokemon.append(pokemon_trade["pokemon_data"])
        target_traded_pokemon = []
        for pokemon_trade in trade_data.get("target_pokemon", []):
            original_index = pokemon_trade["original_index"]
            target_remove_indices.append(original_index)
            target_traded_pokemon.append(pokemon_trade["pokemon_data"])
        requester_traded_pokemon = []
        for pokemon_trade in trade_data.get("requester_pokemon", []):
            requester_traded_pokemon.append(pokemon_trade["pokemon_data"])
        target_traded_pokemon = []
        for pokemon_trade in trade_data.get("target_pokemon", []):
            target_traded_pokemon.append(pokemon_trade["pokemon_data"])
        if "CaughtPokemons" not in requester_data:
            requester_data["CaughtPokemons"] = []
        if "CaughtPokemons" not in target_data:
            target_data["CaughtPokemons"] = []
        requester_data["CaughtPokemons"].extend(target_traded_pokemon)
        target_data["CaughtPokemons"].extend(requester_traded_pokemon)
        if update_trainer_data(str(trade_data["requester_id"]), requester_data) and update_trainer_data(str(trade_data["target_id"]), target_data):
            del active_trades[trade_key]
            await ctx.send(f"Trade between <@{trade_data['requester_id']}> & <@{trade_data['target_id']}> completed successfully! ✅")
        else:
            await ctx.send("❌ Trade failed: Could not update trainer data!")
    except Exception as e:
        print(f"Error executing trade: {e}")
        await ctx.send("❌ Trade failed due to an error!")
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, discord.ext.commands.CommandNotFound):
        command_content = ctx.message.content.lower()
        if any(word in command_content for word in ["summoning", "stone", "gems", "gem", "buy"]):
            await ctx.send(
                "It looks like you're trying to buy something! Use these commands:\n"
                "`@Pokékiro#8400 buy gems <amount>` - Buy gems with pokécoins\n"
                "`@Pokékiro#8400 buy summoning stone <amount>` - Buy summoning stones with gems\n"
                "`@Pokékiro#8400 shop 8` - View gems purchase page\n"
                "`@Pokékiro#8400 shop 10` - View summoning stone page"
            )
    elif isinstance(error, discord.ext.commands.CommandInvokeError):
        print(f"Command error: {error}")
def remove_item_from_inventory(trainer_data, item_name, amount=1):
    if "inventory" not in trainer_data:
        return False
    if item_name not in trainer_data["inventory"]:
        return False
    if trainer_data["inventory"][item_name] < amount:
        return False
    trainer_data["inventory"][item_name] -= amount
    if trainer_data["inventory"][item_name] <= 0:
        del trainer_data["inventory"][item_name]
    return True
def get_pokemon_image_url(pokemon_name):
    from pokémon_dex_entry import get_pokemon_artwork_url
    return get_pokemon_artwork_url(pokemon_name)
def find_pokemon_by_name(pokemon_name):
    pokemon_name_lower = pokemon_name.lower().strip()
    all_generations = [POKEMON_GEN1, POKEMON_GEN2, POKEMON_GEN3, POKEMON_GEN4, POKEMON_GEN5, POKEMON_GEN6, POKEMON_GEN7, POKEMON_GEN8, POKEMON_GEN9]
    for generation in all_generations:
        for i, pokemon in enumerate(generation):
            if pokemon["name"].lower() == pokemon_name_lower:
                return pokemon, i
    return None, None
@bot.command(name='summon')
async def summon_command(ctx, *, pokemon_name=None):
    global current_spawn
    if not pokemon_name:
        embed = discord.Embed(
            title="Missing Pokemon Name",
            description="Please specify which Pokemon to summon!\nExample: `@Pokékiro summon Pikachu`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    trainer_data = get_trainer_data(ctx.author.id)
    if not trainer_data:
        embed = discord.Embed(
            title="Not Registered",
            description="You need to register first!\nUse: `@Pokékiro register [Male/Female]`",
            color=0xe74c3c
        )
        await ctx.send(embed=embed)
        return
    if "inventory" not in trainer_data or "Summoning Stone" not in trainer_data["inventory"] or trainer_data["inventory"]["Summoning Stone"] < 1:
        embed = discord.Embed(
            title="No Summoning Stone",
            description="You need a Summoning Stone to summon Pokemon!\nBuy one from the shop: `@Pokékiro buy summoning stone`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    if current_spawn is not None:
        embed = discord.Embed(
            title="Pokemon Already Spawned",
            description="There's already a Pokemon spawned! Catch it first before summoning another.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    pokemon_data, pokemon_index = find_pokemon_by_name(pokemon_name)
    if not pokemon_data:
        embed = discord.Embed(
            title="Pokemon Not Found",
            description=f"Pokemon '{pokemon_name}' not found in the database!\nMake sure you spelled it correctly.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    if not remove_item_from_inventory(trainer_data, "Summoning Stone", 1):
        embed = discord.Embed(
            title="Error",
            description="Failed to use Summoning Stone. Please try again.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    if not update_trainer_data(ctx.author.id, trainer_data):
        embed = discord.Embed(
            title="Error",
            description="Failed to update your inventory. Please try again.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    spawned_pokemon = create_spawned_pokemon(pokemon_data)
    current_spawn = {
        "name": spawned_pokemon["name"],
        "level": spawned_pokemon["level"],
        "gender": spawned_pokemon["gender"],
        "total_iv": spawned_pokemon["iv_percentage"],
        "caught": False,
        "full_data": spawned_pokemon
    }
    embed = discord.Embed(
        title="A wild pokémon has been summoned!",
        description=f"{ctx.author.mention} used a Summoning Stone <:Summoning_stone:1405194343056408747> guess the pokémon and type `Pokékiro#8400 catch <pokémon>` to catch it!",
        color=0x9932CC
    )
    embed.set_image(url=get_pokemon_image_url(spawned_pokemon['name']))
    remaining_stones = trainer_data["inventory"].get("Summoning Stone", 0)
    embed.set_footer(text=f"Summoning Stones remaining: {remaining_stones}")
    await ctx.send(embed=embed)
BASE_URL = "https://pokemondb.net/pokedex/"
def analyze_special_case(pokemon_name):
    lower_name = pokemon_name.lower().strip()
    special_case_info = {
        "is_special_case": False,
        "category": None,
        "explanation": None,
        "alternative_name": None,
        "note": None
    }
    if any(keyword in lower_name for keyword in ["mega ", "gigantamax ", "primal "]):
        special_case_info.update({
            "is_special_case": True,
            "category": "Transformation",
            "explanation": "This Pokemon uses a temporary transformation. Movesets are usually the same as the base form.",
            "alternative_name": lower_name.replace("mega ", "").replace("gigantamax ", "").replace("primal ", "").strip(),
            "note": "Try searching for the base Pokemon name instead."
        })
    elif "eternamax" in lower_name:
        special_case_info.update({
            "is_special_case": True,
            "category": "Unique Form",
            "explanation": "Eternamax Eternatus is a special raid-only form with the same movesets as regular Eternatus.",
            "alternative_name": "eternatus",
            "note": "This form cannot be used in normal battles."
        })
    elif any(region in lower_name for region in ["alolan ", "galarian ", "hisuian ", "paldean "]):
        special_case_info.update({
            "is_special_case": True,
            "category": "Regional Form",
            "explanation": "This is a regional variant with different movesets from the original form.",
            "note": "Regional forms have unique movesets - this should work with the enhanced scraper."
        })
    elif "urshifu" in lower_name and ("single strike" in lower_name or "rapid strike" in lower_name):
        special_case_info.update({
            "is_special_case": True,
            "category": "Combat Style",
            "explanation": "Urshifu has two different combat styles with different signature moves.",
            "note": "Each style learns different moves at certain levels."
        })
    return special_case_info
def get_level_up_moves(pokemon_name):
    url_name = pokemon_name.lower().strip()
    url_replacements = {
        "mr. mime": "mr-mime",
        "mime jr.": "mime-jr",
        "mr. rime": "mr-rime",
        "farfetch'd": "farfetchd",
        "sirfetch'd": "sirfetchd",
        "nidoran♀": "nidoran-f",
        "nidoran♂": "nidoran-m",
        "ho-oh": "ho-oh",
        "porygon-z": "porygon-z",
        "jangmo-o": "jangmo-o",
        "hakamo-o": "hakamo-o",
        "kommo-o": "kommo-o",
        "tapu koko": "tapu-koko",
        "tapu lele": "tapu-lele",
        "tapu bulu": "tapu-bulu",
        "tapu fini": "tapu-fini",
        "type: null": "type-null",
        "flabébé": "flabebe",
        "mega venusaur": "venusaur",
        "mega charizard x": "charizard",
        "mega charizard y": "charizard",
        "mega blastoise": "blastoise",
        "mega alakazam": "alakazam",
        "mega gengar": "gengar",
        "mega kangaskhan": "kangaskhan",
        "mega pinsir": "pinsir",
        "mega gyarados": "gyarados",
        "mega aerodactyl": "aerodactyl",
        "mega mewtwo x": "mewtwo",
        "mega mewtwo y": "mewtwo",
        "mega ampharos": "ampharos",
        "mega scizor": "scizor",
        "mega heracross": "heracross",
        "mega houndoom": "houndoom",
        "mega tyranitar": "tyranitar",
        "mega blaziken": "blaziken",
        "mega gardevoir": "gardevoir",
        "mega mawile": "mawile",
        "mega aggron": "aggron",
        "mega medicham": "medicham",
        "mega manectric": "manectric",
        "mega banette": "banette",
        "mega absol": "absol",
        "mega garchomp": "garchomp",
        "mega lucario": "lucario",
        "mega abomasnow": "abomasnow",
        "mega rayquaza": "rayquaza",
        "primal groudon": "groudon",
        "primal kyogre": "kyogre",
        "gigantamax charizard": "charizard",
        "gigantamax butterfree": "butterfree",
        "gigantamax pikachu": "pikachu",
        "gigantamax meowth": "meowth",
        "gigantamax machamp": "machamp",
        "gigantamax gengar": "gengar",
        "gigantamax kingler": "kingler",
        "gigantamax lapras": "lapras",
        "gigantamax eevee": "eevee",
        "gigantamax snorlax": "snorlax",
        "gigantamax garbodor": "garbodor",
        "gigantamax corviknight": "corviknight",
        "gigantamax orbeetle": "orbeetle",
        "gigantamax drednaw": "drednaw",
        "gigantamax coalossal": "coalossal",
        "gigantamax flapple": "flapple",
        "gigantamax appletun": "appletun",
        "gigantamax sandaconda": "sandaconda",
        "gigantamax toxapex": "toxapex",
        "gigantamax centiskorch": "centiskorch",
        "gigantamax hatterene": "hatterene",
        "gigantamax grimmsnarl": "grimmsnarl",
        "gigantamax alcremie": "alcremie",
        "gigantamax copperajah": "copperajah",
        "gigantamax duraludon": "duraludon",
        "urshifu single strike style": "urshifu-single-strike",
        "urshifu rapid strike style": "urshifu-rapid-strike",
        "urshifu single strike": "urshifu-single-strike",
        "urshifu rapid strike": "urshifu-rapid-strike",
        "eternamax eternatus": "eternatus",
        "rotom heat": "rotom-heat",
        "rotom wash": "rotom-wash",
        "rotom frost": "rotom-frost",
        "rotom fan": "rotom-fan",
        "rotom mow": "rotom-mow",
        "deoxys attack forme": "deoxys-attack",
        "deoxys defense forme": "deoxys-defense",
        "deoxys speed forme": "deoxys-speed",
        "deoxys attack": "deoxys-attack",
        "deoxys defense": "deoxys-defense",
        "deoxys speed": "deoxys-speed",
        "wormadam plant cloak": "wormadam-plant",
        "wormadam sandy cloak": "wormadam-sandy",
        "wormadam trash cloak": "wormadam-trash",
        "wormadam plant": "wormadam-plant",
        "wormadam sandy": "wormadam-sandy",
        "wormadam trash": "wormadam-trash",
        "shaymin land forme": "shaymin",
        "shaymin sky forme": "shaymin-sky",
        "shaymin land": "shaymin",
        "shaymin sky": "shaymin-sky",
        "alolan rattata": "alolan-rattata",
        "alolan raticate": "alolan-raticate",
        "alolan raichu": "alolan-raichu",
        "alolan sandshrew": "alolan-sandshrew",
        "alolan sandslash": "alolan-sandslash",
        "alolan vulpix": "alolan-vulpix",
        "alolan ninetales": "alolan-ninetales",
        "alolan diglett": "alolan-diglett",
        "alolan dugtrio": "alolan-dugtrio",
        "alolan meowth": "alolan-meowth",
        "alolan persian": "alolan-persian",
        "alolan geodude": "alolan-geodude",
        "alolan graveler": "alolan-graveler",
        "alolan golem": "alolan-golem",
        "alolan grimer": "alolan-grimer",
        "alolan muk": "alolan-muk",
        "alolan exeggutor": "alolan-exeggutor",
        "alolan marowak": "alolan-marowak",
        "galarian meowth": "galarian-meowth",
        "galarian ponyta": "galarian-ponyta",
        "galarian rapidash": "galarian-rapidash",
        "galarian slowpoke": "galarian-slowpoke",
        "galarian slowbro": "galarian-slowbro",
        "galarian farfetch'd": "galarian-farfetchd",
        "galarian weezing": "galarian-weezing",
        "galarian mr. mime": "galarian-mr-mime",
        "galarian articuno": "galarian-articuno",
        "galarian zapdos": "galarian-zapdos",
        "galarian moltres": "galarian-moltres",
        "galarian slowking": "galarian-slowking",
        "galarian corsola": "galarian-corsola",
        "galarian zigzagoon": "galarian-zigzagoon",
        "galarian linoone": "galarian-linoone",
        "galarian darumaka": "galarian-darumaka",
        "galarian darmanitan": "galarian-darmanitan",
        "galarian yamask": "galarian-yamask",
        "galarian stunfisk": "galarian-stunfisk",
        "hisuian growlithe": "hisuian-growlithe",
        "hisuian arcanine": "hisuian-arcanine",
        "hisuian voltorb": "hisuian-voltorb",
        "hisuian electrode": "hisuian-electrode",
        "hisuian typhlosion": "hisuian-typhlosion",
        "hisuian qwilfish": "hisuian-qwilfish",
        "hisuian sneasel": "hisuian-sneasel",
        "hisuian samurott": "hisuian-samurott",
        "hisuian lilligant": "hisuian-lilligant",
        "hisuian zorua": "hisuian-zorua",
        "hisuian zoroark": "hisuian-zoroark",
        "hisuian braviary": "hisuian-braviary",
        "hisuian sliggoo": "hisuian-sliggoo",
        "hisuian goodra": "hisuian-goodra",
        "hisuian avalugg": "hisuian-avalugg",
        "hisuian decidueye": "hisuian-decidueye",
        "paldean tauros (combat breed)": "tauros-paldea-combat",
        "paldean tauros (blaze breed)": "tauros-paldea-blaze",
        "paldean tauros (aqua breed)": "tauros-paldea-aqua",
        "paldean tauros combat": "tauros-paldea-combat",
        "paldean tauros blaze": "tauros-paldea-blaze",
        "paldean tauros aqua": "tauros-paldea-aqua",
        "paldean wooper": "paldean-wooper",
        "arceus bug": "arceus",
        "arceus dark": "arceus",
        "arceus dragon": "arceus",
        "arceus electric": "arceus",
        "arceus fairy": "arceus",
        "arceus fighting": "arceus",
        "arceus fire": "arceus",
        "arceus flying": "arceus",
        "arceus ghost": "arceus",
        "arceus grass": "arceus",
        "arceus ground": "arceus",
        "arceus ice": "arceus",
        "arceus poison": "arceus",
        "arceus psychic": "arceus",
        "arceus rock": "arceus",
        "arceus steel": "arceus",
        "arceus water": "arceus"
    }
    if url_name in url_replacements:
        url_name = url_replacements[url_name]
    else:
        url_name = url_name.replace(" ", "-")
    url = BASE_URL + url_name
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            special_info = analyze_special_case(pokemon_name)
            if special_info["is_special_case"]:
                error_msg = f"❌ **{special_info['category']} Detected:** {pokemon_name.title()}\n\n"
                error_msg += f"ℹ️ **{special_info['explanation']}**\n"
                if special_info['alternative_name']:
                    error_msg += f"💡 **Suggestion:** Try searching for `{special_info['alternative_name'].title()}`\n"
                if special_info['note']:
                    error_msg += f"📝 **Note:** {special_info['note']}"
                return error_msg
            else:
                return f"❌ **Pokemon not found:** Could not fetch data for **{pokemon_name.title()}**. Please check the spelling and try again."
        soup = BeautifulSoup(resp.text, "html.parser")
        moves_section = soup.find("h3", string="Moves learnt by level up")
        if not moves_section:
            moves_section = soup.find("h3", string=lambda text: text and "level up" in text.lower() if text else False)
        if not moves_section:
            moves_section = soup.find("h2", string="Moves learnt by level up")
        if not moves_section:
            moves_section = soup.find("h2", string=lambda text: text and "level up" in text.lower() if text else False)
        if not moves_section:
            return f"❌ **No level-up moves found** for **{pokemon_name.title()}**. This Pokemon may not learn moves by leveling up."
        table = moves_section.find_next("table")
        if not table:
            return f"❌ **No movesets table found** for **{pokemon_name.title()}**."
        rows = table.find_all("tr")
        if len(rows) <= 1:
            return f"❌ **No moves data found** for **{pokemon_name.title()}**."
        formatted_moves = []
        for row in rows[1:]:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            level = cols[0].get_text(strip=True)
            move = cols[1].get_text(strip=True)
            move_type = cols[2].get_text(strip=True)
            category = cols[3].get_text(strip=True)
            formatted_moves.append(f"**Level {level}** - {move} `[{move_type}/{category}]`")
        if not formatted_moves:
            return f"❌ **No valid moves found** for **{pokemon_name.title()}**."
        output = f"📋 **{pokemon_name.title()} — Level-up Movesets**\n\n"
        output += "\n".join(formatted_moves)
        output += f"\n\n*Data fetched from pokemondb.net*"
        return output
    except requests.RequestException as e:
        return f"❌ **Network error:** Could not fetch data from pokemondb.net. Please try again later."
    except Exception as e:
        return f"❌ **Error processing data** for **{pokemon_name.title()}**: {str(e)}"
async def get_level_up_moves_async(pokemon_name):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_level_up_moves, pokemon_name)
def split_long_message(text, max_length=2000):
    if len(text) <= max_length:
        return [text]
    parts = []
    lines = text.split('\n')
    current_part = ""
    for line in lines:
        if len(current_part) + len(line) + 1 > max_length:
            if current_part:
                parts.append(current_part)
                current_part = line
            else:
                while len(line) > max_length:
                    parts.append(line[:max_length])
                    line = line[max_length:]
                current_part = line
        else:
            if current_part:
                current_part += "\n" + line
            else:
                current_part = line
    if current_part:
        parts.append(current_part)
    return parts
def get_move_by_name(move_name):
    move_key = move_name.lower().strip().replace(" ", "-")
    if move_key in POKEMON_MOVES:
        return POKEMON_MOVES[move_key]
    for key, move_data in POKEMON_MOVES.items():
        if move_data["name"].lower() == move_name.lower().strip():
            return move_data
        if key.replace("-", " ").lower() == move_name.lower().strip():
            return move_data
    return None
def get_all_moves():
    return POKEMON_MOVES
def search_moves_by_type(move_type):
    matching_moves = []
    for move_key, move_data in POKEMON_MOVES.items():
        if move_data["type"].lower() == move_type.lower():
            matching_moves.append(move_data)
    return matching_moves
def search_moves_by_class(move_class):
    matching_moves = []
    for move_key, move_data in POKEMON_MOVES.items():
        if move_data["class"].lower() == move_class.lower():
            matching_moves.append(move_data)
    return matching_moves
def format_move_info(move_data):
    if not move_data:
        return "Move not found."
    output = f"**{move_data['name']}**\n"
    output += f"**Type:** {move_data['type']}\n"
    output += f"**Class:** {move_data['class']}\n"
    output += f"**Power:** {move_data.get('power', 'N/A')}\n"
    output += f"**Accuracy:** {move_data.get('accuracy', 'N/A')}%\n"
    output += f"**PP:** {move_data.get('pp', 'N/A')}\n"
    output += f"**Priority:** {move_data.get('priority', 0)}\n"
    output += f"**Target:** {move_data.get('target', 'N/A')}\n"
    output += f"**Generation:** {move_data.get('generation', 'Unknown')}\n"
    if move_data.get('description'):
        output += f"**Description:** {move_data['description']}\n"
    return output
@bot.command()
async def movesets(ctx, *, pokemon_name=None):
    if not pokemon_name:
        embed = discord.Embed(
            title="Missing Pokemon Name",
            description="Please specify a Pokemon name!\nExample: `@Pokékiro movesets Charizard`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    async with ctx.typing():
        try:
            from movesets_scraper import get_all_moves_comprehensive_async, MovePaginationView
            move_data = await get_all_moves_comprehensive_async(pokemon_name)
            if "error" in move_data:
                embed = discord.Embed(
                    title="Error",
                    description=move_data["error"],
                    color=0xff0000
                )
                await ctx.send(embed=embed)
                return
            if not any([move_data["level_up"], move_data["evolution"], move_data["egg"], move_data["tm"]]):
                embed = discord.Embed(
                    title="No Moves Found",
                    description=f"No movesets were found for **{pokemon_name.title()}**. Please check the spelling and try again.",
                    color=0xff0000
                )
                await ctx.send(embed=embed)
                return
            view = MovePaginationView(move_data, ctx.author.id)
            await ctx.send(embed=view.get_current_embed(), view=view)
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"An error occurred while fetching movesets: {str(e)}",
                color=0xff0000
            )
            await ctx.send(embed=embed)
@bot.command(name="use")
async def use_command(ctx, *, args: str):
    trainer_data = get_trainer_data(ctx.author.id)
    if not trainer_data:
        await ctx.send("❌ You are not registered as a trainer. Use `@Pokékiro register` first.")
        return
    
    parts = args.split()
    if len(parts) == 0:
        await ctx.send("❌ Usage: @Pokékiro use rare candy <amount>")
        return
    
    # Handle item usage
    try:
        amount = int(parts[-1])
        item = " ".join(parts[:-1]).lower()
    except ValueError:
        amount = 1
        item = " ".join(parts).lower()
    if item not in ["rare candy", "rare_candy", "rare-candy", "rare"]:
        await ctx.send("❌ Currently, only Rare Candy usage is supported.")
        return
    inventory = trainer_data.get("inventory", {})
    inventory_normalized = {k.lower(): v for k, v in inventory.items()}
    rare_candies = inventory_normalized.get("rare candy", 0)
    if rare_candies < amount:
        await ctx.send(f"❌ You don’t have enough Rare Candies! (You have {rare_candies})")
        return
    inventory_key = next((k for k in inventory if k.lower() == "rare candy"), "Rare Candy")
    trainer_data["inventory"][inventory_key] = rare_candies - amount
    selected = trainer_data.get("SelectedPokemon")
    if not selected:
        await ctx.send("❌ You must select a Pokémon first using `@Pokékiro select <order_number>`.")
        return
    pokemon_entry = None
    if selected["type"] == "starter":
        pokemon_entry = trainer_data.get("StarterPokemon")
    elif selected["type"] == "caught":
        starter = trainer_data.get("StarterPokemon")
        if starter:
            idx = selected["order"] - 2
        else:
            idx = selected["order"] - 1
        if "CaughtPokemons" in trainer_data and 0 <= idx < len(trainer_data["CaughtPokemons"]):
            pokemon_entry = trainer_data["CaughtPokemons"][idx]
    if not pokemon_entry:
        await ctx.send("❌ Selected Pokémon not found.")
        return
    original_name = pokemon_entry.get("name", "Unknown").title()
    old_level = pokemon_entry.get("level", 1)
    old_stats = pokemon_entry.get("calculated_stats", {}).copy()
    pokemon_entry["level"] = min(100, old_level + amount)
    new_level = pokemon_entry["level"]
    base_stats = pokemon_entry.get("base_stats", {})
    ivs = pokemon_entry.get("ivs", {})
    nature = pokemon_entry.get("nature", "hardy")
    evs = pokemon_entry.get("evs", {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0})
    new_stats = calculate_official_stats(base_stats, ivs, new_level, nature, evs)
    pokemon_entry["calculated_stats"] = new_stats
    try:
        from evolutions import LEVEL_ONLY_EVOLUTIONS as EVOLUTIONS
    except Exception:
        EVOLUTIONS = {}
    evolutions_done = []
    while True:
        current_name_lower = pokemon_entry.get("name", "").lower()
        evo_info = EVOLUTIONS.get(current_name_lower)
        if not evo_info:
            break
        required_level = evo_info.get("level", 9999)
        if new_level >= required_level:
            old_species = pokemon_entry.get("name", "").title()
            new_species = evo_info.get("evolves_to", "").lower()
            try:
                species_data = get_pokemon_by_name(new_species)
            except Exception:
                species_data = None
            pokemon_entry["name"] = new_species
            if species_data:
                new_base = species_data.get("base_stats") or species_data.get("stats") or {}
                if new_base:
                    pokemon_entry["base_stats"] = new_base
                sprite_candidate = species_data.get("sprite") if species_data else None
                if sprite_candidate:
                    pokemon_entry["sprite"] = sprite_candidate
            try:
                img_url = get_pokemon_image_url(pokemon_entry["name"])
                if img_url:
                    pokemon_entry["sprite"] = img_url
            except Exception:
                pass
            base_stats = pokemon_entry.get("base_stats", base_stats)
            new_stats = calculate_official_stats(base_stats, ivs, new_level, nature, evs)
            pokemon_entry["calculated_stats"] = new_stats
            evolutions_done.append((old_species, pokemon_entry["name"].title()))
            continue
        else:
            break
    moves_learned = []
    try:
        current_name = pokemon_entry.get("name", original_name)
        movesets = get_all_moves_comprehensive(current_name)
        if "level_up" in movesets and movesets["level_up"]:
            for level in range(old_level + 1, new_level + 1):
                for move_info in movesets["level_up"]:
                    if move_info.get("level") and move_info["level"].isdigit():
                        move_level = int(move_info["level"])
                        if move_level == level:
                            moves_learned.append(move_info["move"])
    except:
        pass
    if moves_learned:
        if "learned_moves" not in pokemon_entry:
            pokemon_entry["learned_moves"] = []
        for move in moves_learned:
            if move not in pokemon_entry["learned_moves"]:
                pokemon_entry["learned_moves"].append(move)
    update_trainer_data(str(ctx.author.id), trainer_data)
    description = (
        f"You used {amount} Rare Candy <:rare_candy:1403486543477473521>!\n\n"
        f"Your {original_name} grew from level {old_level} → {new_level}!"
    )
    if moves_learned:
        moves_text = ", ".join([move.replace("-", " ").title() for move in moves_learned])
        description += f"\n\n✨ **New moves learned:** {moves_text}"
    embed = discord.Embed(
        title="🎉 Level Up!",
        description=description,
        color=discord.Color.gold()
    )
    if evolutions_done:
        first_old = evolutions_done[0][0]
        last_new = evolutions_done[-1][1]
        embed.description += f"\n\n🎉 Congratulations {ctx.author.display_name}!\nYour {first_old} evolved into **{last_new}**!"
    stats_text = ""
    for stat in ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]:
        before = old_stats.get(stat, 0)
        after = new_stats.get(stat, 0)
        diff = after - before
        stats_text += f"**{stat.upper()}**: {before} → {after} (+{diff})\n"
    embed.add_field(name="📊 Stats Update", value=stats_text, inline=False)
    try:
        embed.set_image(url=get_pokemon_image_url(pokemon_entry["name"]))
    except Exception:
        if pokemon_entry.get("sprite"):
            embed.set_thumbnail(url=pokemon_entry["sprite"])
    embed.set_footer(text=f"Remaining Rare Candies: {trainer_data['inventory'][inventory_key]}")
    await ctx.send(embed=embed)
@bot.command(name="moves")
async def show_pokemon_moves(ctx):
    trainer_data = get_trainer_data(ctx.author.id)
    if not trainer_data:
        await ctx.send("❌ You are not registered as a trainer.")
        return
    selected_pokemon = trainer_data.get("SelectedPokemon")
    if not selected_pokemon:
        await ctx.send("❌ You need to select a Pokemon first using `@Pokékiro select <order>`")
        return
    pokemon_data = None
    if selected_pokemon["type"] == "starter" and trainer_data["StarterPokemon"] is not None:
        pokemon_data = trainer_data["StarterPokemon"]
    elif selected_pokemon["type"] == "caught" and "CaughtPokemons" in trainer_data:
        starter = trainer_data.get("StarterPokemon")
        if starter:
            caught_index = selected_pokemon["order"] - 2
        else:
            caught_index = selected_pokemon["order"] - 1
        if 0 <= caught_index < len(trainer_data["CaughtPokemons"]):
            pokemon_data = trainer_data["CaughtPokemons"][caught_index]
    if not pokemon_data:
        await ctx.send("❌ Selected Pokemon not found.")
        return
    pokemon_name = pokemon_data.get("name", "Unknown")
    pokemon_level = pokemon_data.get("level", 1)
    learned_moves = pokemon_data.get("learned_moves", [])
    available_moves = []
    try:
        from movesets_scraper import get_all_moves_comprehensive
        moveset_data = get_all_moves_comprehensive(pokemon_name.lower())
        if moveset_data and 'level_up' in moveset_data:
            for move_info in moveset_data['level_up']:
                level = move_info['level']
                if level.isdigit() and int(level) <= pokemon_level:
                    move_name = move_info['move'].replace('-', ' ').title()
                    available_moves.append(f"{level}. {move_name}")
        available_moves.sort(key=lambda x: int(x.split('.')[0]))
    except Exception as e:
        available_moves = ["Unable to fetch moves data"]
    embed = discord.Embed(
        title=f"Level {pokemon_level} {pokemon_name.title()} — Moves",
        description=f"Here are the moves your pokémon can learn right now. View all moves and how to get them using `@PᴏᴋéKɪʀᴏ movesets {pokemon_name.lower()}`!",
        color=discord.Color.gold()
    )
    if available_moves and available_moves[0] != "Unable to fetch moves data":
        clean_moves = []
        for move in available_moves:
            move_name = move.split('. ', 1)[1] if '. ' in move else move
            clean_moves.append(f"{len(clean_moves)+1}. {move_name}")
        available_text = "\n".join(clean_moves)
    else:
        available_text = "No moves available"
    embed.add_field(name="**Available Moves**", value=available_text, inline=False)
    current_moves = pokemon_data.get("current_moves", [])
    current_moves_text = ""
    for i in range(1, 5):
        if i-1 < len(current_moves):
            current_moves_text += f"{i}. {current_moves[i-1].replace('-', ' ').title()}\n"
        else:
            current_moves_text += f"{i}. None\n"
    embed.add_field(name="**Current Moves**", value=current_moves_text, inline=False)
    await ctx.send(embed=embed)

class MoveReplaceView(View):
    def __init__(self, user_id, pokemon_data, pokemon_type, new_move, trainer_data):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.pokemon_data = pokemon_data
        self.pokemon_type = pokemon_type
        self.new_move = new_move
        self.trainer_data = trainer_data
        
        # Add dropdown for move selection
        current_moves = pokemon_data.get("current_moves", [])
        options = []
        for i, move in enumerate(current_moves):
            if move:
                options.append(discord.SelectOption(
                    label=move.replace('-', ' ').title(),
                    value=str(i),
                    description=f"Slot {i+1}"
                ))
        
        if options:
            self.select_move.options = options
        else:
            self.select_move.disabled = True

    @discord.ui.select(placeholder="Replace a move", min_values=1, max_values=1)
    async def select_move(self, interaction: discord.Interaction, select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the Pokemon owner can replace moves!", ephemeral=True)
            return
            
        slot_index = int(select.values[0])
        old_move = self.pokemon_data["current_moves"][slot_index]
        
        # Replace the move
        self.pokemon_data["current_moves"][slot_index] = self.new_move
        
        # Update trainer data
        if self.pokemon_type == "starter":
            self.trainer_data["StarterPokemon"] = self.pokemon_data
        elif self.pokemon_type == "caught":
            starter = self.trainer_data.get("StarterPokemon")
            if starter:
                caught_index = self.pokemon_data.get("order", 1) - 2
            else:
                caught_index = self.pokemon_data.get("order", 1) - 1
            if 0 <= caught_index < len(self.trainer_data["CaughtPokemons"]):
                self.trainer_data["CaughtPokemons"][caught_index] = self.pokemon_data
        
        update_trainer_data(self.user_id, self.trainer_data)
        
        embed = discord.Embed(
            title="✅ Move Learned!",
            description=f"Your Pokémon has learned **{self.new_move.replace('-', ' ').title()}** and forgotten **{old_move.replace('-', ' ').title()}**!",
            color=0x00ff00
        )
        
        await interaction.response.edit_message(embed=embed, view=None)
@bot.command(name="learn")
async def learn_move(ctx, *, move_name: str = None):
    if not move_name:
        embed = discord.Embed(
            title="Missing Move Name",
            description="Please specify which move you want to learn!\n\nUse: `@Pokékiro learn <move_name>`\nExample: `@Pokékiro learn thunderbolt`",
            color=0xe74c3c
        )
        await ctx.send(embed=embed)
        return
        
    if not is_trainer_registered(ctx.author.id):
        embed = discord.Embed(
            title="Not Registered",
            description="You need to register first!\n\nUse: `@Pokékiro register [Male/Female]`",
            color=0xe74c3c
        )
        await ctx.send(embed=embed)
        return
        
    trainer_data = get_trainer_data(ctx.author.id)
    if not trainer_data:
        await ctx.send("❌ Unable to retrieve trainer data.")
        return
        
    selected_pokemon = trainer_data.get("SelectedPokemon")
    if not selected_pokemon:
        await ctx.send("❌ You need to select a Pokemon first using `@Pokékiro select <order>`")
        return
        
    # Get the selected Pokemon data
    pokemon_data = None
    pokemon_type = selected_pokemon["type"]
    
    if pokemon_type == "starter" and trainer_data["StarterPokemon"] is not None:
        pokemon_data = trainer_data["StarterPokemon"]
    elif pokemon_type == "caught" and "CaughtPokemons" in trainer_data:
        starter = trainer_data.get("StarterPokemon")
        if starter:
            caught_index = selected_pokemon["order"] - 2
        else:
            caught_index = selected_pokemon["order"] - 1
        if 0 <= caught_index < len(trainer_data["CaughtPokemons"]):
            pokemon_data = trainer_data["CaughtPokemons"][caught_index]
            
    if not pokemon_data:
        await ctx.send("❌ Selected Pokemon not found.")
        return
        
    pokemon_name = pokemon_data.get("name", "Unknown")
    pokemon_level = pokemon_data.get("level", 1)
    
    # Normalize move name for comparison
    move_name_normalized = move_name.lower().replace(" ", "-")
    
    # Check if Pokemon can learn this move
    try:
        from movesets_scraper import get_all_moves_comprehensive
        moveset_data = get_all_moves_comprehensive(pokemon_name.lower())
        
        can_learn = False
        required_level = 999
        
        if moveset_data and 'level_up' in moveset_data:
            for move_info in moveset_data['level_up']:
                move_db_name = move_info['move'].lower().replace(" ", "-")
                if move_db_name == move_name_normalized:
                    move_level = move_info['level']
                    if move_level.isdigit():
                        required_level = int(move_level)
                        if pokemon_level >= required_level:
                            can_learn = True
                        break
                        
    except Exception:
        embed = discord.Embed(
            title="❌ Error",
            description="Unable to fetch move data. Please try again later.",
            color=0xe74c3c
        )
        await ctx.send(embed=embed)
        return
        
    if not can_learn:
        if required_level == 999:
            embed = discord.Embed(
                title="❌ Cannot Learn Move",
                description=f"Your {pokemon_name.title()} cannot learn **{move_name.title()}**.",
                color=0xe74c3c
            )
        else:
            embed = discord.Embed(
                title="❌ Level Too Low",
                description=f"Your Pokemon level is too low to learn this move. Required level: {required_level}",
                color=0xe74c3c
            )
        await ctx.send(embed=embed)
        return
        
    # Initialize current_moves if it doesn't exist
    if "current_moves" not in pokemon_data:
        pokemon_data["current_moves"] = []
        
    current_moves = pokemon_data["current_moves"]
    
    # Check if Pokemon already knows this move
    if move_name_normalized in [move.lower().replace(" ", "-") for move in current_moves]:
        embed = discord.Embed(
            title="❌ Already Known",
            description=f"Your {pokemon_name.title()} already knows **{move_name.title()}**!",
            color=0xe74c3c
        )
        await ctx.send(embed=embed)
        return
        
    # If Pokemon has less than 4 moves, add it directly
    if len(current_moves) < 4:
        current_moves.append(move_name_normalized)
        
        # Update trainer data
        if pokemon_type == "starter":
            trainer_data["StarterPokemon"] = pokemon_data
        elif pokemon_type == "caught":
            starter = trainer_data.get("StarterPokemon")
            if starter:
                caught_index = selected_pokemon["order"] - 2
            else:
                caught_index = selected_pokemon["order"] - 1
            if 0 <= caught_index < len(trainer_data["CaughtPokemons"]):
                trainer_data["CaughtPokemons"][caught_index] = pokemon_data
                
        update_trainer_data(ctx.author.id, trainer_data)
        
        embed = discord.Embed(
            title="✅ Move Learned!",
            description=f"Your Pokémon has learned **{move_name.title()}**!",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        
    else:
        # Pokemon already knows 4 moves, need to replace one
        embed = discord.Embed(
            title="<:status:1407693796787097672> Replace Move",
            description="Your pokémon already knows the max number of moves! Please select a move to replace.",
            color=0xffa500
        )
        
        view = MoveReplaceView(ctx.author.id, pokemon_data, pokemon_type, move_name_normalized, trainer_data)
        await ctx.send(embed=embed, view=view)

@bot.command(name="challenge")
async def challenge_command(ctx, battle_format=None, *, target_user=None):
    # Handle the case where both parameters are provided
    if battle_format is not None and target_user is not None:
        # Validate battle format
        valid_formats = ["1v1", "2v2", "3v3", "4v4", "5v5", "6v6"]
        if battle_format not in valid_formats:
            await ctx.send(f"Invalid battle format! Use one of: {', '.join(valid_formats)}\nExample: `@Pokékiro challenge 1v1 @username`")
            return
        
        try:
            user = await commands.MemberConverter().convert(ctx, target_user.strip())
            await challenge_user_with_format(ctx, user, battle_format)
        except commands.BadArgument:
            await ctx.send(f"Please mention a valid user! Example: `@Pokékiro challenge {battle_format} @username`")
            return
    
    # Handle the case where only one parameter is provided - no backwards compatibility
    elif battle_format is not None and target_user is None:
        await ctx.send("Usage: `@Pokékiro challenge <format> @user`\nFormats: 1v1, 2v2, 3v3, 4v4, 5v5, 6v6\nExample: `@Pokékiro challenge 1v1 @username`")
        return
    
    # Handle the case where no parameters are provided
    else:
        await ctx.send("Usage: `@Pokékiro challenge <format> @user`\nFormats: 1v1, 2v2, 3v3, 4v4, 5v5, 6v6\nExample: `@Pokékiro challenge 1v1 @username`")
        return

async def challenge_user_with_format(ctx, user, battle_format):
    """Handle the actual challenge logic with battle format"""
    if user.id == ctx.author.id:
        await ctx.send("You can't challenge yourself!")
        return
    if user.bot:
        await ctx.send("You can't challenge bots!")
        return
    challenger_data = get_trainer_data(ctx.author.id)
    if not challenger_data:
        await ctx.send(f"<@{ctx.author.id}> You need to register first! Use `register [Male/Female]` to get started.")
        return
    target_data = get_trainer_data(user.id)
    if not target_data:
        await ctx.send(f"<@{user.id}> needs to register first! Tell them to use `register [Male/Female]` to get started.")
        return
    
    # Battle system coming soon
    await ctx.send(f"<@{ctx.author.id}> challenged <@{user.id}> to a {battle_format} battle! Battle system coming soon...")
@bot.command(name="evolve")
async def evolve_command(ctx):
    trainer_data = get_trainer_data(ctx.author.id)
    if not trainer_data:
        await ctx.send("❌ You are not registered as a trainer. Use `@Pokékiro register` first.")
        return
    selected = trainer_data.get("SelectedPokemon")
    if not selected:
        await ctx.send("❌ You must select a Pokémon first using `@Pokékiro select <order_number>`.")
        return
    pokemon_entry = None
    if selected["type"] == "starter":
        pokemon_entry = trainer_data.get("StarterPokemon")
    elif selected["type"] == "caught":
        idx = selected["order"] - 2
        if "CaughtPokemons" in trainer_data and 0 <= idx < len(trainer_data["CaughtPokemons"]):
            pokemon_entry = trainer_data["CaughtPokemons"][idx]
    if not pokemon_entry:
        await ctx.send("❌ Selected Pokémon not found.")
        return
    try:
        from evolutions import LEVEL_ONLY_EVOLUTIONS as EVOLUTIONS
    except Exception:
        EVOLUTIONS = {}
    current_name = pokemon_entry.get("name", "").lower()
    evo_info = EVOLUTIONS.get(current_name)
    if not evo_info:
        await ctx.send(f"❌ {pokemon_entry['name'].title()} cannot evolve further.")
        return
    required_level = evo_info.get("level", 9999)
    current_level = pokemon_entry.get("level", 1)
    if current_level < required_level:
        await ctx.send(f"❌ {pokemon_entry['name'].title()} needs to be at least level {required_level} to evolve.")
        return
    old_stats = pokemon_entry.get("calculated_stats", {}).copy()
    old_species = pokemon_entry["name"].title()
    new_species = evo_info.get("evolves_to", "").lower()
    try:
        species_data = get_pokemon_by_name(new_species)
    except Exception:
        species_data = None
    pokemon_entry["name"] = new_species
    if species_data:
        pokemon_entry["base_stats"] = species_data.get("base_stats") or species_data.get("stats") or {}
        if "sprite" in species_data:
            pokemon_entry["sprite"] = species_data["sprite"]
    base_stats = pokemon_entry.get("base_stats", {})
    ivs = pokemon_entry.get("ivs", {})
    nature = pokemon_entry.get("nature", "hardy")
    evs = pokemon_entry.get("evs", {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0})
    new_stats = calculate_official_stats(base_stats, ivs, current_level, nature, evs)
    pokemon_entry["calculated_stats"] = new_stats
    update_trainer_data(str(ctx.author.id), trainer_data)
    embed = discord.Embed(
        description=(
            f"🎉 Congratulations {ctx.author.display_name}!\n"
            f"Your {old_species} evolved into **{pokemon_entry['name'].title()}**!"
        ),
        color=discord.Color.gold()
    )
    stats_text = ""
    for stat in ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]:
        before = old_stats.get(stat, 0)
        after = new_stats.get(stat, 0)
        diff = after - before
        stats_text += f"**{stat.upper()}**: {before} → {after} (+{diff})\n"
    embed.add_field(name="📊 Stats Update", value=stats_text, inline=False)
    try:
        embed.set_image(url=get_pokemon_image_url(pokemon_entry["name"]))
    except Exception:
        if "sprite" in pokemon_entry:
            embed.set_thumbnail(url=pokemon_entry["sprite"])
    await ctx.send(embed=embed)
@bot.group(name="move")
async def move_group(ctx):
    if ctx.invoked_subcommand is None:
        embed = discord.Embed(
            title="Move Commands",
            description="Available move commands:\n`@Pokékiro move info <move_name>` - Get information about a move",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
@move_group.command(name="info")
async def move_info(ctx, *, move_name=None):
    if not move_name:
        embed = discord.Embed(
            title="Missing Move Name",
            description="Please specify a move name!\nExample: `@Pokékiro move info Thunderbolt`",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    move_data = get_move_by_name(move_name)
    if move_data:
        description_text = move_data.get('description', 'No description available.')
        embed = discord.Embed(
            title=move_data['name'],
            description=description_text,
            color=0xFFD700
        )
        power_value = move_data.get('power', 'N/A')
        embed.add_field(name="Power", value=str(power_value), inline=False)
        accuracy_value = move_data.get('accuracy', 'N/A')
        embed.add_field(name="Accuracy", value=str(accuracy_value), inline=False)
        pp_value = move_data.get('pp', 'N/A')
        embed.add_field(name="PP", value=str(pp_value), inline=False)
        priority_value = move_data.get('priority', 0)
        embed.add_field(name="Priority", value=str(priority_value), inline=False)
        type_value = move_data['type']
        type_emojis = {
            'Normal': '<:normal_type:1406551478184706068>', 'Fire': '<:fire_type:1406552697653559336>', 'Water': '<:water_type:1406552467319029860>', 'Electric': '<:electric_type:1406551930406436935>', 'Grass': '<:grass_type:1406552601415122945>',
            'Ice': '<:ice_type:1406553274584399934>', 'Fighting': '<:fighting_type:1406551764483702906>', 'Poison': '<:poison_type:1406555023382413343>', 'Ground': '<:ground_type:1406552961253117993>', 'Flying': '<:flying_type:1406553554897862779>',
            'Psychic': '<:psychic_type:1406552310808576122>', 'Bug': '<:bug_type:1406555435980427358>', 'Rock': '<:rock_type:1406552394950512711>', 'Ghost': '<:ghost_type:1406553684887998484>', 'Dragon': '<:dragon_type:1406552069669916742>',
            'Dark': '<:dark_type:1406553165624774666>', 'Steel': '<:steel_type:1406552865291501629>', 'Fairy': '<:fairy_type:1406552167283691691>'
        }
        type_emoji = type_emojis.get(type_value, '❓')
        embed.add_field(name="Type", value=f"{type_emoji} {type_value}", inline=False)
        class_value = move_data['class']
        class_emojis = {
            'Physical': '<:physical:1407693919722012702>',
            'Special': '<:spiecal:1407693872557064192>',
            'Status': '<:status:1407693796787097672>'
        }
        class_emoji = class_emojis.get(class_value, '❓')
        embed.add_field(name="Class", value=f"{class_emoji} {class_value}", inline=False)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="Move Not Found",
            description=f"Move '{move_name}' not found in the database. Please check the spelling and try again.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
@bot.command(name="pokédex")
async def pokedex_command(ctx, action=None, *, query=None):
    if not action or action.lower() != "info":
        await ctx.send("Usage: `@Pokékiro#8400 pokédex info <pokémon_name>` or `@Pokékiro#8400 pokédex info <#pokédex_id>`")
        return
    
    if not query:
        await ctx.send("Please provide a Pokémon name or Pokédex ID!")
        return
    
    query = query.strip()
    pokemon_data = None
    
    from pokedex import pokedex, pokedex_megas, pokedex_gigantamax, pokedex_alolan, pokedex_paldean, pokedex_hisuian, pokedex_galarian, pokedex_alternate_forms
    
    all_pokedex_lists = [
        pokedex, 
        pokedex_megas, 
        pokedex_gigantamax, 
        pokedex_alolan, 
        pokedex_paldean, 
        pokedex_hisuian, 
        pokedex_galarian, 
        pokedex_alternate_forms
    ]
    
    if query.startswith('#'):
        try:
            pokedex_id = int(query[1:])
            for poke_list in all_pokedex_lists:
                for poke in poke_list:
                    try:
                        if int(poke.get("ID", "0")) == pokedex_id:
                            pokemon_data = poke
                            break
                    except ValueError:
                        continue
                if pokemon_data:
                    break
        except ValueError:
            await ctx.send("Invalid Pokédex ID!")
            return
    else:
        search_name = query.lower()
        search_name_normalized = search_name.replace("'", "'").replace("'", "'")
        
        for poke_list in all_pokedex_lists:
            for poke in poke_list:
                poke_name = poke.get("Name", "").lower()
                poke_name_normalized = poke_name.replace("'", "'").replace("'", "'")
                if poke_name_normalized == search_name_normalized or poke_name == search_name:
                    pokemon_data = poke
                    break
            if pokemon_data:
                break
        
        if not pokemon_data:
            if search_name.startswith("mega "):
                reversed_name = search_name.replace("mega ", "", 1) + " mega"
                reversed_name_normalized = reversed_name.replace("'", "'").replace("'", "'")
                for poke_list in all_pokedex_lists:
                    for poke in poke_list:
                        poke_name = poke.get("Name", "").lower()
                        poke_name_normalized = poke_name.replace("'", "'").replace("'", "'")
                        if poke_name_normalized == reversed_name_normalized or poke_name == reversed_name:
                            pokemon_data = poke
                            break
                    if pokemon_data:
                        break
    
    if not pokemon_data:
        await ctx.send(f"Pokémon '{query}' not found in Pokédex!")
        return
    
    type_emojis = {
        'normal': '<:normal_type:1406551478184706068>', 'fire': '<:fire_type:1406552697653559336>', 
        'water': '<:water_type:1406552467319029860>', 'electric': '<:electric_type:1406551930406436935>', 
        'grass': '<:grass_type:1406552601415122945>', 'ice': '<:ice_type:1406553274584399934>', 
        'fighting': '<:fighting_type:1406551764483702906>', 'poison': '<:poison_type:1406555023382413343>', 
        'ground': '<:ground_type:1406552961253117993>', 'flying': '<:flying_type:1406553554897862779>',
        'psychic': '<:psychic_type:1406552310808576122>', 'bug': '<:bug_type:1406555435980427358>', 
        'rock': '<:rock_type:1406552394950512711>', 'ghost': '<:ghost_type:1406553684887998484>', 
        'dragon': '<:dragon_type:1406552069669916742>', 'dark': '<:dark_type:1406553165624774666>', 
        'steel': '<:steel_type:1406552865291501629>', 'fairy': '<:fairy_type:1406552167283691691>'
    }
    
    gender_emoji_map = {
        'male': '<:male:1400956267979214971>',
        'female': '<:female:1400956073573224520>',
        'genderless': '<:unknown:1401145566863560755>'
    }
    
    embed = discord.Embed(
        title=f"**#{pokemon_data['ID']} {pokemon_data['Name']}**",
        description=pokemon_data.get('Pokedex Entry', ''),
        color=0xFFD700
    )
    
    types_text = ""
    for poke_type in pokemon_data.get('Types', []):
        type_emoji = type_emojis.get(poke_type.lower(), '⚪')
        types_text += f"{type_emoji} {poke_type}\n"
    if types_text:
        embed.add_field(name="**Types**", value=types_text, inline=False)
    
    embed.add_field(name="**Region**", value=pokemon_data.get('Region', 'Unknown'), inline=False)
    embed.add_field(name="**Catchable**", value=pokemon_data.get('Catchable', 'Unknown'), inline=False)
    
    base_stats = pokemon_data.get('Base Stats', {})
    stats_text = f"**HP:** {base_stats.get('Hp', 0)}\n"
    stats_text += f"**Attack:** {base_stats.get('Attack', 0)}\n"
    stats_text += f"**Defense:** {base_stats.get('Defense', 0)}\n"
    stats_text += f"**Sp. Atk:** {base_stats.get('Special Attack', 0)}\n"
    stats_text += f"**Sp. Def:** {base_stats.get('Special Defense', 0)}\n"
    stats_text += f"**Speed:** {base_stats.get('Speed', 0)}\n"
    stats_text += f"**Total: {base_stats.get('Total', 0)}**"
    embed.add_field(name="**Base Stats**", value=stats_text, inline=False)
    
    appearance = pokemon_data.get('Appearance', {})
    appearance_text = f"Height: {appearance.get('Height', 'Unknown')}\n"
    appearance_text += f"Weight: {appearance.get('Weight', 'Unknown')}"
    embed.add_field(name="**Appearance**", value=appearance_text, inline=False)
    
    gender_ratio = pokemon_data.get('Gender Ratio', {})
    is_genderless = False
    if isinstance(gender_ratio, dict) and gender_ratio:
        male_pct = gender_ratio.get('Male', '')
        female_pct = gender_ratio.get('Female', '')
        
        if male_pct == "Genderless" or female_pct == "Genderless" or (not male_pct and not female_pct):
            gender_text = f"{gender_emoji_map['genderless']} Genderless"
            is_genderless = True
        elif male_pct or female_pct:
            gender_text = f"{gender_emoji_map['male']} {male_pct} - {gender_emoji_map['female']} {female_pct}"
        else:
            gender_text = f"{gender_emoji_map['genderless']} Genderless"
            is_genderless = True
    else:
        gender_text = f"{gender_emoji_map['genderless']} Genderless"
        is_genderless = True
    embed.add_field(name="**Gender Ratio**", value=gender_text, inline=False)
    
    egg_groups = pokemon_data.get('Egg Groups', [])
    if egg_groups and egg_groups != ['Undiscovered'] and not is_genderless:
        egg_text = '\n'.join(egg_groups)
    else:
        egg_text = "Undiscovered"
    embed.add_field(name="**Egg Groups**", value=egg_text, inline=False)
    
    hatch_time = pokemon_data.get('Hatch Time', '')
    if is_genderless or egg_text == "Undiscovered":
        hatch_time = "Undiscovered"
    embed.add_field(name="**Hatch Time**", value=hatch_time, inline=False)
    
    artwork_file = pokemon_data.get('Artwork', '')
    if artwork_file and os.path.exists(artwork_file):
        file = discord.File(artwork_file, filename="artwork.png")
        embed.set_image(url="attachment://artwork.png")
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)
 
bot.run(os.getenv('DISCORD_BOT_TOKEN'))