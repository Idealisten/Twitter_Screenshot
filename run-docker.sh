#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE_NAME="${IMAGE_NAME:-twitter-screenshot}"
CONTAINER_NAME="${CONTAINER_NAME:-twitter-screenshot}"
HOST_BIND="${HOST_BIND:-127.0.0.1}"
CONTAINER_PORT="${CONTAINER_PORT:-8000}"
RESTART_POLICY="${RESTART_POLICY:-unless-stopped}"
START_PORT="${HOST_PORT:-${PORT:-8000}}"
MAX_PORT="${MAX_PORT:-}"

if [[ -z "$MAX_PORT" ]]; then
  MAX_PORT=$((START_PORT + 50))
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found." >&2
  exit 1
fi

if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  existing_port="$(
    docker port "$CONTAINER_NAME" "${CONTAINER_PORT}/tcp" 2>/dev/null \
      | awk -F: 'NR == 1 {print $NF}' \
      || true
  )"
  if [[ -z "${HOST_PORT:-}" && "$existing_port" =~ ^[0-9]+$ ]]; then
    START_PORT="$existing_port"
    if (( MAX_PORT < START_PORT )); then
      MAX_PORT=$((START_PORT + 50))
    fi
  fi
  echo "Removing existing container: $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

echo "Starting $CONTAINER_NAME from image $IMAGE_NAME"
echo "Trying host ports ${HOST_BIND}:${START_PORT}-${MAX_PORT} -> container :${CONTAINER_PORT}"

for ((port = START_PORT; port <= MAX_PORT; port += 1)); do
  set +e
  output="$(
    docker run -d \
      --name "$CONTAINER_NAME" \
      -p "${HOST_BIND}:${port}:${CONTAINER_PORT}" \
      --restart "$RESTART_POLICY" \
      "$IMAGE_NAME" 2>&1
  )"
  status=$?
  set -e

  if [[ $status -eq 0 ]]; then
    echo "$output"
    echo
    echo "Started successfully:"
    echo "  container: $CONTAINER_NAME"
    echo "  image:     $IMAGE_NAME"
    echo "  local URL: http://${HOST_BIND}:${port}"
    echo
    echo "If you use Cloudflare Tunnel, set service to:"
    echo "  http://${HOST_BIND}:${port}"
    exit 0
  fi

  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

  if echo "$output" | grep -Eqi "port is already allocated|bind: address already in use|Ports are not available|port.*already in use|Bind for .* failed"; then
    echo "Port ${HOST_BIND}:${port} is busy, trying next port..."
    continue
  fi

  echo "$output" >&2
  exit "$status"
done

echo "No available port found in range ${START_PORT}-${MAX_PORT}." >&2
exit 1
