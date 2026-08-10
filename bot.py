import os
import time
import asyncio
import logging
from threading import Thread

import discord
from dotenv import load_dotenv
from flask import Flask
from discord import Intents
from discord.ext import commands
from waitress import serve

from api.assign_role import assign_role_bp
from api.monitor import monitor_bp, check_server_end, get_game_status
from database import init_db
from api.oauth import oauth_bp
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 3000))
GUILD_ID = 778045351260455022

app = Flask(__name__)

app.register_blueprint(assign_role_bp)
app.register_blueprint(monitor_bp)
app.register_blueprint(oauth_bp)

intents = Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


def run_api():
    serve(app, host="0.0.0.0", port=PORT)


async def update_bot_status():
    await bot.wait_until_ready()

    print("Status loop started")

    while not bot.is_closed():
        try:
            check_server_end(bot)

            game_status = get_game_status()

            player_count = game_status.get("player_count", 0)
            build = game_status.get("build", "Unknown")

            if player_count > 0:
                player_word = "player" if player_count == 1 else "players"

                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{player_count} {player_word} in Ensford"
                )
            else:
                activity = discord.Game(
                    name=f"Ensford | Build {build}"
                )

            await bot.change_presence(
                status=discord.Status.online,
                activity=activity
            )

            print(
                f"Updated bot status: "
                f"players={player_count}, build={build}"
            )

        except Exception:
            logging.exception("Failed to update Discord bot status")

        await asyncio.sleep(15)


async def setup_hook():
    await bot.load_extension("cogs.link")
    await bot.load_extension("cogs.unlink")
    await bot.load_extension("cogs.claimboost")
    await bot.load_extension("cogs.updatelog")
    await bot.load_extension("cogs.whitelist")
    await bot.load_extension("cogs.verify")
    await bot.load_extension("cogs.updateroles")

    guild = discord.Object(id=778045351260455022)

    # Clear old guild commands first
    bot.tree.clear_commands(guild=guild)

    # Copy current global commands into this guild
    bot.tree.copy_global_to(guild=guild)

    synced = await bot.tree.sync(guild=guild)

    print(f"Synced {len(synced)} commands")

    for command in synced:
        print(f"/{command.name}")


# This must be outside setup_hook
bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


if __name__ == "__main__":
    init_db()

    Thread(target=run_api, daemon=True).start()

    bot.run(BOT_TOKEN)