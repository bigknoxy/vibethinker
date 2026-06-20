#!/bin/bash

LOGFILE="/root/watchdog.log"
HEALTH_URL="http://localhost:8002/v1/models"
PIDFILE="/tmp/vibethinker_watchdog.pid"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOGFILE"
}

log "=== Starting vibe server ==="

# Kill anything on port 8002
PID_ON_PORT=$(lsof -ti :8002 2>/dev/null)
if [ -n "$PID_ON_PORT" ]; then
    log "Killing existing process(es) on port 8002: $PID_ON_PORT"
    kill -9 $PID_ON_PORT 2>/dev/null
    sleep 1
fi

# Kill any existing watchdog
if [ -f "$PIDFILE" ]; then
    OLD_WATCHDOG_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_WATCHDOG_PID" 2>/dev/null; then
        log "Killing existing watchdog PID $OLD_WATCHDOG_PID"
        kill -9 "$OLD_WATCHDOG_PID" 2>/dev/null
        sleep 1
    fi
    rm -f "$PIDFILE"
fi

# Start watchdog in background
log "Starting watchdog"
nohup /root/watchdog.sh > /dev/null 2>&1 &
WATCHDOG_PID=$!
log "Watchdog started with PID $WATCHDOG_PID"

# Wait for server to become healthy (up to 120 seconds)
log "Waiting for server to become healthy..."
for i in $(seq 1 120); do
    if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        log "Server is healthy after ${i}s"
        echo "Server started successfully (healthy after ${i}s)"
        exit 0
    fi
    sleep 1
done

log "Server failed to become healthy within 120 seconds"
echo "Server failed to start within 120 seconds" >&2
exit 1
