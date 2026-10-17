#!/usr/bin/env bash
# demo_tunnel.sh - serves the app from this machine on a temporary public HTTPS link (Cloudflare quick tunnel).
#
#   make demo        # or: bash scripts/demo_tunnel.sh
#
# Prints a https://<random>.trycloudflare.com link that works while this script runs; Ctrl+C stops both the app
# and the tunnel. No Cloudflare account is needed. Live PostgreSQL/MySQL introspection is turned off because the
# link is public. Needs cloudflared (https://github.com/cloudflare/cloudflared/releases) and a built web app.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
CLOUDFLARED=$(command -v cloudflared || echo "$HOME/.local/bin/cloudflared")
PORT=${PORT:-8000}
LOG=$(mktemp -t sqldiagnose-tunnel.XXXX.log)

[ -x "$CLOUDFLARED" ] || { echo "cloudflared not found; install it from https://github.com/cloudflare/cloudflared/releases"; exit 1; }
[ -f frontend/dist/index.html ] || { echo "web app not built; run 'make frontend' first"; exit 1; }

cleanup() { kill "$API" "$TUNNEL" 2>/dev/null || true; wait 2>/dev/null || true; rm -f "$LOG"; }
trap cleanup EXIT INT TERM

SQLDIAGNOSE_LIVE_SCHEMA=false $PY -m uvicorn deployment.api.main:app --host 127.0.0.1 --port "$PORT" \
  --proxy-headers --log-level warning &
API=$!

echo "Starting the app (loading the classifier) ..."
for _ in $(seq 120); do
  curl -sf "http://127.0.0.1:$PORT/api/v1/health" >/dev/null && break
  kill -0 "$API" 2>/dev/null || { echo "the app failed to start"; exit 1; }
  sleep 1
done

"$CLOUDFLARED" tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" >"$LOG" 2>&1 &
TUNNEL=$!
for _ in $(seq 60); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1 || true)
  [ -n "$URL" ] && break
  kill -0 "$TUNNEL" 2>/dev/null || { cat "$LOG"; echo "the tunnel failed to start"; exit 1; }
  sleep 1
done
[ -n "${URL:-}" ] || { cat "$LOG"; echo "no tunnel link after 60 s"; exit 1; }

echo
echo "  SQLDiagnose is live at:  $URL"
echo "  (local: http://127.0.0.1:$PORT)   Ctrl+C to stop"
echo
wait "$TUNNEL"
