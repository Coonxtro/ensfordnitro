from discord import app_commands, Interaction, Embed, Color
from discord.ext import commands
from database import execute

class Unlink(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="unlink")
    async def slash(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        did = str(interaction.user.id)
        deleted = execute("DELETE FROM verify WHERE discord_id=?", (did,))
        if deleted:
            embed = Embed(
                title="Unlinked",
                description="✅ Account successfully unlinked!",
                color=Color.green()
            )
        else:
            embed = Embed(
                title="Unlink",
                description="⚠️ No linked account found.",
                color=Color.gold()
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Unlink(bot))