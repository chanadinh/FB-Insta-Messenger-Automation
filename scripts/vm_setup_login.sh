#!/usr/bin/env bash
# Log into Instagram or Facebook ON the VM.
#
# Recommended: --remote  (log in from your Mac via Chrome + SSH tunnel)
#   ./scripts/vm_setup_login.sh instagram
#
# Or import session from Mac (best for Instagram):
#   Mac:  python scripts/export_session.py instagram
#   scp ig_session.json linux@VM:~/FB-Insta-Messenger-Automation/
#   VM:   python scripts/import_session.py ig_session.json instagram
set -euo pipefail
cd "$(dirname "$0")/.."

PLATFORM="${1:-instagram}"
DEBUG_PORT="${DEBUG_PORT:-9222}"

if [[ "$PLATFORM" != "instagram" && "$PLATFORM" != "facebook" ]]; then
  echo "Usage: $0 instagram|facebook"
  exit 1
fi

if [[ -d venv ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

echo "==> Stopping dashboard if running (avoids profile lock)…"
pkill -f "uvicorn server:app" 2>/dev/null || true
sleep 1

echo "==> Starting browser with remote debugging on port ${DEBUG_PORT}…"
echo ""
echo "    ON YOUR MAC, open a new terminal and run:"
echo "      ssh -L ${DEBUG_PORT}:127.0.0.1:${DEBUG_PORT} linux@$(hostname -I 2>/dev/null | awk '{print $1}' || echo YOUR_VM_IP)"
echo ""
echo "    Then open Chrome and visit:  http://127.0.0.1:${DEBUG_PORT}"
echo "    Click the ${PLATFORM} tab, log in (password + 2FA)."
echo ""

python scripts/setup_login_cli.py "$PLATFORM" --remote --port "$DEBUG_PORT"

echo ""
echo "==> Done. Start the server:"
echo "    uvicorn server:app --host 0.0.0.0 --port 8000"
