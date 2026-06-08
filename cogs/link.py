from discord import app_commands, Interaction, Embed, Color
from discord.ext import commands
from database import query_one, execute
from R import fetch_roblox_id

class Link(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="link")
    @app_commands.describe(roblox_name="Roblox username to link")
    async def slash(self, interaction: Interaction, roblox_name: str):
        await interaction.response.defer(ephemeral=True)
        rn = roblox_name.strip()
        did = str(interaction.user.id)
        rid = str(fetch_roblox_id(rn))
        result = {}
        if not int(rid):
            result = {"error": "❌ **Roblox user not found**"}
        elif query_one(
            "SELECT 1 FROM verify WHERE discord_id=? OR roblox_id=?", (
                did, rid)
        ):
            result = {"error": "⚠️ **Already linked**"}
        else:
            execute(
                "INSERT INTO verify (roblox_name, roblox_id, discord_name, discord_id) VALUES (?,?,?,?)",
                (rn, rid, str(interaction.user), did)
            )
            result = {"status": "✅ **Linked successfully**"}
        title = "Error" if "error" in result else "Linked"
        color = Color.red() if "error" in result else Color.green()
        embed = Embed(title=title, description=list(
            result.values())[0], color=color)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Link(bot))
