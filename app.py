
import os
import re
import hmac
import time
from collections import deque
from flask import Flask, jsonify, render_template_string, request
from flask_socketio import SocketIO, join_room

app = Flask(__name__)

TOKEN = os.environ.get("CONTROL_TOKEN", "")
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "").split(",")

socketio = SocketIO(
    app,
    cors_allowed_origins=ALLOWED_ORIGINS,
    async_mode="threading"
)

ADMIN_SIDS = set()
VISITORS = {}
ACTIVITY = deque(maxlen=200)

def log_event(event):
    event["time"] = time.strftime("%H:%M:%S")
    ACTIVITY.appendleft(event)
    socketio.emit("activity", event, to="admins")

def visitor_count():
    return len(VISITORS)

@app.route("/")
def home():
    return "Python Website Controller Online"

@app.route("/health")
def health():
    return jsonify({"status": "online"})

@app.route("/admin")
def admin():
    return render_template_string(DASHBOARD)

@socketio.on("connect")
def connected(auth=None):
    pass

@socketio.on("admin_auth")
def admin_auth(data):
    token = str((data or {}).get("token", ""))

    if not TOKEN or not hmac.compare_digest(token, TOKEN):
        return {"ok": False, "message": "Invalid token"}

    ADMIN_SIDS.add(request.sid)
    join_room("admins")

    return {
        "ok": True,
        "visitors": visitor_count(),
        "activity": list(ACTIVITY)
    }

@socketio.on("visitor_join")
def visitor_join(data):
    data = data if isinstance(data, dict) else {}

    visitor_id = str(data.get("visitor_id", ""))[:50]
    if not re.fullmatch(r"[a-zA-Z0-9_-]{8,50}", visitor_id):
        return

    VISITORS[request.sid] = visitor_id

    log_event({
        "type": "new_visitor",
        "visitor": visitor_id[:12],
        "page": "Website opened",
        "device": str(data.get("device", "Unknown"))[:20]
    })

    socketio.emit("visitor_count", visitor_count(), to="admins")

@socketio.on("visitor_event")
def visitor_event(data):
    data = data if isinstance(data, dict) else {}

    if request.sid not in VISITORS:
        return

    allowed = {
        "page_view",
        "button_click",
        "form_interaction",
        "form_submit",
        "page_navigation"
    }

    event_type = str(data.get("type", ""))

    if event_type not in allowed:
        return

    page = str(data.get("page", ""))[:40]
    target = str(data.get("target", ""))[:64]

    log_event({
        "type": event_type,
        "visitor": VISITORS[request.sid][:12],
        "page": page,
        "target": target
    })

