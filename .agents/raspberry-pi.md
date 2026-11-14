# Raspberry Pi 4

This machine is a Raspberry Pi 4, 8 GB, Ubuntu 24.04 aarch64, ROS 2 Jazzy. librealsense is installed under `/usr/local` with the userspace USB backend, so the stock kernel is enough. The D415 must use a USB 3 port and a USB 3 cable.

Two login accounts matter. `dario` is the administrator and the only member of `sudo`. `franco` is the account for collaborators and for the deploy runner. It is not in `sudo`. Both are in the `dev` group. The shared tree is `/srv/franco`, group `dev`, setgid.

## Paths

- Workspace: `/srv/franco/ros2_ws`
- This package: `/srv/franco/ros2_ws/src/franco`
- RealSense ROS driver: `/srv/franco/ros2_ws/src/realsense-ros`
- Actions runner: `/srv/franco/actions-runner`
- Optional pip prefix: `/srv/franco/python-deps`
- YOLO weights: `/srv/franco/ros2_ws/src/franco/models/yolo11n.onnx`

Place the weights file by hand. It is listed in `.gitignore`. The detection node starts without it and publishes no boxes.

## Packages

These are already available to every user because they are installed on the system: ROS 2 Jazzy under `/opt/ros/jazzy`, `cv_bridge`, `diagnostic_msgs`, `python3-numpy`, `python3-pil`, and librealsense including `pyrealsense2` for the system Python 3.12.

Install the remaining apt packages once, as `dario`. `sudo` asks for the `dario` password, so this step is not done by the deploy job:

```bash
sudo apt update
sudo apt install -y ros-jazzy-vision-msgs python3-flask python3-pip
```

Until that apt install happens, two shared prefixes stand in for it. `/srv/franco/ros-overlay` is an extracted `ros-jazzy-vision-msgs` package. `/srv/franco/python-deps` holds Flask and `onnxruntime` from pip. `deploy/env.sh` appends both, after the system paths, so the apt packages take over when they are installed.

`onnxruntime` has no Ubuntu 24.04 package for this board. Refresh the wheel with:

```bash
pip3 install --target /srv/franco/python-deps -r /srv/franco/ros2_ws/src/franco/requirements.txt
rm -rf /srv/franco/python-deps/numpy /srv/franco/python-deps/numpy.libs /srv/franco/python-deps/numpy-*.dist-info
```

The wheel pulls in NumPy 2. The system NumPy is 1.26, and `cv_bridge` was built against that. Leaving the bundled NumPy in the prefix makes `import cv2` fail, so the install removes it and the system NumPy stays in use.

Build:

```bash
source /srv/franco/ros2_ws/src/franco/deploy/env.sh
cd /srv/franco/ros2_ws
colcon build --packages-select franco --cmake-args -DCMAKE_BUILD_TYPE=Release
```

## USB buffer

The kernel USB buffer resets on reboot. Install the oneshot as `dario`:

```bash
sudo cp /srv/franco/ros2_ws/src/franco/deploy/realsense-usbfs.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now realsense-usbfs.service
```

Check with `cat /sys/module/usbcore/parameters/usbfs_memory_mb`. The value should be 128. The telemetry node reports it on `/diagnostics`.

## User services

Linger lets `franco` run user services at boot without a logged-in session. As `dario`:

```bash
sudo loginctl enable-linger franco
```

As `franco`, install the graph unit:

```bash
mkdir -p ~/.config/systemd/user
cp /srv/franco/ros2_ws/src/franco/deploy/franco.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now franco.service
```

Logs: `journalctl --user -u franco.service -f`.

The preview listens on `127.0.0.1:8080` only. From a laptop, use `ssh -L 8080:127.0.0.1:8080 franco@<pi>` and open `http://127.0.0.1:8080` on the laptop.

## GitHub Actions runner

The runner binary is unpacked in `/srv/franco/actions-runner`. Registration uses a one-time token from the repository settings page (Actions, Runners, New self-hosted runner). Run the script as `franco`, not as `dario`:

```bash
/srv/franco/ros2_ws/src/franco/deploy/register-runner.sh '<token>'
```

The script configures the runner with the label `franco`, copies the user units, and starts `franco-runner.service`. A push to `main` then runs `.github/workflows/deploy.yml` on this machine: stop the graph, fast-forward the shared clone, `colcon build --packages-select franco`, start the graph. The job does not restart the runner.

No GitHub password is stored for `dario`. The runner keeps its own credential files in `/srv/franco/actions-runner`. The repository is public, so `git fetch` does not need a personal access token.
