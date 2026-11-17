# shellcheck shell=bash
# Source from bash or zsh. External bench prefixes remain optional.
_franco_env_setup() {
  local ext=bash prefix
  if [ -n "${ZSH_VERSION:-}" ]; then ext=zsh; fi
  prefix="${FRANCO_ROS_PREFIX:-/opt/ros/jazzy}"
  if [ ! -f "$prefix/setup.$ext" ]; then
    printf 'ROS setup not found: %s\n' "$prefix/setup.$ext" >&2
    return 1
  fi
  # shellcheck disable=SC1090
  source "$prefix/setup.$ext" || return
  prefix="${FRANCO_BASE_INSTALL:-/srv/franco/ros2_ws/install}"
  if [ -f "$prefix/setup.$ext" ]; then
    # shellcheck disable=SC1090
    source "$prefix/setup.$ext" || return
  fi
  prefix="${FRANCO_PYTHON_PREFIX:-/srv/franco/python-deps}"
  if [ -d "$prefix" ] && [[ ":${PYTHONPATH:-}:" != *":$prefix:"* ]]; then
    export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$prefix"
  fi
  prefix="${FRANCO_ROS_OVERLAY:-/srv/franco/ros-overlay/opt/ros/jazzy}"
  if [ -d "$prefix" ]; then
    export AMENT_PREFIX_PATH="${AMENT_PREFIX_PATH:+$AMENT_PREFIX_PATH:}$prefix"
    export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$prefix/lib/python3.12/site-packages"
    export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$prefix/lib"
  fi
  prefix="${FRANCO_INSTALL:-}"
  if [ -n "$prefix" ] && [ -f "$prefix/setup.$ext" ]; then
    # shellcheck disable=SC1090
    source "$prefix/setup.$ext" || return
  fi
}

_franco_had_nounset=false
case $- in *u*) _franco_had_nounset=true ;; esac
set +u
_franco_env_result=0
_franco_env_setup || _franco_env_result=$?
if [ "$_franco_had_nounset" = true ]; then set -u; fi
unset -f _franco_env_setup
unset _franco_had_nounset
if [ "$_franco_env_result" -ne 0 ]; then
  unset _franco_env_result
  return 1
fi
unset _franco_env_result
