#!/usr/bin/env bash
set -euo pipefail
shellcheck scripts/franco deploy/run-graph.sh deploy/env.sh ci/*.sh .githooks/pre-push
export FRANCO_WORKSPACE=/tmp/franco-ci
./scripts/franco build
./scripts/franco test
