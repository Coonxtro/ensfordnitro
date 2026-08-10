import os
import time
import secrets
from urllib.parse import urlencode

import discord

from discord.ext import commands
from discord import app_commands

from database import execute, query_one


ROBLOX_OAUTH_CLIENT_ID = os.getenv(
    "ROBLOX_OAUTH_CLIENT_ID"
)

ROBLOX_OAUTH_REDIRECT_URI = os.getenv(
    "ROBLOX_OAUTH_REDIRECT_URI"
)

STATE_LIFETIME = 10 * 60


class VerifyLinkView(discord.ui.View):

    def __init__(self, url):
        super().__init__(timeout=600)

        self.add_item(
            discord.ui.Button(
                label="Verify with Roblox",
                style=discord.ButtonStyle.link,
                url=url,
                emoji="🔗"
            )
        )


class Verify(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="verify",
        description="Link and verify your Roblox account."
    )
    async def verify(
        self,
        interaction: discord.Interaction
    ):
        existing = query_one(
            """
            SELECT roblox_name, roblox_id
            FROM verify
            WHERE discord_id=?
            """,
            (
                str(interaction.user.id),
            )
        )

        if existing:
            await interaction.response.send_message(
                (
                    "✅ Your account is already verified.\n\n"
                    f"Roblox: **{existing[0]}**"
                ),
                ephemeral=True
            )
            return

        if not ROBLOX_OAUTH_CLIENT_ID:
            await interaction.response.send_message(
                "❌ Roblox OAuth is not configured.",
                ephemeral=True
            )
            return

        state = secrets.token_urlsafe(32)

        expires_at = int(
            time.time() + STATE_LIFETIME
        )

        execute(
            """
            INSERT OR REPLACE INTO oauth_states
            (
                state,
                discord_id,
                expires_at
            )
            VALUES (?, ?, ?)
            """,
            (
                state,
                str(interaction.user.id),
                expires_at
            )
        )

        params = {
            "client_id": ROBLOX_OAUTH_CLIENT_ID,
            "redirect_uri": ROBLOX_OAUTH_REDIRECT_URI,
            "scope": "openid profile",
            "response_type": "code",
            "state": state
        }

        url = (
            "https://apis.roblox.com/oauth/v1/authorize?"
            + urlencode(params)
        )

        embed = discord.Embed(
            title="Ensford Roblox Verification",
            description=(
                "Press the button below to verify ownership "
                "of your Roblox account.\n\n"
                "You will be redirected to Roblox to authorize "
                "the Ensford verification application.\n\n"
                "**This link expires in 10 minutes.**"
            ),
            color=discord.Color.blue()
        )

        embed.set_footer(
            text="Ensford • Roblox Verification"
        )

        await interaction.response.send_message(
            embed=embed,
            view=VerifyLinkView(url),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(
        Verify(bot)
    )