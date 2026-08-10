import os
import time
import asyncio
import discord

from discord.ext import commands
from discord import app_commands

from database import query_one, execute


APPLICATION_CHANNEL_ID = int(os.getenv("APPLICATION_CHANNEL_ID", "0"))
APPLICATION_REVIEW_CHANNEL_ID = int(
    os.getenv("APPLICATION_REVIEW_CHANNEL_ID", "0")
)

APPLICATION_TIMEOUT = 3 * 60 * 60


QUESTIONS = [
    "What is your Roblox username?",

    "Please link your Roblox profile.",

    """Are you pending for the main Ensford group?

If you aren't pending, you will not be accepted.

https://www.roblox.com/communities/5642568/Ensford""",

    "Are you 16 years of age or older?",

    "Do you have Roblox Voice Chat?",

    "What other roleplay communities have you been a part of?",

    """Please create a quick character that you could play in Ensford.

Include:
• RP Name
• Date of Birth
• Place of Birth
• A short description of your character""",

    "What timezone are you in?",

    "What country are you from?",

    "How did you hear about Ensford?",

    """Do you have any connections in Ensford, such as friends or people you know?

If so, who?"""
]


def application_expired(started_at):
    return int(time.time()) - int(started_at) >= APPLICATION_TIMEOUT


