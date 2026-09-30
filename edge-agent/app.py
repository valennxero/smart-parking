"""Edge Agent Smart Parking: Sense -> Think -> Act -> Report (MQTT asinkron).

Prinsip failover: keputusan (Think) dan aksi (Act) TIDAK pernah bergantung pada
broker. Report dilakukan sesudahnya, dan bila gagal disimpan di buffer lokal.
"""
import csv
import json
import os
import signal
import time
from collections import deque
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from actuator import get_led
from sensor import get_sensor

SLOT_ID = os.getenv("SLOT_ID", "A1")
FLOOR = os.getenv("FLOOR", "lantai-1")
BROKER = os.getenv("BROKER_HOST", "localhost")
PORT = int(os.getenv("BROKER_PORT", "1883"))
THRESHOLD = float(os.getenv("THRESHOLD_CM", "10"))
CONFIRM_N = int(os.getenv("CONFIRM_N", "2"))      # debounce: 2 pembacaan sama
LOOP_S = float(os.getenv("LOOP_SECONDS", "1"))
MAX_VALID = 200.0                                  # di atas ini = outlier HC-SR04
BUF_MAX = int(os.getenv("BUFFER_MAX", "500"))
LAT_FILE = os.getenv("LATENCY_FILE", "/data/latency.csv")
TOPIC = f"parking/{FLOOR}/slot/{SLOT_ID}"
ONLINE_TOPIC = f"parking/{FLOOR}/agent/{SLOT_ID}/online"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    print(f"[{SLOT_ID}] {msg}", flush=True)


# ---------------- REPORT layer (asinkron, tidak memblokir loop) ----------------
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"edge-{SLOT_ID}")
client.will_set(ONLINE_TOPIC, "0", qos=1, retain=True)   # broker menandai agent offline
buffer = deque(maxlen=BUF_MAX)   # pesan yang belum terkirim
pending = {}                     # mid -> payload, menunggu PUBACK
connected = False


def flush_buffer():
    n = 0
    while buffer and connected:
        payload = buffer.popleft()
        info = client.publish(TOPIC, payload, qos=1, retain=True)
        pending[info.mid] = payload
        n += 1
    if n:
        log(f"FAILOVER PULIH: {n} pesan buffer dikirim ulang")


def on_connect(c, userdata, flags, rc, props=None):
    global connected
    connected = not rc.is_failure
    if connected:
        log(f"MQTT terhubung ke {BROKER}:{PORT}")
        c.publish(ONLINE_TOPIC, "1", qos=1, retain=True)
        flush_buffer()
    else:
        log(f"MQTT gagal terhubung: {rc}")


def on_disconnect(c, userdata, flags, rc, props=None):
    global connected
    connected = False
    # pesan yang belum di-ACK dikembalikan ke buffer agar tidak hilang
    for payload in pending.values():
        buffer.appendleft(payload)
    pending.clear()
    log("!! MQTT TERPUTUS -> Edge TETAP berjalan (mode failover, telemetry di-buffer)")


def on_publish(c, userdata, mid, rc=None, props=None):
    pending.pop(mid, None)


client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_publish = on_publish
client.reconnect_delay_set(min_delay=1, max_delay=5)


def start_mqtt():
    try:
        client.connect_async(BROKER, PORT, keepalive=5)  # tidak melempar walau broker mati
        client.loop_start()
    except Exception as e:  # noqa: BLE001
        log(f"MQTT init error (diabaikan, Edge tetap jalan): {e}")


def report(status, dist):
    payload = json.dumps(
        {"slot_id": SLOT_ID, "status": status, "distance_cm": dist, "ts": now_iso()}
    )
    if connected:
        try:
            info = client.publish(TOPIC, payload, qos=1, retain=True)
            pending[info.mid] = payload
            log(f"REPORT -> {TOPIC} {payload}")
            return
        except Exception:  # noqa: BLE001
            pass
    buffer.append(payload)
    log(f"REPORT tertunda (offline) -> masuk buffer, isi buffer = {len(buffer)}")


# ---------------- THINK layer (murni lokal, tanpa I/O, diukur latensinya) --------
def think(distance, state):
    """Kembalikan status baru. Outlier dibuang, perubahan butuh CONFIRM_N pembacaan sama."""
    if distance <= 0 or distance > MAX_VALID:
        return state["status"]
    raw = "OCCUPIED" if distance < THRESHOLD else "FREE"
    if raw == state["status"]:
        state["cand"], state["cnt"] = None, 0
        return state["status"]
    if raw == state["cand"]:
        state["cnt"] += 1
    else:
        state["cand"], state["cnt"] = raw, 1
    if state["cnt"] >= CONFIRM_N:
        state["cand"], state["cnt"] = None, 0
        return raw
    return state["status"]


def main():
    sensor, led = get_sensor(), get_led(SLOT_ID)
    state = {"status": "FREE", "cand": None, "cnt": 0}

    os.makedirs(os.path.dirname(LAT_FILE) or ".", exist_ok=True)
    fh = open(LAT_FILE, "a", newline="")
    writer = csv.writer(fh)
    if fh.tell() == 0:
        writer.writerow(["ts", "slot", "distance_cm", "think_us", "status"])

    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    start_mqtt()
    log(f"Edge Agent start | threshold={THRESHOLD}cm confirm={CONFIRM_N} topic={TOPIC}")
    led.set(state["status"])
    report(state["status"], -1)  # status awal (masuk buffer bila broker belum siap)

    while not stop:
        d = sensor.read_cm()                                   # SENSE
        t0 = time.perf_counter_ns()
        new = think(d, state)                                  # THINK (diukur)
        think_us = (time.perf_counter_ns() - t0) / 1000
        writer.writerow([now_iso(), SLOT_ID, d, f"{think_us:.2f}", new])
        fh.flush()
        log(f"SENSE d={d:>5} cm | THINK {think_us:6.1f} us | status={new}")
        if new != state["status"]:
            state["status"] = new
            led.set(new)                                       # ACT dulu (lokal)
            report(new, d)                                     # REPORT sesudahnya
        time.sleep(LOOP_S)

    log("shutdown")
    client.loop_stop()
    fh.close()


if __name__ == "__main__":
    main()
