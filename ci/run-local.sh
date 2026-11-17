#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
if ! docker info >/dev/null 2>&1; then
  printf 'Start Docker to run the Franco test suite.\n' >&2
  exit 1
fi

image=$(docker build --quiet -t franco-ci "$root/ci")
docker run --rm --network none \
  -e PYTHONDONTWRITEBYTECODE=1 -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
  -v "$root:/workspace:ro" "$image" bash ci/test.sh
