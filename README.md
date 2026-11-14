# franco

Starting ROS 2 graph for an Intel RealSense D415 on a Raspberry Pi 4. The camera driver is the existing `realsense2_camera` package. This repository adds four nodes: YOLO11n detection, a preview on the local network, diagnostics, and a command placeholder that does not drive any hardware.

The preview listens on port 8080 on every interface. A phone or laptop on the same Wi-Fi opens `http://<pi-address>:8080`. It is not exposed through a tunnel.

## Layout

```text
franco/                  Python nodes
launch/franco.launch.py  Starts the driver and the four nodes
deploy/                  systemd units and the runner registration script
docs/design.md           Why the graph is shaped this way
.agents/                 Notes for this machine and for the ROS graph
models/yolo11n.onnx      Weights, not committed
```

## Run

From a shell that can see the workspace:

```bash
source /srv/franco/ros2_ws/src/franco/deploy/env.sh
ros2 launch franco franco.launch.py
```

On the Pi itself, open `http://127.0.0.1:8080`. From another device on the Wi-Fi, open `http://<pi-address>:8080`. The launch log prints the addresses it detected.

Stop the launch with Ctrl+C. One graph at a time: a second launch cannot open the camera.

## Topics

| Topic | Type | Role |
| --- | --- | --- |
| `/camera/camera/color/image_raw` | `sensor_msgs/Image` | Color from the driver |
| `/camera/camera/depth/image_rect_raw` | `sensor_msgs/Image` | Depth in millimeters |
| `/franco/detections` | `vision_msgs/Detection2DArray` | YOLO11n boxes |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | Camera rate, detection count, last command, USB buffer |
| `/franco/cmd_vel` | `geometry_msgs/Twist` | Command input, not connected to motors |
| `/franco/command/last` | `geometry_msgs/Twist` | Last command, latched |

## Service

`deploy/franco.service` is a user unit for the `franco` account. Install steps, the USB buffer unit, and the self-hosted runner are in `.agents/raspberry-pi.md`. The design notes are in `docs/design.md`.
