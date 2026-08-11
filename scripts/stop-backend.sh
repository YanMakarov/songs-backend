#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BACKEND_DIR=$(cd -- "${SCRIPT_DIR}/.." && pwd)
DEFAULT_PID_FILE="${BACKEND_DIR}/.backend.pid"
PID_FILE=${BACKEND_PID_FILE:-${DEFAULT_PID_FILE}}
WAIT_SECONDS=${BACKEND_STOP_TIMEOUT:-10}
FORCE_SIGNAL=${BACKEND_FORCE_SIGNAL:-9}

if [[ ! -f "${PID_FILE}" ]]; then
  echo "No backend PID file found at ${PID_FILE}. Nothing to stop."
  exit 0
fi

backend_pid=$(cat "${PID_FILE}" 2>/dev/null || true)

if [[ -z "${backend_pid}" || ! "${backend_pid}" =~ ^[0-9]+$ ]]; then
  echo "PID file ${PID_FILE} is invalid. Removing it." >&2
  rm -f -- "${PID_FILE}"
  exit 1
fi

if ! kill -0 "${backend_pid}" 2>/dev/null; then
  echo "Backend process ${backend_pid} not running. Cleaning up PID file."
  rm -f -- "${PID_FILE}"
  exit 0
fi

echo "Stopping backend (PID ${backend_pid})"
kill -TERM "${backend_pid}" 2>/dev/null || true

for ((i = 0; i < WAIT_SECONDS; i++)); do
  if ! kill -0 "${backend_pid}" 2>/dev/null; then
    rm -f -- "${PID_FILE}"
    echo "Backend stopped."
    exit 0
  fi
  sleep 1
done

echo "Backend still running; sending SIG${FORCE_SIGNAL}" >&2
kill -"${FORCE_SIGNAL}" "${backend_pid}" 2>/dev/null || true
rm -f -- "${PID_FILE}"
exit 0
