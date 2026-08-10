import os
import time
import requests
import asyncio

from flask import Blueprint, request

from database import query_one, execute
from role_sync import sync_group_role


oauth_bp = Blueprint(
    "roblox_oauth",
    __name__
)


ROBLOX_OAUTH_CLIENT_ID = os.getenv(
    "ROBLOX_OAUTH_CLIENT_ID"
)

ROBLOX_OAUTH_CLIENT_SECRET = os.getenv(
    "ROBLOX_OAUTH_CLIENT_SECRET"
)

ROBLOX_OAUTH_REDIRECT_URI = os.getenv(
    "ROBLOX_OAUTH_REDIRECT_URI"
)


def success_page(username):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ensford Verification</title>
        <style>
            body {{
                background: #111318;
                color: white;
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }}

            .box {{
                background: #1c1f26;
                padding: 40px;
                border-radius: 14px;
                text-align: center;
                max-width: 500px;
            }}

            h1 {{
                color: #57f287;
            }}
        </style>
    </head>

    <body>
        <div class="box">
            <h1>✓ Verification Complete</h1>

            <p>
                Roblox account
                <strong>{username}</strong>
                has been successfully linked to your Discord account.
            </p>

            <p>You may now close this page.</p>
        </div>
    </body>
    </html>
    """


def error_page(message):
    return f"""
    <!DOCTYPE html>
    <html>
    <body style="
        background:#111318;
        color:white;
        font-family:Arial;
        text-align:center;
        padding-top:100px;
    ">

        <h1>Verification Failed</h1>

        <p>{message}</p>

    </body>
    </html>
    """, 400


@oauth_bp.route(
    "/oauth/roblox/callback"
)
def roblox_callback():

    code = request.args.get(
        "code"
    )

    state = request.args.get(
        "state"
    )

    error = request.args.get(
        "error"
    )

    if error:
        return error_page(
            "Roblox authorization was cancelled."
        )

    if not code or not state:
        return error_page(
            "Missing authorization information."
        )

    state_row = query_one(
        """
        SELECT discord_id, expires_at
        FROM oauth_states
        WHERE state=?
        """,
        (
            state,
        )
    )

    if not state_row:
        return error_page(
            "Invalid or expired verification request."
        )

    discord_id, expires_at = state_row

    if int(time.time()) > int(expires_at):

        execute(
            """
            DELETE FROM oauth_states
            WHERE state=?
            """,
            (
                state,
            )
        )

        return error_page(
            "This verification link has expired."
        )

    token_response = requests.post(
        "https://apis.roblox.com/oauth/v1/token",
        data={
            "client_id": ROBLOX_OAUTH_CLIENT_ID,
            "client_secret": ROBLOX_OAUTH_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code
        },
        headers={
            "Content-Type":
            "application/x-www-form-urlencoded"
        },
        timeout=15
    )

    if not token_response.ok:
        return error_page(
            (
                "Roblox token exchange failed: "
                f"{token_response.status_code}"
            )
        )

    tokens = token_response.json()

    access_token = tokens.get(
        "access_token"
    )

    if not access_token:
        return error_page(
            "Roblox did not return an access token."
        )

    user_response = requests.get(
        "https://apis.roblox.com/oauth/v1/userinfo",
        headers={
            "Authorization":
            f"Bearer {access_token}"
        },
        timeout=15
    )

    if not user_response.ok:
        return error_page(
            "Could not retrieve Roblox account information."
        )

    roblox_user = user_response.json()

    roblox_id = str(
        roblox_user["sub"]
    )

    roblox_name = (
        roblox_user.get(
            "preferred_username"
        )
        or roblox_user.get(
            "nickname"
        )
        or roblox_user.get(
            "name"
        )
        or "Unknown"
    )

    existing_roblox = query_one(
        """
        SELECT discord_id
        FROM verify
        WHERE roblox_id=?
        """,
        (
            roblox_id,
        )
    )

    if (
        existing_roblox
        and str(existing_roblox[0])
        != str(discord_id)
    ):
        return error_page(
            "That Roblox account is already linked "
            "to another Discord account."
        )

    # Remove any previous link for this Discord account.
    execute(
        """
        DELETE FROM verify
        WHERE discord_id=?
        """,
        (
            str(discord_id),
        )
    )

    execute(
        """
        INSERT INTO verify
        (
            roblox_name,
            roblox_id,
            discord_name,
            discord_id
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            roblox_name,
            roblox_id,
            "",
            str(discord_id)
        )
    )

    try:
        from bot import bot

        guild_id = int(
            os.getenv("GUILD_ID", "778045351260455022")
        )

        async def sync_after_verify():
            guild = bot.get_guild(
                guild_id
            )

            if not guild:
                return

            member = guild.get_member(
                int(discord_id)
            )

            if not member:
                try:
                    member = await guild.fetch_member(
                        int(discord_id)
                    )
                except Exception:
                    return

            await sync_group_role(
                member,
                roblox_id
            )

        asyncio.run_coroutine_threadsafe(
            sync_after_verify(),
            bot.loop
        )

    except Exception as error:
        print(
            "Role sync after verification failed:",
            error
        )

    execute(
        """
        DELETE FROM oauth_states
        WHERE state=?
        """,
        (
            state,
        )
    )

    return success_page(
        roblox_name
    )