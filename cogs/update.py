import discord

from discord.ext import commands
from discord import app_commands

from database import query_one
from role_sync import sync_group_role


class UpdateRoles(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="update",
        description="Update your Discord roles from Roblox."
    )
    async def updateroles(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.defer(
            ephemeral=True
        )

        linked = query_one(
            """
            SELECT roblox_name, roblox_id
            FROM verify
            WHERE discord_id=?
            """,
            (
                str(interaction.user.id),
            )
        )

        if not linked:
            await interaction.followup.send(
                "❌ You are not verified. Use `/verify` first.",
                ephemeral=True
            )
            return

        roblox_name, roblox_id = linked

        try:
            result = await sync_group_role(
                interaction.user,
                roblox_id
            )

        except Exception as error:
            await interaction.followup.send(
                f"❌ Could not update roles:\n`{error}`",
                ephemeral=True
            )
            return

        if not result["success"]:
            await interaction.followup.send(
                f"⚠️ {result['message']}",
                ephemeral=True
            )
            return

        role_name = result.get(
            "roblox_role",
            "Unknown"
        )

        added = result.get(
            "added",
            []
        )

        if added:
            changes = ", ".join(
                added
            )

            message = (
                "✅ **Roles Updated**\n\n"
                f"Roblox: **{roblox_name}**\n"
                f"Group Role: **{role_name}**\n"
                f"Added: **{changes}**"
            )

        else:
            message = (
                "✅ **Roles Already Up to Date**\n\n"
                f"Roblox: **{roblox_name}**\n"
                f"Group Role: **{role_name}**"
            )

        await interaction.followup.send(
            message,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(
        UpdateRoles(bot)
    )