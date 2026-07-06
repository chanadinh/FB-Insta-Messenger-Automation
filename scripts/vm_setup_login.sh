#!/usr/bin/env bash
# Log into Instagram or Facebook ON the VM (creates a session that headless automation can use).
# Usage: ./scripts/vm_setup_login.sh instagram
#        ./scripts/vm_setup_login.sh facebook
set -euo pipefail
cd "$(dirname "$0")/.."

PLATFORM="${1:-instagram}"
if [[ "$PLATFORM" != "instagram" && "$PLATFORM" != "facebook" ]]; then
  echo "Usage: $0 instagram|facebook"
  exit 1
fi

if ! command -v xvfb-run >/dev/null 2>&1; then
  echo "Install Xvfb first: sudo apt-get update && sudo apt-get install -y xvfb"
  exit 1
fi

if [[ -d venv ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

echo "==> Stopping dashboard if running (avoids profile lock)…"
pkill -f "uvicorn server:app" 2>/dev/null || true
sleep 1

echo "==> Opening browser via virtual display (xvfb)…"
xvfb-run -a python scripts/setup_login_cli.py "$PLATFORM"

echo "==> Done. Start the server again and check session status on the dashboard."
echo "    uvicorn server:app --host 0.0.0.0 --port 8000"
