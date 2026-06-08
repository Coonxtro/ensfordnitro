from discord import app_commands, Interaction, Role, Embed, Color
from discord.ext import commands
from database import execute


class AddMapping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="addmapping")
    @app_commands.describe(
        achievement="Key for achievement trigger",
        role="Discord role to assign"
    )
    async def slash(
        self,
        interaction: Interaction,
        achievement: str,
        role: Role
    ):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.manage_roles:
            embed = Embed(
                title="Permission Denied",
                description="❌ You do not have permission to use this command.",
                color=Color.red()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        guild_id = str(interaction.guild_id)
        execute(
            "INSERT OR REPLACE INTO role_mappings (guild_id, achievement, role_id) VALUES (?,?,?)",
            (guild_id, achievement, str(role.id))
        )
        embed = Embed(
            title="Mapping Created",
            description=f"✅ `{achievement}` → {role.mention}",
            color=Color.blue()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AddMapping(bot))
