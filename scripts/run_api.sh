#!/usr/bin/env bash
set -euo pipefail

HOST="${HYDRA_API_HOST:-127.0.0.1}"
PORT="${HYDRA_API_PORT:-8080}"

if [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" ]]; then
  echo "Refusing non-local bind in pre-alpha. Set up an authenticated gateway first." >&2
  exit 2
fi

exec uvicorn hydra.api:app --host "$HOST" --port "$PORT"
