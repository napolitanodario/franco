# ROS 2 interface

Distribution: ROS 2 Jazzy on Ubuntu 24.04. The workspace overlay is `/srv/franco/ros2_ws/install`. Load it through `deploy/env.sh`, which also sources `/opt/ros/jazzy/setup.bash`.

## Nodes and topics

| Node | Subscribes | Publishes |
| --- | --- | --- |
| `realsense2_camera` |  | `/camera/camera/color/image_raw`, `/camera/camera/depth/image_rect_raw`, camera info, TF |
| `franco_detect` | color image | `/franco/detections` (`vision_msgs/Detection2DArray`) |
| `franco_preview` | color, depth, `/franco/detections` | none (HTTP on `0.0.0.0:8080`) |
| `franco_telemetry` | color, `/franco/detections`, `/franco/command/last` | `/diagnostics` |
| `franco_command` | `/franco/cmd_vel` (`geometry_msgs/Twist`) | `/franco/command/last` |

Image subscriptions use sensor-data QoS (`best effort`, volatile, keep-last). Detection and command input use the default reliable QoS. `/franco/command/last` is reliable, keep-last 1, transient local, so a late subscriber receives the last command.

`Detection2D.results[0].hypothesis.class_id` is the COCO label. `score` is the class confidence. The box center and size are in color-image pixels. `theta` is 0. The detection `id` is empty.

## Launch parameters

`launch/franco.launch.py` passes these to `rs_launch.py`:

- `rgb_camera.color_profile`: `640x480x15`
- `depth_module.depth_profile`: `640x480x15`
- `align_depth.enable`: `false`
- `pointcloud.enable`: `false`
- `colorizer.enable`: `false`

Detection parameters, set on the node if you run it without the launch file:

- `color_topic` (default `/camera/camera/color/image_raw`)
- `model_path` (default `/srv/franco/ros2_ws/src/franco/models/yolo11n.onnx`)
- `input_size` (320), `confidence` (0.45), `iou` (0.45), `max_detections` (20)

Preview parameters: `color_topic`, `depth_topic` (default `/camera/camera/depth/image_rect_raw`), `port` (8080), `jpeg_quality` (75), `host` (default `0.0.0.0`, every interface).

## Adding a node

Put the new package in `/srv/franco/ros2_ws/src` and add a `Node` action to the launch file only if it should start with the graph. A controller that is still experimental can be launched by hand against the same topics.

Publish velocity commands with:

```bash
source /srv/franco/ros2_ws/src/franco/deploy/env.sh
ros2 topic pub --once /franco/cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.1}, angular: {z: 0.0}}"
```

Read health with `ros2 topic echo /diagnostics`.

Do not open the camera with pyrealsense2 in a second process while the driver is running. The preview is already reachable on the local network.
