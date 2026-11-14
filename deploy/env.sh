# Shell environment for every franco ROS 2 process.
#
# Source this file. Do not execute it. It loads Jazzy and the workspace
# install prefix. Two extra prefixes are appended only so this machine can run
# before the apt packages are installed: /srv/franco/python-deps holds the
# onnxruntime wheel (and Flask, if apt does not have it yet), and
# /srv/franco/ros-overlay holds an extracted ros-jazzy-vision-msgs package.
# System paths stay in front, so a later apt install wins.

# ROS setup scripts read variables they do not always define.
set +u
source /opt/ros/jazzy/setup.bash
if [ -f /srv/franco/ros2_ws/install/setup.bash ]; then
  source /srv/franco/ros2_ws/install/setup.bash
fi

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
