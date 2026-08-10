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


# ============================================================
# DATABASE / BASIC HELPERS
# ============================================================

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


def save_review(discord_id, status, reviewer_id, reason=""):
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


def save_review_message(message_id, applicant_discord_id):
    execute(
        """
        INSERT OR REPLACE INTO whitelist_review_messages
        (
            message_id,
            applicant_discord_id,
            created_at
        )
        VALUES (?, ?, ?)
        """,
        (
            str(message_id),
            str(applicant_discord_id),
            int(time.time())
        )
    )


def delete_review_message(message_id):
    execute(
        """
        DELETE FROM whitelist_review_messages
        WHERE message_id=?
        """,
        (str(message_id),)
    )


def get_applicant_id_from_message(message):
    # Primary lookup: persistent SQLite mapping.
    row = query_one(
        """
        SELECT applicant_discord_id
        FROM whitelist_review_messages
        WHERE message_id=?
        """,
        (str(message.id),)
    )

    if row:
        return int(row[0])

    # Fallback for older messages created before the mapping existed.
    for embed in reversed(message.embeds):
        footer = embed.footer.text or ""

        match = re.search(
            r"Applicant ID:\s*(\d+)",
            footer
        )

        if match:
            applicant_id = int(match.group(1))
            save_review_message(message.id, applicant_id)
            return applicant_id

    return None


async def get_user(bot, discord_id):
    user = bot.get_user(int(discord_id))

    if user:
        return user

    return await bot.fetch_user(int(discord_id))


def staff_allowed(interaction):
    if not isinstance(interaction.user, discord.Member):
        return False

    return (
        interaction.user.guild_permissions.administrator
        or interaction.user.guild_permissions.manage_roles
    )


# ============================================================
# ROBLOX HELPERS
# ============================================================

def get_roblox_user_id(discord_id):
    # First try the profile URL from question 2.
    profile = get_answer(discord_id, 1)

    if profile:
        match = re.search(
            r"roblox\.com/users/(\d+)",
            profile,
            re.IGNORECASE
        )

        if match:
            return int(match.group(1))

    # Fallback to the exact username from question 1.
    username = get_answer(discord_id, 0)

    if not username:
        return None

    username = username.strip()

    try:
        roblox_id = fetch_roblox_id(username)

        if roblox_id:
            return int(roblox_id)

    except Exception as error:
        print(
            f"Failed to resolve Roblox user '{username}': {error}"
        )

    return None


def roblox_headers():
    if not ROBLOX_OPEN_CLOUD_KEY:
        raise RuntimeError(
            "ROBLOX_OPEN_CLOUD_KEY is not configured."
        )

    return {
        "x-api-key": ROBLOX_OPEN_CLOUD_KEY,
        "Content-Type": "application/json"
    }


def _extract_join_requests(data):
    """
    Roblox's response shape may change while this endpoint is beta.
    Find likely request objects without hardcoding only one wrapper name.
    """
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in (
        "groupJoinRequests",
        "joinRequests",
        "group_join_requests",
        "join_requests",
        "data",
    ):
        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


def _find_user_id_in_request(item):
    if not isinstance(item, dict):
        return None

    # Common direct fields.
    for key in (
        "userId",
        "user_id",
        "requesterUserId",
        "requester_user_id",
    ):
        value = item.get(key)

        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass

    # Nested user/requester objects.
    for key in ("user", "requester"):
        value = item.get(key)

        if isinstance(value, dict):
            for id_key in ("id", "userId", "user_id"):
                nested = value.get(id_key)

                if nested is not None:
                    try:
                        return int(nested)
                    except (TypeError, ValueError):
                        pass

        if isinstance(value, str):
            match = re.search(r"/users/(\d+)", value)

            if match:
                return int(match.group(1))

    # Search resource-name strings.
    for key in ("name", "path"):
        value = item.get(key)

        if isinstance(value, str):
            match = re.search(r"/users/(\d+)", value)

            if match:
                return int(match.group(1))

    return None


def _extract_join_request_id(item):
    if not isinstance(item, dict):
        return None

    for key in (
        "joinRequestId",
        "join_request_id",
        "id",
    ):
        value = item.get(key)

        if value is not None:
            return str(value)

    for key in ("name", "path"):
        value = item.get(key)

        if isinstance(value, str):
            match = re.search(
                r"join-requests/([^/:]+)",
                value
            )

            if match:
                return match.group(1)

    return None


def get_join_request_id(roblox_id):
    """
    Lists pending requests and matches the applicant by Roblox user ID.
    """
    url = (
        f"https://apis.roblox.com/cloud/v2/groups/"
        f"{ROBLOX_GROUP_ID}/join-requests"
    )

    response = requests.get(
        url,
        headers=roblox_headers(),
        timeout=15
    )

    if not response.ok:
        raise RuntimeError(
            f"Roblox API returned {response.status_code}: "
            f"{response.text[:500]}"
        )

    data = response.json()

    print("ROBLOX JOIN REQUEST RESPONSE:")
    print(data)

    requests_list = _extract_join_requests(data)

    for item in requests_list:
        item_user_id = _find_user_id_in_request(item)

        if item_user_id == int(roblox_id):
            request_id = _extract_join_request_id(item)

            if request_id:
                return request_id

    return None


