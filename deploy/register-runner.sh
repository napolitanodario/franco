#!/bin/bash
# Register the self-hosted GitHub Actions runner and install its user service.
#
# Run this as the franco user. The only argument is the one-time registration
# token from the repository page Settings, Actions, Runners, New self-hosted
# runner. The token is not stored in this repository. After registration the
# runner keeps its own credentials in /srv/franco/actions-runner.
#
# Usage: ./deploy/register-runner.sh <registration-token>

set -eu

if [ "$(id -un)" != "franco" ]; then
  echo "Run this as the franco user, not as $(id -un)." >&2
  exit 1
fi

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  echo "Usage: $0 <registration-token>" >&2
  exit 1
fi

runner_dir=/srv/franco/actions-runner
if [ ! -x "$runner_dir/config.sh" ]; then
  echo "The runner is not unpacked in $runner_dir." >&2
  exit 1
fi

"$runner_dir/config.sh" \
  --unattended \
  --url https://github.com/napolitanodario/franco \
  --token "$1" \
  --name raspberrypi-franco \
  --labels franco \
  --replace \
  --work "$runner_dir/_work"

unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir"
cp /srv/franco/ros2_ws/src/franco/deploy/franco-runner.service "$unit_dir/franco-runner.service"
cp /srv/franco/ros2_ws/src/franco/deploy/franco.service "$unit_dir/franco.service"
systemctl --user daemon-reload
systemctl --user enable --now franco-runner.service
echo "Runner service is enabled. Enable linger with: sudo loginctl enable-linger franco"
