from flask import Blueprint, request, jsonify, render_template_string
import os

monitor_bp = Blueprint("monitor", __name__)

live_players = []

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Live Server Monitor</title>

<style>
body { background:#121212; color:white; font-family:Arial; padding:30px; }
.card { background:#1e1e1e; padding:10px; margin:10px 0; border-radius:10px; display:flex; align-items:center; }
img { border-radius:50%; margin-right:15px; }
</style>

</head>
<body>

<h1>Live Roblox Server</h1>
<h2 id="count"></h2>

<div id="players"></div>

<script>

async function load(){
    const res = await fetch("/players");
    const data = await res.json();

    document.getElementById("count").innerText =
        "Players Online: " + data.players.length;

    let html = "";

    data.players.forEach(p => {
        html += `
        <div class="card">
            <img src="https://www.roblox.com/headshot-thumbnail/image?userId=${p.userId}&width=100&height=100&format=png">
            <div>
                <b>${p.name}</b><br>
                💰 Bank: $${p.bank}
            </div>
        </div>
        `;
    });

    document.getElementById("players").innerHTML = html;
}

load();
setInterval(load, 3000);

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

@monitor_bp.route("/server/update", methods=["POST"])
def update():
    global live_players

    if request.headers.get("X-API-Key") != os.getenv("API_KEY"):
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "no data"}), 400

    live_players = data.get("players", [])

    return jsonify({"success": True})