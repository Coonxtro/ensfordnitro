# bot.py
print("bot starting")
print(__name__)
print("bot starting")
import os
import logging
import asyncio
from threading import Thread
from dotenv import load_dotenv
from flask import Flask
import os
import time
from urllib.parse import quote_plus
import requests
from discord import Intents
from discord.ext import commands
from waitress import serve
from api.assign_role import assign_role_bp
from api.monitor import monitor_bp
from database import init_db
import keep_alive  # importamos el módulo completo para exponer `keep_alive.app`

# --- Configuración ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 3000))
DEBUG_MODE = os.getenv("DEBUG", "False").lower() in ("1", "true", "yes")

# --- Logging ---
if not DEBUG_MODE:
    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] %(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Flask principal ---
app = Flask(__name__)
app.register_blueprint(assign_role_bp)
app.register_blueprint(monitor_bp)

# --- Discord Bot ---
intents = Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    await bot.tree.sync()
    if DEBUG_MODE:
        logger.debug(f"Bot ready: {bot.user}")
    else:
        logger.info(f"Bot ready: {bot.user}")

# --- Funciones de arranque ---


def run_api_server():
    serve(app, host="0.0.0.0", port=PORT)


# def run_keep_alive_server():
#     serve(keep_alive.app, host="0.0.0.0", port=8080)


# --- Main ---
async def setup_hook():
    print("loading link")
    await bot.load_extension("cogs.link")

    print("loading unlink")
    await bot.load_extension("cogs.unlink")

    print("loading claimboost")
    await bot.load_extension("cogs.claimboost")

    synced = await bot.tree.sync()
    print(f"synced {len(synced)} commands")


bot.setup_hook = setup_hook

if __name__ == "__main__":
    init_db()

    Thread(target=run_api_server, daemon=True).start()

    print("BOT_TOKEN =", BOT_TOKEN is not None)

    bot.run(BOT_TOKEN)