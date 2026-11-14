# Shell environment for every franco ROS 2 process.
#
# Source this file. Do not execute it. It loads Jazzy and the workspace
# install prefix, then appends two shared prefixes after the system paths.
# /srv/franco/python-deps holds the onnxruntime wheel. /srv/franco/ros-overlay
# holds an extracted ros-jazzy-vision-msgs package. System paths stay in front,
# so the apt packages are the ones that load.

# ROS setup scripts read variables they do not always define.
# setup.bash uses BASH_SOURCE. Under zsh that variable is empty, so the
# script looks for setup.sh in the current directory and fails. Pick the
# file that matches the shell that is sourcing this one. systemd runs bash.
set +u
if [ -n "${ZSH_VERSION:-}" ]; then
  _franco_setup_ext=zsh
else
  _franco_setup_ext=bash
fi
source "/opt/ros/jazzy/setup.${_franco_setup_ext}"
if [ -f "/srv/franco/ros2_ws/install/setup.${_franco_setup_ext}" ]; then
  source "/srv/franco/ros2_ws/install/setup.${_franco_setup_ext}"
fi
unset _franco_setup_ext

_franco_append_python() {
  # Append a directory to PYTHONPATH when it exists and is not already listed.
  # The argument is the directory. A missing directory is ignored. Appending
  # keeps packages already installed by apt ahead of these extras.
  if [ -d "$1" ] && [[ ":${PYTHONPATH:-}:" != *":$1:"* ]]; then
    export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$1"
  fi
}

_franco_append_python /srv/franco/python-deps

_franco_append_library() {
  # Append a directory to LD_LIBRARY_PATH so an extracted ROS package can load
  # its .so files. The argument is the directory. System libraries stay first
  # because this appends. A missing directory is ignored.
  if [ -d "$1" ] && [[ ":${LD_LIBRARY_PATH:-}:" != *":$1:"* ]]; then
    export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$1"
  fi
}

_overlay=/srv/franco/ros-overlay/opt/ros/jazzy
if [ -d "$_overlay" ]; then
  if [[ ":${AMENT_PREFIX_PATH:-}:" != *":$_overlay:"* ]]; then
    export AMENT_PREFIX_PATH="${AMENT_PREFIX_PATH:+$AMENT_PREFIX_PATH:}$_overlay"
  fi
  _franco_append_python "$_overlay/lib/python3.12/site-packages"
  _franco_append_library "$_overlay/lib"
fi
unset _overlay
