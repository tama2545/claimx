#!/bin/bash
set -e

cleanup() {
    echo "Stopping all processes..."
    kill ${API_PID:-0} ${APP_PID:-0} ${XVFB_PID:-0} 2>/dev/null || true
    pkill -f "tor -f" 2>/dev/null || true
    pkill -f "Api.js|app.py" 2>/dev/null || true
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
    exit 0
}
trap cleanup SIGINT SIGTERM

export DISPLAY=:99

# ===================== 1. START Xvfb =====================
echo "Starting Xvfb..."
pkill -x Xvfb 2>/dev/null || true
rm -f /tmp/.X99-lock
rm -rf /tmp/.X11-unix/X99

Xvfb :99 -screen 0 1366x768x24 -ac -nolisten tcp +extension RANDR >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
sleep 2
if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo "Xvfb gagal!"; cat /tmp/xvfb.log; exit 1
fi
echo "Xvfb OK (PID $XVFB_PID)"

# ===================== 2. START TOR MULTI-INSTANCE =====================
echo "=== Setting up Tor Multi-Instance (6 SOCKS) ==="

# Hentikan Tor yang mungkin berjalan
pkill -f "tor -f" 2>/dev/null || true
sleep 2

BASE_SOCKS=9050
BASE_CONTROL=10050
DATA_DIR="/app/tor_data"
mkdir -p "$DATA_DIR"

for i in {0..11}; do
    SOCKS=$((BASE_SOCKS + i))
    CONTROL=$((BASE_CONTROL + i))
    TORRC="/app/.torrc_thread_$i"
    DATADIR="$DATA_DIR/instance_$i"
    mkdir -p "$DATADIR"
    cat > "$TORRC" <<EOF
SOCKSPort $SOCKS
ControlPort $CONTROL
CookieAuthentication 1
DataDirectory $DATADIR
Log notice file /app/tor-notices-$i.log
EOF
    echo "Starting Tor instance $i (SOCKS $SOCKS)..."
    tor -f "$TORRC" --runasdaemon 1
done

echo "Waiting for Tor SOCKS ports (9050-9055)..."
for i in {1..30}; do
    all_ready=true
    for port in {9050..9061}; do
        if ! nc -z 127.0.0.1 $port 2>/dev/null; then
            all_ready=false
            break
        fi
    done
    if $all_ready; then
        break
    fi
    sleep 2
done

# Tunggu bootstrap setiap instance (ambil dari log)
for i in {0..11}; do
    logfile="/app/tor-notices-$i.log"
    echo "Menunggu bootstrap instance $i..."
    while ! grep -q "Bootstrapped 100%" "$logfile" 2>/dev/null; do
        sleep 2
    done
    echo "✅ Instance $i siap."
done

echo "All Tor instances ready."

# ===================== 3. START API =====================
echo "Starting API (Api.js)..."
cd /app/Api
node --expose-gc --no-deprecation Api.js &
API_PID=$!
echo "API PID: $API_PID"

# Tunggu API siap
echo "Waiting for API (port 8080)..."
for i in {1..120}; do
    if curl -fs http://127.0.0.1:8080 >/dev/null 2>&1; then
        echo "API ready."
        break
    fi
    sleep 1
    if [ $i -eq 120 ]; then
        echo "API timeout, killing..."
        kill $API_PID 2>/dev/null || true
        exit 1
    fi
done

# ===================== 4. START BOT =====================
cd /app
echo "Starting app.py (multi-account bot)..."
sleep 60
python app.py &
APP_PID=$!
echo "APP PID: $APP_PID"

# Tunggu salah satu proses mati
wait -n $API_PID $APP_PID
cleanup
