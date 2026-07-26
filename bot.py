import os
import time
import asyncio
import logging
from threading import Thread
import discord
from dotenv import load_dotenv
from flask import Flask
from discord import Intents, guild
from discord.ext import commands
from waitress import serve

from api.assign_role import assign_role_bp
from api.monitor import monitor_bp, check_server_end, get_game_status
from database import init_db

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 3000))

app = Flask(__name__)

# register ALL APIs
app.register_blueprint(assign_role_bp)
app.register_blueprint(monitor_bp)

intents = Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


def run_api():
    serve(app, host="0.0.0.0", port=PORT)


@bot.event

async def monitor_loop():
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            check_server_end(bot)

            game_status = get_game_status()
            player_count = game_status["player_count"]
            build = game_status["build"]

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

        except Exception:
            logging.exception("Failed to update monitor status")

        await asyncio.sleep(15)

async def setup_hook():

    await bot.load_extension("cogs.link")
    await bot.load_extension("cogs.unlink")
    await bot.load_extension("cogs.claimboost")
    await bot.load_extension("cogs.update")
    bot.loop.create_task(monitor_loop())
    #await bot.tree.sync()
    guild = discord.Object(id=778045351260455022)
    synced = await bot.tree.sync(guild=guild)
    print(f"Synced {len(synced)} commands")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


if __name__ == "__main__":
    init_db()

    Thread(target=run_api, daemon=True).start()

    bot.run(BOT_TOKEN)