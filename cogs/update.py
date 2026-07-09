import json
import os
import discord
from discord.ext import commands
from discord import app_commands

UPDATE_CHANNEL_ID = int(os.getenv("UPDATE_CHANNEL_ID"))


def bullets(text: str):
    if not text.strip():
        return "*None*"
    return "\n".join(f"• {line.strip()}" for line in text.splitlines() if line.strip())


def get_version():
    try:
        with open("version.json", "r") as f:
            data = json.load(f)
            return data["version"], data["build"]
    except:
        return "Unknown", "?"


class UpdateModal(discord.ui.Modal, title="Publish Update"):

    new_features = discord.ui.TextInput(
        label="✨ New Features",
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder="One feature per line"
    )

    qol = discord.ui.TextInput(
        label="⚙️ Quality of Life",
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder="One change per line"
    )

    bugfixes = discord.ui.TextInput(
        label="🐛 Bug Fixes",
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder="One fix per line"
    )

    notes = discord.ui.TextInput(
        label="📝 Developer Notes",
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder="Anything else..."
    )

    async def on_submit(self, interaction: discord.Interaction):

        version, build = get_version()

        embed = discord.Embed(
            title="🚀 ENSFORD UPDATE",
            description=f"**Version:** `{version}` • **Build:** `#{build}`",
            color=discord.Color.blue()
        )

        if self.new_features.value.strip():
            embed.add_field(
                name="✨ New Features",
                value=bullets(self.new_features.value),
                inline=False
            )

        if self.qol.value.strip():
            embed.add_field(
                name="⚙️ Quality of Life",
                value=bullets(self.qol.value),
                inline=False
            )

        if self.bugfixes.value.strip():
            embed.add_field(
                name="🐛 Bug Fixes",
                value=bullets(self.bugfixes.value),
                inline=False
            )

        if self.notes.value.strip():
            embed.add_field(
                name="📝 Developer Notes",
                value=self.notes.value,
                inline=False
            )

        embed.set_footer(
            text=f"Published by {interaction.user.display_name}"
        )

        embed.timestamp = discord.utils.utcnow()

        channel = interaction.client.get_channel(UPDATE_CHANNEL_ID)

        await channel.send(embed=embed)

        await interaction.response.send_message(
            "✅ Update posted.",
            ephemeral=True
        )


class Update(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="update",
        description="Publish a game update."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def update(self, interaction: discord.Interaction):

        await interaction.response.send_modal(UpdateModal())


async def setup(bot):
    await bot.add_cog(Update(bot))