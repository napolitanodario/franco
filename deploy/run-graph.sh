#!/bin/bash
# Start the franco launch file with the ROS 2 environment loaded.
#
# systemd calls this script. A login shell is not required. The script does
# not return: exec replaces it with the launch process so systemd tracks the
# real PID and a stop signal reaches the nodes.

set -eu
# shellcheck disable=SC1091
source /srv/franco/ros2_ws/src/franco/deploy/env.sh
exec ros2 launch franco franco.launch.py
