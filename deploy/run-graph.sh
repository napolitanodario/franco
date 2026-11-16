#!/bin/bash
# Start the franco launch file with the ROS 2 environment loaded.
#
# systemd calls this script. A login shell is not required. The script does
# not return: exec replaces it with the launch process so systemd tracks the
# real PID and a stop signal reaches the nodes.

set -eu
franco_deploy_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$franco_deploy_dir/env.sh"
exec ros2 launch franco_bringup bench.launch.py "$@"