def accept_roblox_join_request(roblox_id):
    join_request_id = get_join_request_id(roblox_id)

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

    if response.status_code in (200, 201, 204):
        return True, "Roblox group request accepted."

    return False, (
        f"Roblox returned HTTP {response.status_code}: "
        f"{response.text[:500]}"
    )


def decline_roblox_join_request(roblox_id):
    join_request_id = get_join_request_id(roblox_id)

    if not join_request_id:
        return True, "No pending Roblox group request existed."

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

    if response.status_code in (200, 201, 204):
        return True, "Roblox group request declined."

    return False, (
        f"Roblox returned HTTP {response.status_code}: "
        f"{response.text[:500]}"
    )


# ============================================================
# REQUEST CHANGES
# ============================================================

class RequestChangesModal(
    discord.ui.Modal,
    title="Request Application Changes"
):
    request_text = discord.ui.TextInput(
        label="What should the applicant change?",
        placeholder=(
            "Example: Please provide more detail about "
            "your character's background."
        ),
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1500
    )

    def __init__(self, bot, applicant_id, review_message):
        super().__init__()

        self.bot = bot
        self.applicant_id = applicant_id
        self.review_message = review_message

    async def on_submit(self, interaction: discord.Interaction):
        question = self.request_text.value.strip()

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

        save_review(
            self.applicant_id,
            "changes_required",
            interaction.user.id,
            question
        )

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

    new_review_message = await review_channel.send(
        embed=embed,
        view=ReviewView(bot)
    )

    save_review_message(
        new_review_message.id,
        applicant.id
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


# ============================================================
# DENY MODAL
# ============================================================

class DenyModal(
    discord.ui.Modal,
    title="Deny Whitelist Application"
):
    reason = discord.ui.TextInput(
        label="Reason for denial",
        placeholder="Explain why the application is being denied.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1500
    )

    def __init__(self, bot, applicant_id, review_message):
        super().__init__()

        self.bot = bot
        self.applicant_id = applicant_id
        self.review_message = review_message

    async def on_submit(self, interaction: discord.Interaction):
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
                _, roblox_message = decline_roblox_join_request(
                    roblox_id
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

        delete_review_message(
            self.review_message.id
        )

        await interaction.followup.send(
            "Application denied.",
            ephemeral=True
        )


# ============================================================
# ACCEPT MODAL
# ============================================================

class AcceptModal(
    discord.ui.Modal,
    title="Accept Whitelist Application"
):
    note = discord.ui.TextInput(
        label="Acceptance note",
        placeholder="Optional message for the applicant.",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    def __init__(self, bot, applicant_id, review_message):
        super().__init__()

        self.bot = bot
        self.applicant_id = applicant_id
        self.review_message = review_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(
            ephemeral=True
        )

        roblox_id = get_roblox_user_id(
            self.applicant_id
        )

        if not roblox_id:
            await interaction.followup.send(
                "❌ I couldn't determine the applicant's Roblox "
                "User ID. Check their Roblox username/profile answer.",
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
                "❌ Could not accept the Roblox group request.\n"
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

        delete_review_message(
            self.review_message.id
        )

        await interaction.followup.send(
            "✅ Application accepted. Roblox group request "
            "accepted and Resident role added.",
            ephemeral=True
        )


# ============================================================
# STAFF REVIEW BUTTONS
# ============================================================

class ReviewView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
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


# ============================================================
# APPLICATION CONFIRMATION
# ============================================================

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


# ============================================================
# PUBLIC APPLICATION PANEL
# ============================================================

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
                    "If you wish to stop the application, "
                    "you may cancel at any time."
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


# ============================================================
# QUESTION SYSTEM
# ============================================================

async def ask_questions(bot, user):
    discord_id = str(user.id)

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

        if message.content.strip().lower() == "cancel":
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


# ============================================================
# SUBMIT APPLICATION TO STAFF
# ============================================================

async def submit_application(bot, user):
    discord_id = str(user.id)

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

    await review_channel.send(
        embed=main_embed
    )

    # Split answers across multiple embeds to stay within Discord limits.
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

        page_embeds.append(page)

    for page in page_embeds[:-1]:
        await review_channel.send(
            embed=page
        )

    final_embed = page_embeds[-1]

    final_embed.set_footer(
        text=f"Applicant ID: {user.id}"
    )

    new_review_message = await review_channel.send(
        embed=final_embed,
        view=ReviewView(bot)
    )

    save_review_message(
        new_review_message.id,
        user.id
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


# ============================================================
# COG
# ============================================================

class Whitelist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # Persistent public panel buttons.
        self.bot.add_view(
            ApplicationPanelView(
                self.bot
            )
        )

        # Persistent review buttons.
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
                "Press **Start Application** below to begin.\n\n"
                "The application will take place in your DMs.\n"
                "You will have **3 hours** to complete it.\n\n"
                "To join our community, you must fill out the "
                "Whitelist Application and be approved by an "
                "Administrator before attending server startups.\n\n"
                "Ensford is a **16+ voice chat community**. "
                "It is recommended that you review the Community "
                "Guidelines before applying."
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
