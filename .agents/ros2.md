# ROS 2 interface

ROS 2 Jazzy. Build the four packages under `packages/` and source the workspace install.
Launch with `ros2 launch franco_bringup bench.launch.py` and supply model weights.

| Node | Package | Inputs | Outputs |
| --- | --- | --- | --- |
| camera | external `realsense2_camera` | RealSense device | color, depth, camera info, TF |
| `franco_detect` | `franco_perception` | color | detections, diagnostics |
| `franco_preview` | `franco_tools` | color, depth, detections | HTTP MJPEG |
| `franco_telemetry` | `franco_diagnostics` | color, last command | diagnostics |
| `franco_command` | `franco_tools` | velocity command | last command; no actuation |

Default topics in the root namespace remain `/camera/camera/color/image_raw`,
`/camera/camera/depth/image_rect_raw`, `/franco/detections`, `/diagnostics`,
`/franco/cmd_vel` and `/franco/command/last`. A launch namespace prefixes the graph.
Image remappings follow the camera namespace/name in the profile. Give separate
camera instances unique names (TF frames) and preview ports.

Images use sensor-data QoS. Detection and command input use reliable QoS.
The last-command topic is reliable, transient local, depth 1. Detections use
`vision_msgs/Detection2DArray`: COCO label, score, pixel box and source header;
no tracking ID or estimated 3D pose.

The installed `config/bench.yaml` is the bench profile. Launch arguments:
`config`, `namespace`, `model_path`, `with_camera`, `with_preview`.
`FRANCO_MODEL_PATH` is the default for the model launch argument; a nonempty
argument overrides the profile. Relative profile model paths resolve beside it.
`with_camera:=false with_preview:=false` supports tests without hardware or HTTP.
Node parameters configure startup; restart nodes to apply changes.

Each completed, fresh inference is published once. Missing models and inference
errors produce ERROR diagnostics; expired results produce WARN. The detector owns
`franco_detect` status, while telemetry owns camera, command and USB statuses.
The default result/overlay timeout is 2 seconds and preview is capped at 5 fps per
stream. Unexpected process exit shuts down the graph for systemd to restart it.
