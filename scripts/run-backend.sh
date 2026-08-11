#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BACKEND_DIR=$(cd -- "${SCRIPT_DIR}/.." && pwd)
REPO_ROOT=$(cd -- "${BACKEND_DIR}/.." && pwd)
DEFAULT_ENV_FILE="${BACKEND_DIR}/.env"
FALLBACK_ENV_FILE="${BACKEND_DIR}/.env.example"
DEFAULT_PID_FILE="${BACKEND_DIR}/.backend.pid"

ENV_FILE=${BACKEND_ENV_FILE:-${DEFAULT_ENV_FILE}}

if [[ -f "${ENV_FILE}" ]]; then
  echo "Loading environment variables from ${ENV_FILE}"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
elif [[ -f "${FALLBACK_ENV_FILE}" ]]; then
  echo "${ENV_FILE} not found; loading defaults from ${FALLBACK_ENV_FILE}" >&2
  set -a
  # shellcheck disable=SC1090
  source "${FALLBACK_ENV_FILE}"
  set +a
else
  echo "No environment file found. Create ${DEFAULT_ENV_FILE} or set BACKEND_ENV_FILE." >&2
fi

PYTHON_BIN=${PYTHON_BIN:-}

if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python"
  elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3)
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python)
  else
    echo "Python interpreter not found. Install dependencies or set PYTHON_BIN." >&2
    exit 1
  fi
fi

HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}
RELOAD=${RELOAD:-1}
UVICORN_APP=${UVICORN_APP:-app.main:app}
PID_FILE=${BACKEND_PID_FILE:-${DEFAULT_PID_FILE}}
PID_DIR=$(dirname -- "${PID_FILE}")
uvicorn_pid=""

mkdir -p -- "${PID_DIR}"

if [[ -f "${PID_FILE}" ]]; then
  existing_pid=$(cat "${PID_FILE}" 2>/dev/null || true)
  if [[ -n "${existing_pid}" && "${existing_pid}" =~ ^[0-9]+$ ]]; then
    if kill -0 "${existing_pid}" 2>/dev/null; then
      echo "Backend already running (PID ${existing_pid}). Use scripts/stop-backend.sh or remove ${PID_FILE}" >&2
      exit 1
    fi
  fi
  rm -f -- "${PID_FILE}"
fi

cleanup_pid_file() {
  rm -f -- "${PID_FILE}"
}

forward_signal() {
  if [[ -n "${uvicorn_pid:-}" ]]; then
    if kill -0 "${uvicorn_pid}" 2>/dev/null; then
      kill -TERM "${uvicorn_pid}"
    fi
  fi
}

trap cleanup_pid_file EXIT
trap forward_signal INT TERM HUP

UVICORN_ARGS=("${PYTHON_BIN}" -m uvicorn "${UVICORN_APP}" --host "${HOST}" --port "${PORT}")

if [[ "${RELOAD}" != "0" ]]; then
  UVICORN_ARGS+=(--reload)
fi

if [[ -n "${UVICORN_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARGS=( ${UVICORN_EXTRA_ARGS} )
  UVICORN_ARGS+=("${EXTRA_ARGS[@]}")
fi

cd "${BACKEND_DIR}"

echo "Starting backend with: ${UVICORN_ARGS[*]}"
"${UVICORN_ARGS[@]}" &
uvicorn_pid=$!
echo "${uvicorn_pid}" > "${PID_FILE}"
wait "${uvicorn_pid}"
