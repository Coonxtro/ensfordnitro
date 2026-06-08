from flask import Blueprint, request, jsonify
import asyncio

from database import query_one, execute

assign_role_bp = Blueprint("assign_role", __name__)


@assign_role_bp.route("/assign-role/<int:guild_id>", methods=["POST"])
def assign_role(guild_id):
    data = request.get_json(silent=True)

    if not data or not data.get("robloxId") or not data.get("achievement"):
        return jsonify(error="Invalid payload"), 400

    rid = str(data["robloxId"])
    ach = data["achievement"].strip()

    async def task():
        from bot import bot

        row = query_one(
            """
            SELECT v.discord_id, r.role_id
            FROM verify v
            JOIN role_mappings r
              ON r.guild_id = ?
             AND r.achievement = ?
            WHERE v.roblox_id = ?
            """,
            (str(guild_id), ach, rid)
        )

        if not row:
            return {"error": "No mapping or link found"}

        did, role_id = row

        guild = bot.get_guild(guild_id) or await bot.fetch_guild(guild_id)
        member = guild.get_member(int(did)) or await guild.fetch_member(int(did))
        role = guild.get_role(int(role_id))

        if not member or not role:
            return {"error": "Member or role not found"}

        await member.add_roles(role)

        return {"status": "Role assigned successfully"}

    from bot import bot

    result = asyncio.run_coroutine_threadsafe(
        task(),
        bot.loop
    ).result(timeout=10)

    code = 200 if result.get("status") else 400

    return jsonify(result), code


@assign_role_bp.route("/reward/<int:roblox_id>", methods=["GET"])
def get_reward(roblox_id):

    row = query_one(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM pending_rewards
        WHERE roblox_id = ?
        AND delivered = 0
        """,
        (str(roblox_id),)
    )

    amount = row[0] if row else 0

    if amount > 0:
        execute(
            """
            UPDATE pending_rewards
            SET delivered = 1
            WHERE roblox_id = ?
            AND delivered = 0
            """,
            (str(roblox_id),)
        )

    return jsonify({
        "amount": amount
    })