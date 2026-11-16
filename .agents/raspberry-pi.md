# Raspberry Pi 4

Observed bench setup before the monorepo migration. The new source layout has not been deployed. The paths and runner workflow below describe that existing installation.

This machine is a Raspberry Pi 4, 8 GB, Ubuntu 24.04 aarch64, ROS 2 Jazzy. librealsense is installed under `/usr/local` with the userspace USB backend, so the stock kernel is enough. The D415 must use a USB 3 port and a USB 3 cable.

Two login accounts matter. `dario` is the administrator and the only member of `sudo`. `franco` is the account for collaborators and for the deploy runner. It is not in `sudo`. Both are in the `dev` group. The shared tree is `/srv/franco`, group `dev`, setgid.

## Paths

- Workspace: `/srv/franco/ros2_ws`
- Repository checkout: `/srv/franco/ros2_ws/src/franco`
- RealSense ROS driver: `/srv/franco/ros2_ws/src/realsense-ros`
- Actions runner: `/srv/franco/actions-runner`
- Python prefix for `onnxruntime`: `/srv/franco/python-deps`
- YOLO weights: `/srv/franco/ros2_ws/src/franco/models/yolo11n.onnx`

Place the weights file by hand. It is listed in `.gitignore`. Without it, the detector reports ERROR on `/diagnostics` and publishes no detection results.

## Packages

Installed for every user: ROS 2 Jazzy under `/opt/ros/jazzy`, `cv_bridge`, `diagnostic_msgs`, `ros-jazzy-vision-msgs`, `python3-numpy`, `python3-pil`, `python3-flask`, `python3-pip`, and librealsense including `pyrealsense2` for the system Python 3.12.

`onnxruntime` has no Ubuntu 24.04 package for this board. The wheel is in `/srv/franco/python-deps`. That wheel also ships NumPy 2, which is not kept in the prefix: the system NumPy is 1.26, and `cv_bridge` was built against it. `deploy/env.sh` appends the prefix after the system paths.

`/srv/franco/ros-overlay` holds an extracted `ros-jazzy-vision-msgs`. `deploy/env.sh` appends it after the system paths, so the apt package is the one that loads.

## USB buffer

`realsense-usbfs.service` is enabled. It is a system oneshot that writes 128 to `/sys/module/usbcore/parameters/usbfs_memory_mb` at boot, because the kernel value resets on reboot. The telemetry node reports that value on `/diagnostics`.

## User services

Linger is enabled for `franco`, so user services start at boot without a logged-in session. The graph unit is `franco.service`. Logs: `journalctl --user -u franco.service -f`.

The preview listens on `0.0.0.0:8080`. From a device on the same Wi-Fi, open `http://<pi-address>:8080`. On the Pi, `http://127.0.0.1:8080` still works.

## GitHub Actions runner

The runner is registered in `/srv/franco/actions-runner` with the label `franco`, and `franco-runner.service` runs it as `franco`. A push to `main` runs `.github/workflows/deploy.yml` on this machine: stop the graph, fast-forward the shared clone, remove `build/franco` and `install/franco`, `colcon build --packages-select franco`, start the graph. The job does not restart the runner.

No GitHub password is stored for `dario`. The runner keeps its own credential files in `/srv/franco/actions-runner`. The repository is public, so `git fetch` does not need a personal access token.
