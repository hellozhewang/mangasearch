#!/bin/sh
# MangaSearch web server manager (macOS).
#
#   sh serve.sh start [port]   start now + auto-start at login (installs launchd agent)
#   sh serve.sh stop           stop until next login / `start`
#   sh serve.sh status         is it loaded? is it answering?
#   sh serve.sh build          rebuild the frontend (web/ -> docs/), no restart
#   sh serve.sh deploy [port]  rebuild the frontend, then restart the server
#   sh serve.sh uninstall      stop and remove the launchd agent
#   sh serve.sh run [port]     run in the foreground (what launchd executes)
#
# Runs src/serve.py: static docs/ plus the /api/* JSON endpoints. Static
# serving covers ONLY docs/ — never the repo root, which holds .env, the
# DB, and .git. Default port: 8000.

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DIR")"
PORT="${2:-8000}"
LABEL="com.zzwang.mangasearch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="/tmp/mangasearch-serve.log"

# GUI domain when a desktop session exists, else the user domain (SSH-only).
if launchctl print "gui/$(id -u)" >/dev/null 2>&1; then
    DOMAIN="gui/$(id -u)"
else
    DOMAIN="user/$(id -u)"
fi
TARGET="$DOMAIN/$LABEL"

install_agent() {
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/sh</string>
        <string>$DIR/serve.sh</string>
        <string>run</string>
        <string>$PORT</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOG</string>
    <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF
}

build_frontend() {
    echo "Building frontend (web/ -> docs/)..."
    (cd "$ROOT/web" && npm run build) || exit 1
}

start_agent() {
    [ -f "$PLIST" ] || install_agent
    launchctl bootout "$TARGET" 2>/dev/null
    # bootout is asynchronous; retry bootstrap until launchd lets go.
    for attempt in 1 2 3 4; do
        sleep 1
        launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null && break
        if [ "$attempt" = 4 ]; then
            echo "bootstrap failed after 4 attempts" >&2
            exit 1
        fi
    done
    sleep 1
    sh "$0" status "$PORT"
}

case "${1:-status}" in
    run)
        exec python3 -u "$ROOT/src/serve.py" "$PORT"
        ;;
    start)
        start_agent
        ;;
    build)
        build_frontend
        ;;
    deploy)
        build_frontend
        start_agent
        ;;
    stop)
        if launchctl bootout "$TARGET" 2>/dev/null; then
            echo "Stopped. (Starts again at next login, or with: sh serve.sh start)"
        else
            echo "Not running."
        fi
        ;;
    status)
        if launchctl print "$TARGET" >/dev/null 2>&1; then
            PID=$(launchctl print "$TARGET" 2>/dev/null | awk '/[ \t]pid = /{print $3; exit}')
            echo "launchd: loaded${PID:+ (pid $PID)}"
        else
            echo "launchd: not loaded"
        fi
        CODE=$(curl -s -o /dev/null -w '%{http_code}' -m 3 "http://127.0.0.1:$PORT/" 2>/dev/null)
        IP=$(ipconfig getifaddr en0 2>/dev/null || echo 127.0.0.1)
        if [ "$CODE" = "200" ]; then
            echo "http:    OK — http://$IP:$PORT"
        else
            echo "http:    NOT responding on port $PORT"
        fi
        ;;
    uninstall)
        launchctl bootout "$TARGET" 2>/dev/null
        rm -f "$PLIST"
        echo "Agent removed."
        ;;
    *)
        echo "Usage: sh serve.sh {start|stop|status|build|deploy|uninstall|run} [port]" >&2
        exit 1
        ;;
esac
