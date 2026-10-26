#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi

  wait "${BACKEND_PID}" "${FRONTEND_PID}" 2>/dev/null || true
  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

cd "${ROOT_DIR}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required." >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is required." >&2
  exit 1
fi
if [[ ! -d "dashboard/node_modules" ]]; then
  echo "Installing dashboard dependencies..."
  (cd dashboard && npm install)
fi

echo "Starting backend at http://127.0.0.1:8000"
python3 -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

echo "Starting dashboard at http://127.0.0.1:5173"
(cd dashboard && npm run dev -- --host 127.0.0.1) &
FRONTEND_PID=$!

echo "Both services are running. Press Ctrl+C to stop them."
wait -n "${BACKEND_PID}" "${FRONTEND_PID}"
exit $?
