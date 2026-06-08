import time

from discord import app_commands, Interaction
from discord.ext import commands

from database import query_one, execute

BOOSTER_ROLE_ID = 792146055914717235
REWARD_AMOUNT = 5000
COOLDOWN_SECONDS = 30 * 24 * 60 * 60
ADMIN_IDS = {
    580509062723010590
}

class ClaimBoost(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="claimboost",
        description="Claim your monthly Nitro Booster reward"
    )
    async def claimboost(self, interaction: Interaction):

        await interaction.response.defer(ephemeral=True)

        member = interaction.user

     

        if (
            interaction.user.id not in ADMIN_IDS
            and not any(role.id == BOOSTER_ROLE_ID for role in member.roles)
        ):
            await interaction.followup.send(
                "You must be a Nitro Booster to claim this reward.",
                ephemeral=True
            )
            return

        user = query_one(
            "SELECT roblox_id FROM verify WHERE discord_id=?",
            (str(interaction.user.id),)
        )

        if not user:
            await interaction.followup.send(
                "Link your Roblox account first using /link",
                ephemeral=True
            )
            return

        roblox_id = user[0]

        last_claim = query_one(
            "SELECT last_claim FROM booster_claims WHERE discord_id=?",
            (str(interaction.user.id),)
        )

        now = int(time.time())

        if last_claim:
            elapsed = now - last_claim[0]

            if elapsed < COOLDOWN_SECONDS:
                days_left = (COOLDOWN_SECONDS - elapsed) // 86400

                await interaction.followup.send(
                    f"You have already claimed your booster reward. Try again in approximately {days_left} day(s).",
                    ephemeral=True
                )
                return

        execute(
            """
            INSERT INTO pending_rewards
            (discord_id, roblox_id, amount)
            VALUES (?, ?, ?)
            """,
            (
                str(interaction.user.id),
                str(roblox_id),
                REWARD_AMOUNT
            )
        )

        execute(
            """
            INSERT OR REPLACE INTO booster_claims
            (discord_id, last_claim)
            VALUES (?, ?)
            """,
            (
                str(interaction.user.id),
                now
            )
        )

        await interaction.followup.send(
            f"${REWARD_AMOUNT:,} has been queued for your Roblox account.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(ClaimBoost(bot))