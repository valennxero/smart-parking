#!/usr/bin/env bash
# Menjalankan Edge Agent untuk 3 slot (A1, A2, A3) di Raspberry Pi tanpa Docker.
#
# Pemakaian (dari folder project atau folder mana saja):
#   ./run_edge_3slots.sh start  <IP-laptop>   # jalankan 3 agent
#   ./run_edge_3slots.sh status               # cek agent yang hidup
#   ./run_edge_3slots.sh logs                 # lihat log gabungan (Ctrl+C untuk keluar)
#   ./run_edge_3slots.sh stop                 # hentikan semua agent
#
# Letakkan file ini di folder project (sejajar dengan edge-agent/ dan data/),
# atau di scripts/. Skrip mencari folder edge-agent otomatis.

set -u

SLOTS=(A1 A2 A3)
PERIODS=(8 11 14)          # SIM_PERIOD berbeda agar slot tidak berganti serempak
VENV="${VENV:-$HOME/venv}"

# Cari folder project (yang berisi edge-agent/app.py)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if   [ -f "$HERE/edge-agent/app.py" ];    then ROOT="$HERE"
elif [ -f "$HERE/../edge-agent/app.py" ]; then ROOT="$(cd "$HERE/.." && pwd)"
else echo "edge-agent/app.py tidak ditemukan dari $HERE"; exit 1; fi

DATA="$ROOT/data"
RUN="$DATA/run"
mkdir -p "$DATA" "$RUN"

cmd="${1:-}"

case "$cmd" in
  start)
    BROKER="${2:-${BROKER_HOST:-}}"
    if [ -z "$BROKER" ]; then
      echo "Pemakaian: $0 start <IP-laptop>   (contoh: $0 start 10.20.72.9)"; exit 1
    fi
    if [ ! -f "$VENV/bin/activate" ]; then
      echo "Virtualenv tidak ada di $VENV. Buat dulu: python3 -m venv ~/venv && ~/venv/bin/pip install paho-mqtt"; exit 1
    fi
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"

    # Hindari client_id ganda: hentikan agent lama lebih dulu
    if pgrep -f "python3 app.py" >/dev/null; then
      echo "Ada agent yang masih berjalan, dihentikan dulu..."
      pkill -f "python3 app.py"; sleep 1
    fi

    cd "$ROOT/edge-agent" || exit 1
    for i in "${!SLOTS[@]}"; do
      s="${SLOTS[$i]}"; p="${PERIODS[$i]}"
      BROKER_HOST="$BROKER" SLOT_ID="$s" SIM_PERIOD="$p" \
        LATENCY_FILE="$DATA/latency-$s.csv" \
        nohup python3 app.py > "$DATA/edge-$s.log" 2>&1 &
      echo $! > "$RUN/$s.pid"
      echo "Agent $s dimulai (PID $!, SIM_PERIOD=$p, broker=$BROKER)"
      sleep 1
    done
    echo
    echo "Selesai. Lihat log: $0 logs   |   Status: $0 status"
    ;;

  status)
    for s in "${SLOTS[@]}"; do
      pidf="$RUN/$s.pid"
      if [ -f "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null; then
        echo "$s: HIDUP (PID $(cat "$pidf")) | log terakhir: $(tail -n 1 "$DATA/edge-$s.log" 2>/dev/null | cut -c1-90)"
      else
        echo "$s: MATI"
      fi
    done
    ;;

  logs)
    tail -n 5 -f "$DATA"/edge-A1.log "$DATA"/edge-A2.log "$DATA"/edge-A3.log
    ;;

  stop)
    # SIGTERM tanpa disconnect rapi -> Last Will terkirim oleh broker
    for s in "${SLOTS[@]}"; do
      pidf="$RUN/$s.pid"
      if [ -f "$pidf" ]; then kill "$(cat "$pidf")" 2>/dev/null; rm -f "$pidf"; fi
    done
    pkill -f "python3 app.py" 2>/dev/null
    echo "Semua agent dihentikan."
    ;;

  *)
    echo "Pemakaian: $0 {start <IP-laptop>|status|logs|stop}"; exit 1
    ;;
esac