class ConfirmApplicationView(discord.ui.View):

    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot

    @discord.ui.button(
        label="Start Application",
        style=discord.ButtonStyle.success,
        emoji="✅"
    )
    async def start(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        existing = query_one(
            """
            SELECT started_at, current_question, status
            FROM whitelist_applications
            WHERE discord_id=?
            """,
            (str(interaction.user.id),)
        )

        if existing:
            started_at, current_question, status = existing

            if status == "active" and not application_expired(started_at):
                await interaction.response.send_message(
                    "You already have an active application.",
                    ephemeral=True
                )
                return

            execute(
                "DELETE FROM whitelist_applications WHERE discord_id=?",
                (str(interaction.user.id),)
            )

            execute(
                "DELETE FROM whitelist_answers WHERE discord_id=?",
                (str(interaction.user.id),)
            )

        now = int(time.time())

        execute(
            """
            INSERT INTO whitelist_applications
            (discord_id, started_at, current_question, status)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(interaction.user.id),
                now,
                0,
                "active"
            )
        )

        await interaction.response.edit_message(
            content=(
                "✅ **Application Started**\n\n"
                "I will now begin asking you questions.\n"
                "You have **3 hours** to complete the application.\n\n"
                "You may type `cancel` at any time to stop."
            ),
            embed=None,
            view=None
        )

        await ask_questions(self.bot, interaction.user)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.danger,
        emoji="✖️"
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="Application cancelled.",
            embed=None,
            view=None
        )


class ApplicationPanelView(discord.ui.View):

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Start Application",
        style=discord.ButtonStyle.primary,
        emoji="📝",
        custom_id="ensford_whitelist_start"
    )
    async def start_application(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        try:
            dm = interaction.user.dm_channel

            if dm is None:
                dm = await interaction.user.create_dm()

            embed = discord.Embed(
                title="Ensford Whitelist Application",
                description=(
                    "**Are you sure you want to apply?**\n\n"
                    "Once you start the application, I will send you "
                    "a series of questions.\n\n"
                    "You will have **3 hours** to complete the application. "
                    "If you do not complete the application in time, "
                    "you will have to restart.\n\n"
                    "If you wish to stop the application, you may cancel "
                    "at any time."
                ),
                color=discord.Color.blue()
            )

            embed.set_footer(
                text="Ensford Whitelist • Application System"
            )

            await dm.send(
                embed=embed,
                view=ConfirmApplicationView(self.bot)
            )

            await interaction.response.send_message(
                "📨 Check your DMs to begin your application.",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "I couldn't DM you. Please enable DMs from server members "
                "and try again.",
                ephemeral=True
            )


async def ask_questions(bot, user):

    discord_id = str(user.id)

    application = query_one(
        """
        SELECT started_at, current_question
        FROM whitelist_applications
        WHERE discord_id=? AND status='active'
        """,
        (discord_id,)
    )

    if not application:
        return

    started_at, current_question = application

    dm = user.dm_channel or await user.create_dm()

    for index in range(current_question, len(QUESTIONS)):

        if application_expired(started_at):
            await dm.send(
                "⏰ **Application Expired**\n\n"
                "Your 3-hour application window has expired. "
                "Please start a new application from the server."
            )

            execute(
                """
                UPDATE whitelist_applications
                SET status='expired'
                WHERE discord_id=?
                """,
                (discord_id,)
            )

            return

        question = QUESTIONS[index]

        embed = discord.Embed(
            title=f"Question {index + 1} of {len(QUESTIONS)}",
            description=question,
            color=discord.Color.blurple()
        )

        remaining = (
            APPLICATION_TIMEOUT
            - (int(time.time()) - int(started_at))
        )

        embed.set_footer(
            text=f"Time remaining: approximately {remaining // 60} minutes"
        )

        await dm.send(embed=embed)

        def check(message):
            return (
                message.author.id == user.id
                and isinstance(message.channel, discord.DMChannel)
            )

        remaining_timeout = (
            APPLICATION_TIMEOUT
            - (int(time.time()) - int(started_at))
        )

        if remaining_timeout <= 0:
            return

        try:
            message = await bot.wait_for(
                "message",
                timeout=remaining_timeout,
                check=check
            )

        except asyncio.TimeoutError:

            execute(
                """
                UPDATE whitelist_applications
                SET status='expired'
                WHERE discord_id=?
                """,
                (discord_id,)
            )

            await dm.send(
                "⏰ Your application expired because the "
                "3-hour time limit was reached."
            )

            return

        if message.content.strip().lower() == "cancel":

            execute(
                """
                UPDATE whitelist_applications
                SET status='cancelled'
                WHERE discord_id=?
                """,
                (discord_id,)
            )

            await dm.send(
                "❌ Your application has been cancelled."
            )

            return

        execute(
            """
            INSERT OR REPLACE INTO whitelist_answers
            (discord_id, question_number, question, answer)
            VALUES (?, ?, ?, ?)
            """,
            (
                discord_id,
                index,
                question,
                message.content.strip()
            )
        )

        execute(
            """
            UPDATE whitelist_applications
            SET current_question=?
            WHERE discord_id=?
            """,
            (
                index + 1,
                discord_id
            )
        )

    await submit_application(bot, user)


async def submit_application(bot, user):

    discord_id = str(user.id)

    execute(
        """
        UPDATE whitelist_applications
        SET status='submitted'
        WHERE discord_id=?
        """,
        (discord_id,)
    )

    review_channel = bot.get_channel(
        APPLICATION_REVIEW_CHANNEL_ID
    )

    if not review_channel:
        try:
            review_channel = await bot.fetch_channel(
                APPLICATION_REVIEW_CHANNEL_ID
            )
        except Exception:
            review_channel = None

    answers = []

    for index, question in enumerate(QUESTIONS):

        row = query_one(
            """
            SELECT answer
            FROM whitelist_answers
            WHERE discord_id=? AND question_number=?
            """,
            (
                discord_id,
                index
            )
        )

        answer = row[0] if row else "No response"

        answers.append(
            (
                question,
                answer
            )
        )

    if review_channel:

        embed = discord.Embed(
            title="📋 New Ensford Whitelist Application",
            description=(
                f"**Applicant:** {user.mention}\n"
                f"**Discord:** `{user}`\n"
                f"**Discord ID:** `{user.id}`"
            ),
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )

        embed.set_thumbnail(
            url=user.display_avatar.url
        )

        for index, (question, answer) in enumerate(answers):

            field_value = answer

            if len(field_value) > 1000:
                field_value = field_value[:997] + "..."

            embed.add_field(
                name=f"{index + 1}. {question[:200]}",
                value=field_value,
                inline=False
            )

        embed.set_footer(
            text="Ensford Whitelist Application"
        )

        await review_channel.send(embed=embed)

    dm = user.dm_channel or await user.create_dm()

    finished = discord.Embed(
        title="✅ Application Submitted",
        description=(
            "Your Ensford whitelist application has been submitted "
            "successfully.\n\n"
            "Staff will review your application. "
            "Please be patient while a decision is made."
        ),
        color=discord.Color.green()
    )

    await dm.send(embed=finished)


class Whitelist(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="whitelistpanel",
        description="Post the Ensford whitelist application panel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelistpanel(
        self,
        interaction: discord.Interaction
    ):

        channel = interaction.channel

        embed = discord.Embed(
            title="Ensford Whitelist Applications",
            description=(
                "Interested in becoming a whitelisted member of Ensford?\n\n"
                "Press **Start Application** below to begin.\n\n"
                "📨 The application will take place in your DMs.\n"
                "⏱️ You will have **3 hours** to complete it.\n"
                "🔞 Applicants must meet Ensford's age requirements.\n"
                "🎙️ Roblox Voice Chat is required."
            ),
            color=discord.Color.blue()
        )

        embed.set_footer(
            text="Ensford • Whitelist Applications"
        )

        await channel.send(
            embed=embed,
            view=ApplicationPanelView(self.bot)
        )

        await interaction.response.send_message(
            "✅ Whitelist application panel posted.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Whitelist(bot))