#!/usr/bin/env bash
# Log into Instagram or Facebook ON the VM via Chrome remote debugging + SSH tunnel.
#
# Easier alternative (recommended for Instagram):
#   Mac: python scripts/export_session.py instagram && scp ig_session.json linux@VM:~/FB-Insta-Messenger-Automation/
#   VM:  python scripts/import_session.py ig_session.json instagram
set -euo pipefail
cd "$(dirname "$0")/.."

PLATFORM="${1:-instagram}"
DEBUG_PORT="${DEBUG_PORT:-9222}"
VM_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
VM_IP="${VM_IP:-YOUR_VM_IP}"

if [[ "$PLATFORM" != "instagram" && "$PLATFORM" != "facebook" ]]; then
  echo "Usage: $0 instagram|facebook"
  exit 1
fi

if [[ -d venv ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

if ss -ltn 2>/dev/null | grep -q ":${DEBUG_PORT} "; then
  echo "ERROR: Port ${DEBUG_PORT} is already in use. Stop the other process or: DEBUG_PORT=9223 $0 $PLATFORM"
  exit 1
fi

echo "==> Stopping dashboard if running (avoids profile lock)…"
pkill -f "uvicorn server:app" 2>/dev/null || true
sleep 1

echo ""
echo "==> Step 1: leave THIS terminal running — starting browser on port ${DEBUG_PORT}…"
echo ""
echo "    When you see 'Browser ready on the VM', do Step 2 ON YOUR MAC (not on this VM):"
echo ""
echo "      ssh -N -L ${DEBUG_PORT}:127.0.0.1:${DEBUG_PORT} linux@${VM_IP}"
echo ""
echo "    Step 3 on Mac: open Chrome → http://127.0.0.1:${DEBUG_PORT}"
echo "    Click the ${PLATFORM} tab → log in (password + 2FA)."
echo ""
echo "    (Connection refused = SSH tunnel started before this script, or wrong order.)"
echo ""

python scripts/setup_login_cli.py "$PLATFORM" --remote --port "$DEBUG_PORT"

echo ""
echo "==> Done. Start the server:"
echo "    uvicorn server:app --host 0.0.0.0 --port 8000"
