"""Fog: Data Aggregator + dashboard web sederhana.

Subscribe status semua slot, hitung ketersediaan area, publish ringkasan,
tulis log telemetry, dan tampilkan dashboard di http://localhost:5000
"""
import json
import os
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template_string

BROKER = os.getenv("BROKER_HOST", "localhost")
PORT = int(os.getenv("BROKER_PORT", "1883"))
LOG_FILE = os.getenv("TELEMETRY_LOG", "/data/telemetry.log")
STALE_S = float(os.getenv("STALE_SECONDS", "0"))  # 0 = tidak dipakai

slots = {}    # (floor, slot_id) -> dict
agents = {}   # (floor, slot_id) -> "1"/"0"
lock = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def summary():
    with lock:
        floors = {}
        for (fl, sid), v in slots.items():
            f = floors.setdefault(fl, {"free": 0, "occupied": 0, "total": 0})
            f["total"] += 1
            f["free" if v["status"] == "FREE" else "occupied"] += 1
        return floors


def on_connect(c, u, f, rc, p=None):
    print(f"[FOG] terhubung ke broker {BROKER}:{PORT}", flush=True)
    c.subscribe([("parking/+/slot/+", 1), ("parking/+/agent/+/online", 1)])


def on_message(c, u, msg):
    parts = msg.topic.split("/")
    try:
        if len(parts) == 4 and parts[2] == "slot":
            data = json.loads(msg.payload)
            data["received_at"] = now_iso()
            with lock:
                slots[(parts[1], parts[3])] = data
            line = f"{data['received_at']} {msg.topic} {msg.payload.decode()}"
            print(f"[FOG] RECV {line}", flush=True)
            with open(LOG_FILE, "a") as fh:
                fh.write(line + "\n")
            s = summary()[parts[1]]
            print(f"[FOG] {parts[1]}: tersisa {s['free']} dari {s['total']} slot", flush=True)
            c.publish(f"parking/{parts[1]}/summary", json.dumps(s), qos=1, retain=True)
        elif len(parts) == 5 and parts[4] == "online":
            with lock:
                agents[(parts[1], parts[3])] = msg.payload.decode()
            print(f"[FOG] agent {parts[3]} online={msg.payload.decode()}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[FOG] pesan diabaikan ({e})", flush=True)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fog-aggregator")
client.on_connect, client.on_message = on_connect, on_message
client.reconnect_delay_set(1, 5)

app = Flask(__name__)
PAGE = """<!doctype html><meta charset=utf-8><title>Smart Parking - Fog Dashboard</title>
<style>
body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;margin:2rem}
h1{margin:0 0 .3rem}.sum{font-size:1.4rem;margin:1rem 0}
.grid{display:flex;gap:1rem;flex-wrap:wrap}
.slot{width:150px;padding:1rem;border-radius:12px;text-align:center;font-weight:600}
.FREE{background:#166534}.OCCUPIED{background:#991b1b}
.slot small{display:block;font-weight:400;opacity:.85;margin-top:.4rem}
.off{outline:3px dashed #f59e0b}
</style>
<h1>Smart Parking - Fog Dashboard</h1><div id=s class=sum></div><div id=g class=grid></div>
<script>
async function tick(){
  const r=await (await fetch('/api/state')).json();
  document.getElementById('s').textContent=Object.entries(r.summary).map(
    ([f,v])=>`${f}: tersisa ${v.free} dari ${v.total} slot`).join(' | ')||'menunggu data...';
  document.getElementById('g').innerHTML=r.slots.map(x=>
    `<div class="slot ${x.status} ${x.online==='0'?'off':''}">${x.slot_id}<br>${x.status}
     <small>${x.distance_cm} cm</small><small>agent: ${x.online==='0'?'OFFLINE':'online'}</small></div>`).join('');
}
tick();setInterval(tick,1000);
</script>"""


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/api/state")
def state():
    with lock:
        rows = []
        for (fl, sid), v in sorted(slots.items()):
            rows.append({**v, "floor": fl, "online": agents.get((fl, sid), "1")})
    return jsonify({"summary": summary(), "slots": rows})


def mqtt_loop():
    while True:
        try:
            client.connect(BROKER, PORT, keepalive=10)
            client.loop_forever()
        except Exception as e:  # noqa: BLE001
            print(f"[FOG] broker belum siap ({e}), coba lagi...", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
    threading.Thread(target=mqtt_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
