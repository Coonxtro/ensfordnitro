import os
import re
import time
import asyncio
import requests
import discord

from discord.ext import commands
from discord import app_commands

from database import query_one, execute
from R import fetch_roblox_id


APPLICATION_REVIEW_CHANNEL_ID = int(
    os.getenv("APPLICATION_REVIEW_CHANNEL_ID", "0")
)

RESIDENT_ROLE_ID = int(
    os.getenv("RESIDENT_ROLE_ID", "0")
)

ROBLOX_GROUP_ID = os.getenv("ROBLOX_GROUP_ID", "5642568")
ROBLOX_OPEN_CLOUD_KEY = os.getenv("ROBLOX_OPEN_CLOUD_KEY")

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


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def expired(started_at):
    return int(time.time()) - int(started_at) >= APPLICATION_TIMEOUT


def get_answer(discord_id, question_number):
    row = query_one(
        """
        SELECT answer
        FROM whitelist_answers
        WHERE discord_id=? AND question_number=?
        """,
        (str(discord_id), question_number)
    )

    return row[0] if row else None


def get_applicant_id_from_message(message):
    if not message.embeds:
        return None

    footer = message.embeds[-1].footer.text or ""

    match = re.search(r"Applicant ID:\s*(\d+)", footer)

    if not match:
        return None

    return int(match.group(1))


def get_roblox_user_id(discord_id):
    # Question 2 should be their Roblox profile URL
    profile = get_answer(discord_id, 1)

    if profile:
        match = re.search(
            r"roblox\.com/users/(\d+)",
            profile,
            re.IGNORECASE
        )

        if match:
            return int(match.group(1))

    # Fallback to username from question 1
    username = get_answer(discord_id, 0)

    if not username:
        return None

    try:
        roblox_id = fetch_roblox_id(username.strip())

        if roblox_id:
            return int(roblox_id)

    except Exception:
        pass

    return None


def roblox_headers():
    return {
        "x-api-key": ROBLOX_OPEN_CLOUD_KEY,
        "Content-Type": "application/json"
    }


def contains_user_id(obj, target):
    target = str(target)

    if isinstance(obj, dict):

        for key, value in obj.items():

            key_lower = key.lower()

            if key_lower in (
                "userid",
                "user_id",
                "user",
                "userid"
            ):
                if isinstance(value, (str, int)):
                    if target == str(value):
                        return True

                if isinstance(value, dict):
                    if contains_user_id(value, target):
                        return True

            if contains_user_id(value, target):
                return True

    elif isinstance(obj, list):

        for item in obj:
            if contains_user_id(item, target):
                return True

    elif isinstance(obj, str):

        if obj.endswith("/users/" + target):
            return True

    return False


def extract_join_request_id(obj):
    if not isinstance(obj, dict):
        return None

    possible_keys = (
        "joinRequestId",
        "join_request_id",
        "id"
    )

    for key in possible_keys:

        value = obj.get(key)

        if value:
            return str(value)

    for key in ("path", "name"):

        value = obj.get(key)

        if value and "join-requests/" in str(value):
            return str(value).split("join-requests/")[-1].split("/")[0]

    return None


def search_join_request(data, roblox_id):
    if isinstance(data, dict):

        if contains_user_id(data, roblox_id):

            request_id = extract_join_request_id(data)

            if request_id:
                return request_id

        for value in data.values():

            result = search_join_request(value, roblox_id)

            if result:
                return result

    elif isinstance(data, list):

        for item in data:

            result = search_join_request(item, roblox_id)

            if result:
                return result

    return None


