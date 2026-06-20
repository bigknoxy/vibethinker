#!/bin/bash

LOGFILE="/root/watchdog.log"
SERVER_CMD="python3 /root/serve_vibethinker.py"
SERVER_LOG="/root/vibethinker_server.log"
HEALTH_URL="http://localhost:8002/v1/models"
PIDFILE="/tmp/vibethinker_watchdog.pid"
CHECK_INTERVAL=10
MAX_FAILURES=3

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOGFILE"
}

start_server() {
    log "Starting server: $SERVER_CMD"
    nohup $SERVER_CMD >> "$SERVER_LOG" 2>&1 &
    SERVER_PID=$!
    log "Server started with PID $SERVER_PID"
}

cleanup() {
    log "Watchdog shutting down"
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill -9 "$SERVER_PID" 2>/dev/null
        log "Killed server PID $SERVER_PID"
    fi
    rm -f "$PIDFILE"
    exit 0
}

trap cleanup SIGTERM SIGINT SIGHUP

echo $$ > "$PIDFILE"

start_server

fail_count=0

while true; do
    sleep "$CHECK_INTERVAL"

    if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        fail_count=0
        continue
    fi

    fail_count=$((fail_count + 1))
    log "Health check failed ($fail_count/$MAX_FAILURES)"

    if [ "$fail_count" -ge "$MAX_FAILURES" ]; then
        log "Server unhealthy after $MAX_FAILURES consecutive failures, killing and restarting"
        if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
            kill -9 "$SERVER_PID" 2>/dev/null
            log "Sent SIGKILL to PID $SERVER_PID"
        fi
        sleep 1
        start_server
        fail_count=0
    fi
done
