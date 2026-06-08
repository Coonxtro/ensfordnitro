from flask import Blueprint, request, jsonify
import asyncio
import os

from database import query_one, execute

@assign_role_bp.route("/reward/<int:roblox_id>", methods=["GET"])
def reward(roblox_id):

    key = request.args.get("key")
    if key != os.getenv("API_KEY"):
        return jsonify({"error": "unauthorized"}), 401

    row = query_one(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM pending_rewards
        WHERE roblox_id=? AND delivered=0
        """,
        (str(roblox_id),)
    )

    amount = row[0] if row else 0

    if amount > 0:
        execute(
            """
            UPDATE pending_rewards
            SET delivered=1
            WHERE roblox_id=? AND delivered=0
            """,
            (str(roblox_id),)
        )

    return jsonify({"amount": amount})
