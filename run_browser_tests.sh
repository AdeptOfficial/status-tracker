#!/usr/bin/env bash
# Uses only synthetic data; no app .env or live data volumes are mounted.
set -euo pipefail
cd "$(dirname "$0")"
repo=$(pwd)
name="status-tracker-browser-$$"
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
# Build test image first with ./run_tests.sh. Install browser dependencies via npm ci.
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
docker run -d --rm --name "$name" -p "127.0.0.1:$port:8000" --tmpfs /tmp \
  -v "$repo/app:/app/app:ro" -v "$repo/tests/browser:/fixture:ro" \
  -e DATABASE_URL=sqlite:////tmp/browser-test.db -e ENABLE_SHOKO=false \
  -e ENABLE_TIMEOUT_CHECKER=false -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 \
  -w /fixture status-tracker-test:latest uvicorn fixture:app --host 0.0.0.0 --port 8000 >/dev/null
port=$(docker port "$name" 8000/tcp | cut -d: -f2)
for attempt in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$port/api/sse/status" >/dev/null 2>&1; then break; fi
  sleep .25
done
TEST_CONTAINER="$name" TEST_ORIGIN="http://127.0.0.1:$port" node tests/browser/check.mjs
