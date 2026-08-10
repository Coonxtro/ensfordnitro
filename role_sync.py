import os
import requests
import discord


ROBLOX_GROUP_ID = int(
    os.getenv("ROBLOX_GROUP_ID", "5642568")
)


def get_roblox_group_role(roblox_id):
    url = (
        f"https://groups.roblox.com/v2/users/"
        f"{roblox_id}/groups/roles"
    )

    response = requests.get(
        url,
        timeout=10
    )

    if not response.ok:
        raise RuntimeError(
            f"Roblox role lookup failed "
            f"{response.status_code}: "
            f"{response.text[:500]}"
        )

    data = response.json()

    for membership in data.get("data", []):
        group = membership.get("group", {})
        role = membership.get("role", {})

        if int(group.get("id", 0)) == ROBLOX_GROUP_ID:
            return {
                "group_name": group.get("name"),
                "role_id": role.get("id"),
                "role_name": role.get("name"),
                "rank": role.get("rank")
            }

    return None


async def sync_group_role(member, roblox_id):
    group_role = get_roblox_group_role(
        roblox_id
    )

    if not group_role:
        return {
            "success": False,
            "message": "You are not currently in the Ensford Roblox group.",
            "added": [],
            "removed": [],
            "current": None
        }

    roblox_role_name = group_role["role_name"]

    discord_role = discord.utils.get(
        member.guild.roles,
        name=roblox_role_name
    )

    if not discord_role:
        return {
            "success": False,
            "message": (
                f'Your Roblox role is "{roblox_role_name}", '
                "but there is no matching Discord role."
            ),
            "added": [],
            "removed": [],
            "current": roblox_role_name
        }

    added = []
    removed = []

    #
    # Roles controlled by Roblox syncing
    #
    # Add ALL Roblox group rank names here.
    #
    MANAGED_ROLE_NAMES = [
        "Resident",
        "Trusted Member",

        "Upper Class Resident",
        "Administrator",
        "Developer",
        "Community Oversight"
    ]

    # Remove outdated Roblox-managed roles
    for role in member.roles:

        if (
            role.name in MANAGED_ROLE_NAMES
            and role.name != roblox_role_name
        ):
            try:
                await member.remove_roles(
                    role,
                    reason="Ensford Roblox role synchronization"
                )

                removed.append(
                    role.name
                )

            except discord.Forbidden:
                pass

    # Add current Roblox role
    if discord_role not in member.roles:

        await member.add_roles(
            discord_role,
            reason="Ensford Roblox role synchronization"
        )

        added.append(
            discord_role.name
        )

    return {
        "success": True,
        "message": "Roles synchronized.",
        "current": roblox_role_name,
        "added": added,
        "removed": removed
    }

def build_role_sync_embed(
    roblox_name,
    result,
    title="Roles Updated"
):

    if not result["success"]:

        embed = discord.Embed(
            title="⚠️ Role Update",
            description=result["message"],
            color=discord.Color.orange()
        )

        return embed

    added = result.get(
        "added",
        []
    )

    removed = result.get(
        "removed",
        []
    )

    current = result.get(
        "current",
        "Unknown"
    )

    embed = discord.Embed(
        title=f"✅ {title}",
        description=(
            f"Your Discord roles have been synchronized "
            f"with **{roblox_name}**."
        ),
        color=discord.Color.green()
    )

    embed.add_field(
        name="Roblox Group Role",
        value=f"**{current}**",
        inline=False
    )

    if added:
        embed.add_field(
            name="➕ Added",
            value="\n".join(
                f"• {role}"
                for role in added
            ),
            inline=True
        )

    if removed:
        embed.add_field(
            name="➖ Removed",
            value="\n".join(
                f"• {role}"
                for role in removed
            ),
            inline=True
        )

    if not added and not removed:
        embed.add_field(
            name="No Changes",
            value=(
                "Your Discord roles were already up to date."
            ),
            inline=False
        )

    embed.set_footer(
        text="Ensford • Roblox Role Synchronization"
    )

    return embed