from flask import Blueprint, request, jsonify, render_template_string
import os
import time
import asyncio

monitor_bp = Blueprint("monitor", __name__)

live_players = []
last_update = 0
server_start = time.time()
max_players = 0
server_active = False


HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Server Monitor</title>

<style>
body { background:#0f0f0f; color:white; font-family:Arial; padding:30px; }
.card { background:#1c1c1c; padding:10px; margin:10px 0; border-radius:10px; display:flex; align-items:center; }
img { border-radius:50%; margin-right:10px; }
</style>

</head>

<body>

<h1>🎮 Live Server</h1>
<h2 id="status">Loading...</h2>
<h3 id="count"></h3>

<div id="players"></div>

<script>

async function load(){

    const r = await fetch("/players");
    const d = await r.json();

    document.getElementById("count").innerText =
        "Players: " + d.players.length;

    let html = "";

    d.players.forEach(p => {
        html += `
        <div class="card">
            <img src="https://www.roblox.com/headshot-thumbnail/image?userId=${p.userId}&width=100&height=100&format=png">
            <div>
                <b>${p.name}</b><br>
                💰 $${p.bank}
            </div>
        </div>`;
    });

    document.getElementById("players").innerHTML = html;
}

async function status(){

    const r = await fetch("/status");
    const d = await r.json();

    document.getElementById("status").innerText =
        d.online ? "🟢 Online" : "🔴 Offline";
}

load();
status();

setInterval(load, 3000);
setInterval(status, 5000);

</script>

</body>
</html>
"""


@monitor_bp.route("/monitor")
def monitor():
    return render_template_string(HTML)


@monitor_bp.route("/players")
def players():
    return jsonify({"players": live_players})


@monitor_bp.route("/status")
def status():
    online = (time.time() - last_update) < 15
    return jsonify({
        "online": online,
        "players": len(live_players)
    })


@monitor_bp.route("/server/update", methods=["POST"])
def update():

    global live_players, last_update, server_start, max_players, server_active

    if request.headers.get("X-API-Key") != os.getenv("API_KEY"):
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "no data"}), 400

    players = data.get("players", [])
    live_players = players

    now = time.time()

    if not server_active:
        server_start = now
        server_active = True

    last_update = now

    if len(players) > max_players:
        max_players = len(players)

    return jsonify({"success": True})


def check_server_end(bot):

    global server_active, last_update, server_start, max_players

    now = time.time()

    if server_active and now - last_update > 20:

        duration = int(now - server_start)

        msg = (
            "📡 Server Ended\n"
            f"⏱ Time: {duration}s\n"
            f"👥 Peak Players: {max_players}"
        )

        channel_id = int(os.getenv("LOG_CHANNEL_ID"))

        channel = bot.get_channel(channel_id)
        if channel:
            asyncio.run_coroutine_threadsafe(channel.send(msg), bot.loop)

        server_active = False
        max_players = 0