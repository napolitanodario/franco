#!/bin/bash
# Enter the immutable release selected by the user service.

set -eu
franco_deploy_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$franco_deploy_dir/../scripts/franco_cli.py" run-release "$franco_deploy_dir/../.."