def get_join_request_id(roblox_id):
    if not ROBLOX_OPEN_CLOUD_KEY:
        raise RuntimeError(
            "ROBLOX_OPEN_CLOUD_KEY is not configured."
        )

    url = (
        f"https://apis.roblox.com/cloud/v2/groups/"
        f"{ROBLOX_GROUP_ID}/join-requests"
    )

    response = requests.get(
        url,
        headers=roblox_headers(),
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    return search_join_request(
        data,
        roblox_id
    )


def accept_roblox_join_request(roblox_id):
    join_request_id = get_join_request_id(
        roblox_id
    )

    if not join_request_id:
        return False, (
            "No pending Roblox group request was found "
            "for this applicant."
        )

    url = (
        f"https://apis.roblox.com/cloud/v2/groups/"
        f"{ROBLOX_GROUP_ID}/join-requests/"
        f"{join_request_id}:accept"
    )

    response = requests.post(
        url,
        headers=roblox_headers(),
        json={},
        timeout=15
    )

    if response.status_code not in (200, 201, 204):
        return False, (
            f"Roblox returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    return True, "Roblox group request accepted."


def decline_roblox_join_request(roblox_id):
    join_request_id = get_join_request_id(
        roblox_id
    )

    if not join_request_id:
        # Denial should still work even if they were never pending
        return True, "No pending Roblox request existed."

    url = (
        f"https://apis.roblox.com/cloud/v2/groups/"
        f"{ROBLOX_GROUP_ID}/join-requests/"
        f"{join_request_id}:decline"
    )

    response = requests.post(
        url,
        headers=roblox_headers(),
        json={},
        timeout=15
    )

    if response.status_code not in (200, 201, 204):
        return False, (
            f"Roblox returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    return True, "Roblox group request declined."


def save_review(
    discord_id,
    status,
    reviewer_id,
    reason=""
):
    execute(
        """
        INSERT OR REPLACE INTO whitelist_reviews
        (
            discord_id,
            status,
            reviewer_id,
            reason,
            reviewed_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(discord_id),
            status,
            str(reviewer_id),
            reason,
            int(time.time())
        )
    )

    execute(
        """
        UPDATE whitelist_applications
        SET status=?
        WHERE discord_id=?
        """,
        (
            status,
            str(discord_id)
        )
    )


async def get_user(bot, discord_id):
    user = bot.get_user(
        int(discord_id)
    )

    if user:
        return user

    return await bot.fetch_user(
        int(discord_id)
    )


def staff_allowed(interaction):
    if not isinstance(
        interaction.user,
        discord.Member
    ):
        return False

    return (
        interaction.user.guild_permissions.administrator
        or interaction.user.guild_permissions.manage_roles
    )


# --------------------------------------------------
# Request Changes modal
# --------------------------------------------------

class RequestChangesModal(
    discord.ui.Modal,
    title="Request Application Changes"
):

    request_text = discord.ui.TextInput(
        label="What should the applicant change?",
        placeholder=(
            "Example: Please provide more detail "
            "about your character's background."
        ),
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1500
    )

    def __init__(
        self,
        bot,
        applicant_id,
        review_message
    ):
        super().__init__()

        self.bot = bot
        self.applicant_id = applicant_id
        self.review_message = review_message

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        question = self.request_text.value.strip()

        save_review(
            self.applicant_id,
            "changes_required",
            interaction.user.id,
            question
        )

        applicant = await get_user(
            self.bot,
            self.applicant_id
        )

        embed = discord.Embed(
            title="📝 Changes Requested",
            description=(
                "Ensford staff have requested additional "
                "information for your whitelist application."
            ),
            color=discord.Color.orange()
        )

        embed.add_field(
            name="Staff Request",
            value=question,
            inline=False
        )

        embed.add_field(
            name="What to do",
            value=(
                "Reply to this DM with your updated answer. "
                "You have **3 hours** to respond."
            ),
            inline=False
        )

        try:
            await applicant.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                "The applicant has DMs disabled.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "✅ Change request sent. Waiting for their response.",
            ephemeral=True
        )

        asyncio.create_task(
            wait_for_change_response(
                self.bot,
                applicant,
                question,
                self.review_message,
                interaction.user
            )
        )


async def wait_for_change_response(
    bot,
    applicant,
    question,
    review_message,
    reviewer
):
    def check(message):
        return (
            message.author.id == applicant.id
            and isinstance(
                message.channel,
                discord.DMChannel
            )
        )

    try:
        response = await bot.wait_for(
            "message",
            timeout=APPLICATION_TIMEOUT,
            check=check
        )

    except asyncio.TimeoutError:

        try:
            await applicant.send(
                "⏰ Your requested-changes response expired. "
                "Please contact Ensford staff if you still "
                "wish to continue your application."
            )
        except Exception:
            pass

        return

    answer = response.content.strip()

    review_channel = review_message.channel

    embed = discord.Embed(
        title="📝 Applicant Change Response",
        description=applicant.mention,
        color=discord.Color.orange(),
        timestamp=discord.utils.utcnow()
    )

    embed.add_field(
        name="Staff Request",
        value=question[:1024],
        inline=False
    )

    embed.add_field(
        name="Applicant Response",
        value=answer[:1024],
        inline=False
    )

    embed.set_footer(
        text=(
            f"Applicant ID: {applicant.id} • "
            f"Requested by {reviewer}"
        )
    )

    await review_channel.send(
        embed=embed,
        view=ReviewView(bot)
    )

    save_review(
        applicant.id,
        "submitted",
        reviewer.id,
        "Applicant responded to requested changes."
    )

    try:
        await applicant.send(
            "✅ Your response has been sent back to Ensford staff."
        )
    except Exception:
        pass


# --------------------------------------------------
# Denial modal
# --------------------------------------------------

class DenyModal(
    discord.ui.Modal,
    title="Deny Whitelist Application"
):

    reason = discord.ui.TextInput(
        label="Reason for denial",
        placeholder=(
            "Explain why the application is being denied."
        ),
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1500
    )

    def __init__(
        self,
        bot,
        applicant_id,
        review_message
    ):
        super().__init__()

        self.bot = bot
        self.applicant_id = applicant_id
        self.review_message = review_message

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.defer(
            ephemeral=True
        )

        reason = self.reason.value.strip()

        roblox_id = get_roblox_user_id(
            self.applicant_id
        )

        roblox_message = (
            "No Roblox account could be resolved."
        )

        if roblox_id:
            try:
                _, roblox_message = (
                    decline_roblox_join_request(
                        roblox_id
                    )
                )
            except Exception as error:
                roblox_message = (
                    f"Roblox decline failed: {error}"
                )

        save_review(
            self.applicant_id,
            "denied",
            interaction.user.id,
            reason
        )

        applicant = await get_user(
            self.bot,
            self.applicant_id
        )

        embed = discord.Embed(
            title="❌ Ensford Whitelist Application",
            description=(
                "Your whitelist application has been denied."
            ),
            color=discord.Color.red()
        )

        embed.add_field(
            name="Reason",
            value=reason,
            inline=False
        )

        try:
            await applicant.send(embed=embed)
        except Exception:
            pass

        old_embed = (
            self.review_message.embeds[-1]
            if self.review_message.embeds
            else discord.Embed()
        )

        old_embed.color = discord.Color.red()

        old_embed.add_field(
            name="❌ Decision",
            value=(
                f"Denied by {interaction.user.mention}\n"
                f"**Reason:** {reason}\n"
                f"**Roblox:** {roblox_message}"
            )[:1024],
            inline=False
        )

        await self.review_message.edit(
            embed=old_embed,
            view=None
        )

        await interaction.followup.send(
            "Application denied.",
            ephemeral=True
        )


# --------------------------------------------------
# Accept note modal
# --------------------------------------------------

class AcceptModal(
    discord.ui.Modal,
    title="Accept Whitelist Application"
):

    note = discord.ui.TextInput(
        label="Acceptance note",
        placeholder=(
            "Optional message for the applicant."
        ),
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    def __init__(
        self,
        bot,
        applicant_id,
        review_message
    ):
        super().__init__()

        self.bot = bot
        self.applicant_id = applicant_id
        self.review_message = review_message

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.defer(
            ephemeral=True
        )

        roblox_id = get_roblox_user_id(
            self.applicant_id
        )

        if not roblox_id:
            await interaction.followup.send(
                "❌ I couldn't determine the applicant's "
                "Roblox User ID. Check their Roblox profile answer.",
                ephemeral=True
            )
            return

        try:
            success, roblox_message = (
                accept_roblox_join_request(
                    roblox_id
                )
            )

        except Exception as error:
            await interaction.followup.send(
                f"❌ Roblox API error:\n`{error}`",
                ephemeral=True
            )
            return

        if not success:
            await interaction.followup.send(
                f"❌ Could not accept the Roblox group request.\n"
                f"{roblox_message}",
                ephemeral=True
            )
            return

        member = interaction.guild.get_member(
            self.applicant_id
        )

        if not member:
            try:
                member = await interaction.guild.fetch_member(
                    self.applicant_id
                )
            except Exception:
                member = None

        resident_role = interaction.guild.get_role(
            RESIDENT_ROLE_ID
        )

        if not resident_role:
            await interaction.followup.send(
                "⚠️ Roblox was accepted, but I couldn't find "
                "the configured Resident Discord role.",
                ephemeral=True
            )
            return

        if not member:
            await interaction.followup.send(
                "⚠️ Roblox was accepted, but the applicant "
                "couldn't be found in this Discord server.",
                ephemeral=True
            )
            return

        try:
            await member.add_roles(
                resident_role,
                reason=(
                    "Ensford whitelist application accepted "
                    f"by {interaction.user}"
                )
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "⚠️ Roblox was accepted, but I could not add "
                "the Resident role. Move the bot's role above "
                "Resident and give it Manage Roles.",
                ephemeral=True
            )
            return

        note = self.note.value.strip()

        save_review(
            self.applicant_id,
            "accepted",
            interaction.user.id,
            note
        )

        applicant = await get_user(
            self.bot,
            self.applicant_id
        )

        accepted_embed = discord.Embed(
            title="✅ Welcome to Ensford!",
            description=(
                "Your whitelist application has been "
                "**accepted**."
            ),
            color=discord.Color.green()
        )

        accepted_embed.add_field(
            name="Roblox Group",
            value=(
                "Your pending request to the main Ensford "
                "group has been accepted."
            ),
            inline=False
        )

        accepted_embed.add_field(
            name="Discord",
            value=(
                "You have been given the **Resident** role."
            ),
            inline=False
        )

        if note:
            accepted_embed.add_field(
                name="Staff Message",
                value=note,
                inline=False
            )

        try:
            await applicant.send(
                embed=accepted_embed
            )
        except Exception:
            pass

        old_embed = (
            self.review_message.embeds[-1]
            if self.review_message.embeds
            else discord.Embed()
        )

        old_embed.color = discord.Color.green()

        old_embed.add_field(
            name="✅ Decision",
            value=(
                f"Accepted by {interaction.user.mention}\n"
                f"Roblox User ID: `{roblox_id}`\n"
                f"Resident role added: {resident_role.mention}"
            ),
            inline=False
        )

        await self.review_message.edit(
            embed=old_embed,
            view=None
        )

        await interaction.followup.send(
            "✅ Application accepted. Roblox group request "
            "accepted and Resident role added.",
            ephemeral=True
        )


# --------------------------------------------------
# Staff review buttons
# --------------------------------------------------

class ReviewView(discord.ui.View):

    def __init__(self, bot):
        super().__init__(
            timeout=None
        )

        self.bot = bot

    @discord.ui.button(
        label="Accept",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="ensford_whitelist_accept"
    )
    async def accept_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not staff_allowed(interaction):
            await interaction.response.send_message(
                "You do not have permission to review applications.",
                ephemeral=True
            )
            return

        applicant_id = get_applicant_id_from_message(
            interaction.message
        )

        if not applicant_id:
            await interaction.response.send_message(
                "Could not determine the applicant.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            AcceptModal(
                self.bot,
                applicant_id,
                interaction.message
            )
        )

    @discord.ui.button(
        label="Deny",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="ensford_whitelist_deny"
    )
    async def deny_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not staff_allowed(interaction):
            await interaction.response.send_message(
                "You do not have permission to review applications.",
                ephemeral=True
            )
            return

        applicant_id = get_applicant_id_from_message(
            interaction.message
        )

        if not applicant_id:
            await interaction.response.send_message(
                "Could not determine the applicant.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            DenyModal(
                self.bot,
                applicant_id,
                interaction.message
            )
        )

    @discord.ui.button(
        label="Request Changes",
        style=discord.ButtonStyle.secondary,
        emoji="📝",
        custom_id="ensford_whitelist_changes"
    )
    async def changes_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not staff_allowed(interaction):
            await interaction.response.send_message(
                "You do not have permission to review applications.",
                ephemeral=True
            )
            return

        applicant_id = get_applicant_id_from_message(
            interaction.message
        )

        if not applicant_id:
            await interaction.response.send_message(
                "Could not determine the applicant.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            RequestChangesModal(
                self.bot,
                applicant_id,
                interaction.message
            )
        )


# --------------------------------------------------
# Application confirmation
# --------------------------------------------------

class ConfirmApplicationView(discord.ui.View):

    def __init__(self, bot):
        super().__init__(
            timeout=300
        )

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
            (
                str(interaction.user.id),
            )
        )

        if existing:

            started_at, current_question, status = existing

            if (
                status == "active"
                and not expired(started_at)
            ):
                await interaction.response.send_message(
                    "You already have an active application.",
                    ephemeral=True
                )
                return

            execute(
                """
                DELETE FROM whitelist_applications
                WHERE discord_id=?
                """,
                (
                    str(interaction.user.id),
                )
            )

            execute(
                """
                DELETE FROM whitelist_answers
                WHERE discord_id=?
                """,
                (
                    str(interaction.user.id),
                )
            )

        now = int(time.time())

        execute(
            """
            INSERT INTO whitelist_applications
            (
                discord_id,
                started_at,
                current_question,
                status
            )
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
                "I will now begin asking you questions.\n\n"
                "You have **3 hours** to complete the application.\n"
                "Type `cancel` at any time to cancel."
            ),
            embed=None,
            view=None
        )

        asyncio.create_task(
            ask_questions(
                self.bot,
                interaction.user
            )
        )

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


# --------------------------------------------------
# Public panel
# --------------------------------------------------

class ApplicationPanelView(discord.ui.View):

    def __init__(self, bot):
        super().__init__(
            timeout=None
        )

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

            dm = (
                interaction.user.dm_channel
                or await interaction.user.create_dm()
            )

            embed = discord.Embed(
                title="Ensford Whitelist Application",
                description=(
                    "**Are you sure you want to apply?**\n\n"
                    "Once you start the application, I will "
                    "send you a series of questions.\n\n"
                    "You will have **3 hours** to complete the "
                    "application. If you do not complete it in "
                    "time, you will have to restart.\n\n"
                    "You may cancel at any time."
                ),
                color=discord.Color.blue()
            )

            embed.set_footer(
                text="Ensford • Whitelist Application"
            )

            await dm.send(
                embed=embed,
                view=ConfirmApplicationView(
                    self.bot
                )
            )

            await interaction.response.send_message(
                "📨 Check your DMs.",
                ephemeral=True
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "I couldn't DM you. Enable server DMs "
                "and try again.",
                ephemeral=True
            )


# --------------------------------------------------
# Question system
# --------------------------------------------------

async def ask_questions(
    bot,
    user
):
    discord_id = str(
        user.id
    )

    application = query_one(
        """
        SELECT started_at, current_question
        FROM whitelist_applications
        WHERE discord_id=?
        AND status='active'
        """,
        (
            discord_id,
        )
    )

    if not application:
        return

    started_at, current_question = application

    dm = (
        user.dm_channel
        or await user.create_dm()
    )

    for index in range(
        current_question,
        len(QUESTIONS)
    ):

        if expired(started_at):

            execute(
                """
                UPDATE whitelist_applications
                SET status='expired'
                WHERE discord_id=?
                """,
                (
                    discord_id,
                )
            )

            await dm.send(
                "⏰ Your 3-hour application window expired."
            )

            return

        question = QUESTIONS[index]

        embed = discord.Embed(
            title=(
                f"Question {index + 1} "
                f"of {len(QUESTIONS)}"
            ),
            description=question,
            color=discord.Color.blurple()
        )

        remaining = (
            APPLICATION_TIMEOUT
            - (
                int(time.time())
                - int(started_at)
            )
        )

        embed.set_footer(
            text=(
                f"Approximately "
                f"{remaining // 60} minutes remaining"
            )
        )

        await dm.send(
            embed=embed
        )

        def check(message):
            return (
                message.author.id == user.id
                and isinstance(
                    message.channel,
                    discord.DMChannel
                )
            )

        try:

            message = await bot.wait_for(
                "message",
                timeout=remaining,
                check=check
            )

        except asyncio.TimeoutError:

            execute(
                """
                UPDATE whitelist_applications
                SET status='expired'
                WHERE discord_id=?
                """,
                (
                    discord_id,
                )
            )

            await dm.send(
                "⏰ Your application expired."
            )

            return

        if (
            message.content.strip().lower()
            == "cancel"
        ):

            execute(
                """
                UPDATE whitelist_applications
                SET status='cancelled'
                WHERE discord_id=?
                """,
                (
                    discord_id,
                )
            )

            await dm.send(
                "❌ Your application was cancelled."
            )

            return

        execute(
            """
            INSERT OR REPLACE INTO whitelist_answers
            (
                discord_id,
                question_number,
                question,
                answer
            )
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

    await submit_application(
        bot,
        user
    )


# --------------------------------------------------
# Submit to staff
# --------------------------------------------------

async def submit_application(
    bot,
    user
):
    discord_id = str(
        user.id
    )

    execute(
        """
        UPDATE whitelist_applications
        SET status='submitted'
        WHERE discord_id=?
        """,
        (
            discord_id,
        )
    )

    review_channel = bot.get_channel(
        APPLICATION_REVIEW_CHANNEL_ID
    )

    if not review_channel:

        review_channel = await bot.fetch_channel(
            APPLICATION_REVIEW_CHANNEL_ID
        )

    main_embed = discord.Embed(
        title="📋 New Ensford Whitelist Application",
        description=(
            f"**Applicant:** {user.mention}\n"
            f"**Discord:** `{user}`\n"
            f"**Discord ID:** `{user.id}`"
        ),
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow()
    )

    main_embed.set_thumbnail(
        url=user.display_avatar.url
    )

    # Discord embeds have overall limits,
    # so split the application into pages.
    page_embeds = []

    for page_start in range(
        0,
        len(QUESTIONS),
        4
    ):

        page = discord.Embed(
            color=discord.Color.gold()
        )

        for index in range(
            page_start,
            min(
                page_start + 4,
                len(QUESTIONS)
            )
        ):

            answer = (
                get_answer(
                    discord_id,
                    index
                )
                or "No response"
            )

            page.add_field(
                name=(
                    f"{index + 1}. "
                    f"{QUESTIONS[index][:180]}"
                ),
                value=answer[:900],
                inline=False
            )

        page_embeds.append(
            page
        )

    await review_channel.send(
        embed=main_embed
    )

    for page in page_embeds[:-1]:
        await review_channel.send(
            embed=page
        )

    final_embed = page_embeds[-1]

    final_embed.set_footer(
        text=(
            f"Applicant ID: {user.id}"
        )
    )

    await review_channel.send(
        embed=final_embed,
        view=ReviewView(bot)
    )

    finished = discord.Embed(
        title="✅ Application Submitted",
        description=(
            "Your Ensford whitelist application "
            "has been submitted successfully.\n\n"
            "Staff will review it and contact you "
            "with a decision."
        ),
        color=discord.Color.green()
    )

    await user.send(
        embed=finished
    )


# --------------------------------------------------
# Cog
# --------------------------------------------------

class Whitelist(commands.Cog):

    def __init__(
        self,
        bot
    ):
        self.bot = bot

    async def cog_load(self):
        # Persistent buttons survive Render restarts.
        self.bot.add_view(
            ApplicationPanelView(
                self.bot
            )
        )

        self.bot.add_view(
            ReviewView(
                self.bot
            )
        )

    @app_commands.command(
        name="whitelistpanel",
        description=(
            "Post the Ensford whitelist application panel."
        )
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def whitelistpanel(
        self,
        interaction: discord.Interaction
    ):

        embed = discord.Embed(
            title="Ensford Whitelist Applications",
            description=(
               "Interested in becoming a whitelisted member of Ensford?\n\n"



            "Press Start Application below to begin.\n\n"



"The application will take place in your DMs.\n"



"You will have 3 hours to complete it.\n"



"To join our community, you must fill out the Whitelist Application provided below and be approved by an Administrator before you can attend server startups. It is recommended that you review the Community Guidelines below to understand what you are getting into. You will be tested on specific rules in the Whitelist Application. Ensford is a 16+ voice chat community\n"
            ),
            color=discord.Color.blue()
        )

        embed.set_footer(
            text="Ensford • Whitelist Applications"
        )

        await interaction.channel.send(
            embed=embed,
            view=ApplicationPanelView(
                self.bot
            )
        )

        await interaction.response.send_message(
            "✅ Whitelist panel posted.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(
        Whitelist(bot)
    )