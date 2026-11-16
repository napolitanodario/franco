# Design hypothesis

This is the first shape of the franco graph, not a finished robot. The point is a small set of processes with stable topic names, so later work adds a node instead of rewriting a single program.

## What the previous prototype was

The previous tree was one Python process. A thread read the D415 through pyrealsense2, another thread ran YOLO11n, and Flask served color and depth MJPEG on `0.0.0.0:8080`, including through a Cloudflare tunnel. That was enough to see the camera. It was a poor base: the detector could not be restarted alone, a second consumer had to scrape HTTP, and the page was reachable beyond the machine.

## What this graph is

The camera device is owned by `realsense2_camera`, the standard ROS 2 driver, already built in `/srv/franco/ros2_ws`. This package does not open the device.

Four nodes sit on the driver's topics:

- `franco_detect` subscribes to color and publishes `vision_msgs/Detection2DArray` on `/franco/detections`. The class id is the COCO name string. That is a shortcut. A later metadata step can replace it with a stable id. Boxes are not tracked across frames, so the detection id field is empty. There is no 6D pose.
- `franco_preview` subscribes to color, depth, and detections. It draws the latest boxes and serves MJPEG on every interface, port 8080, so a browser on the same Wi-Fi can watch. Depth is colorized in this node from the 16-bit image. Alignment stays off because it costs more CPU than this check needs. There is no Cloudflare tunnel and no password on the page.
- `franco_telemetry` publishes camera rate, last command and USB buffer status on `/diagnostics` once a second. The detector independently publishes `franco_detect` on the same topic, including model/inference errors and result freshness.
- `franco_command` subscribes to `/franco/cmd_vel` and republishes the last `geometry_msgs/Twist` on `/franco/command/last` with transient local durability. It does not actuate anything.

Profiles are 640x480 at 15 fps for both streams. The point cloud, the colorizer inside the driver, and the IMU streams are off. The D415 used here has no IMU.

## What is deliberately missing

No navigation stack, no SLAM, no map, no motor driver, no joystick node, no recording, no cloud upload, and no account on the preview. Those can be separate packages that subscribe to the topics above. A base driver should subscribe to `/franco/cmd_vel`. A teleop node should publish that same topic. Neither belongs in this package until the hardware exists.

The YOLO weights are a file on disk, `models/yolo11n.onnx`. The repository does not contain the binary. Missing weights produce an ERROR diagnostic, not empty detections. A valid empty list means inference completed with no objects. Each fresh result is published once; the source timestamp is preserved. NMS is class-aware by default.

The initial freshness timeout is 2 seconds, configurable on detection and preview. This is a bench default, not a navigation latency requirement. The preview encodes at most 5 fps per stream and omits expired or wrong-frame boxes. On any unexpected component process exit, the launch shuts down the graph so systemd can restart it. Data silence is diagnosed rather than automatically restarting a still-running process.

## How a new node should join

Subscribe or publish the topics in the table in the README. Do not open the RealSense device from a second process. Prefer `/diagnostics` for health, and add a `DiagnosticStatus` name rather than a one-off topic, unless the data is something a controller must act on.

## Deploy

The Pi is reached over Tailscale. GitHub-hosted runners are not on that network, so deploy runs as a self-hosted runner under the `franco` user. A push to `main` updates `/srv/franco/ros2_ws/src/franco`, builds the package, and restarts the user service. The runner credentials are the runner's own, not a login of the GitHub account that owns the repository.
