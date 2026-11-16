# Architecture

Five processes, one camera owner.

`realsense2_camera` is the only process that opens the D415. It publishes color on `/camera/camera/color/image_raw` and depth on `/camera/camera/depth/image_rect_raw`. Depth values are millimeters in a 16-bit image. The launch file asks for 640x480 at 15 fps and leaves alignment, the point cloud, and the driver colorizer off.

`franco_detect` subscribes with sensor-data QoS, compatible with both best-effort and reliable image publishers. The callback keeps only the newest frame. A worker runs YOLO11n (ONNX, CPU, two threads, 320 px input), and a timer consumes each completed result once. Missing weights and inference failures produce ERROR diagnostics without fabricated empty detections. Results older than `result_timeout` are dropped. NMS preserves different classes unless class-agnostic mode is explicitly enabled.

`franco_preview` subscribes to color, depth, and detections. It JPEG-encodes the latest color image with the latest boxes drawn on it, and a colorized copy of the depth image. Flask serves those bytes as MJPEG on `0.0.0.0:8080`, so browsers on the same Wi-Fi can open the page. Handlers wait for the next frame. They do not call the camera SDK.

`franco_telemetry` counts color images for one second, reads the latched command and the USB buffer size, and publishes its statuses on `/diagnostics`. The detector owns and publishes the `franco_detect` status on that topic.

`franco_command` is a placeholder. It copies `/franco/cmd_vel` onto `/franco/command/last` and stores that last message for subscribers that start later. There is no motor, servo, or GPIO call in this process.

The preview does not wait for matching detection timestamps, but rejects expired boxes and different optical frames. JPEG encoding is capped at `preview_fps` per stream. Unexpected component process exits shut down the launch for systemd to restart; stale data from a live process is reported through diagnostics.

Shared files live in `/srv/franco/ros2_ws`. The `franco` package source is `/srv/franco/ros2_ws/src/franco`. `realsense-ros` is a sibling checkout, not a copy inside this repository.