@socketio.on("control_update")
def control_update(data):
    if request.sid not in ADMIN_SIDS:
        return {"ok": False, "message": "Not authorized"}

    data = data if isinstance(data, dict) else {}

    element_id = str(data.get("id", ""))
    action = str(data.get("action", ""))
    value = str(data.get("value", ""))

    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}", element_id):
        return {"ok": False, "message": "Invalid element ID"}

    if action not in ("text", "background", "color", "hide", "show"):
        return {"ok": False, "message": "Invalid action"}

    if len(value) > 300:
        return {"ok": False, "message": "Value too long"}

    if action in ("background", "color"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            return {"ok": False, "message": "Invalid HEX color"}

    socketio.emit("site_control", {
        "id": element_id,
        "action": action,
        "value": value
    }, skip_sid=request.sid)

    return {"ok": True, "message": "Control command sent"}

@socketio.on("disconnect")
def disconnected(reason=None):
    ADMIN_SIDS.discard(request.sid)

    visitor_id = VISITORS.pop(request.sid, None)

    if visitor_id:
        log_event({
            "type": "visitor_left",
            "visitor": visitor_id[:12],
            "page": "Connection ended"
        })

        socketio.emit("visitor_count", visitor_count(), to="admins")


DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Website Owner Dashboard</title>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<style>
*{box-sizing:border-box}
body{margin:0;background:#101820;color:white;font-family:Arial;padding:20px}
.container{max-width:850px;margin:auto}
.card{background:#1b2935;border-radius:12px;padding:18px;margin:14px 0}
input,select,button{width:100%;padding:12px;margin:7px 0;border:0;border-radius:7px}
button{background:#00c8ff;color:#07121a;font-weight:bold;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.stat{background:#263746;padding:18px;border-radius:10px}
.number{font-size:30px;color:#00e6a0;font-weight:bold}
.event{padding:12px 4px;border-bottom:1px solid #344450;font-size:14px}
.small{color:#aab9c5;font-size:12px}
#dashboard{display:none}
</style>
</head>
<body>
<div class="container">
<h2>⚡ Website Owner Dashboard</h2>

<div class="card" id="login">
<h3>Admin Login</h3>
<input id="token" type="password" placeholder="Enter admin token">
<button onclick="login()">CONNECT DASHBOARD</button>
<p id="loginStatus"></p>
</div>

<div id="dashboard">
<div class="grid">
<div class="stat">
<div class="number" id="visitors">0</div>
<div>Active visitors</div>
</div>
<div class="stat">
<div class="number" id="events">0</div>
<div>Recent activities</div>
</div>
</div>

<div class="card">
<h3>🔔 Notifications</h3>
<button onclick="enableNotifications()">ENABLE BROWSER NOTIFICATIONS</button>
<p class="small">Notifications work when this dashboard is open and browser permission is granted.</p>
</div>

<div class="card">
<h3>📊 Live Activity</h3>
<div id="logs">Waiting for visitors...</div>
</div>

<div class="card">
<h3>🎨 Website Live Controller</h3>

<input id="element" placeholder="Element ID">

<select id="action">
<option value="text">Change Text</option>
<option value="background">Change Background</option>
<option value="color">Change Text Color</option>
<option value="hide">Hide Element</option>
<option value="show">Show Element</option>
</select>

<input id="value" placeholder="Text or HEX color">

<button onclick="sendControl()">APPLY LIVE CHANGE</button>
<p id="controlStatus"></p>
</div>
</div>
</div>

<script>
let socket;
let totalEvents = 0;

function login(){
    socket = io();

    socket.on("connect", async () => {
        const result = await new Promise(resolve => {
            socket.emit("admin_auth",
                {token: document.getElementById("token").value},
                resolve
            );
        });

        if(!result || !result.ok){
            document.getElementById("loginStatus").innerText =
                "Login failed: invalid token";
            socket.disconnect();
            return;
        }

        document.getElementById("login").style.display = "none";
        document.getElementById("dashboard").style.display = "block";

        document.getElementById("visitors").innerText = result.visitors;

        result.activity.forEach(addLog);
    });

    socket.on("connect_error", () => {
        document.getElementById("loginStatus").innerText =
            "Connection failed";
    });

    socket.on("activity", addLog);

    socket.on("visitor_count", count => {
        document.getElementById("visitors").innerText = count;
    });
}

function addLog(event){
    totalEvents++;
    document.getElementById("events").innerText = totalEvents;

    const box = document.getElementById("logs");
    const row = document.createElement("div");
    row.className = "event";

    const names = {
        new_visitor: "🟢 New visitor entered",
        visitor_left: "⚪ Visitor disconnected",
        page_view: "📄 Page opened",
        page_navigation: "➡️ Page navigation",
        button_click: "🖱️ Button clicked",
        form_interaction: "⌨️ Form interacted",
        form_submit: "📨 Form submitted"
    };

    row.textContent =
        (names[event.type] || event.type) +
        " | Visitor: " + (event.visitor || "-") +
        " | Page: " + (event.page || "-") +
        " | Target: " + (event.target || "-") +
        " | " + (event.time || "");

    box.prepend(row);

    if(event.type === "new_visitor" &&
       "Notification" in window &&
       Notification.permission === "granted"){
        new Notification("New website visitor", {
            body: "A visitor opened your website"
        });
    }
}

function enableNotifications(){
    if("Notification" in window){
        Notification.requestPermission();
    }
}

function sendControl(){
    socket.emit("control_update", {
        id: document.getElementById("element").value,
        action: document.getElementById("action").value,
        value: document.getElementById("value").value
    }, result => {
        document.getElementById("controlStatus").innerText =
            result ? result.message : "No server response";
    });
}
socket.on("connect", () => {
    console.log("CONNECTED:", socket.id);
});

socket.on("connect_error", (error) => {
    alert("Connection Error: " + error.message);
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Set CONTROL_TOKEN environment variable")

    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
)

