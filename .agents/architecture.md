# Architecture

Five processes, one camera owner.

`realsense2_camera` is the only process that opens the D415. It publishes color on `/camera/camera/color/image_raw` and depth on `/camera/camera/depth/image_rect_raw`. Depth values are millimeters in a 16-bit image. The launch file asks for 640x480 at 15 fps and leaves alignment, the point cloud, and the driver colorizer off.

`franco_detect` subscribes to color with sensor-data QoS, which is what the driver uses. A reliable subscription would not connect. The callback keeps only the newest frame. A worker runs YOLO11n (ONNX, CPU, two threads, 320 px input) and a timer publishes `/franco/detections`. A pass that is still running drops the waiting frame instead of building a queue. Missing weights are not fatal: the node publishes an empty list.

`franco_preview` subscribes to color, depth, and detections. It JPEG-encodes the latest color image with the latest boxes drawn on it, and a colorized copy of the depth image. Flask serves those bytes as MJPEG on `127.0.0.1:8080`. The bind address is forced. A parameter that asks for another interface is ignored and logged. Handlers wait for the next frame. They do not call the camera SDK.

`franco_telemetry` counts color images for one second, reads the latest detection length, reads the latched command, and reads `/sys/module/usbcore/parameters/usbfs_memory_mb`. It publishes one `DiagnosticArray` on `/diagnostics`.

`franco_command` is a placeholder. It copies `/franco/cmd_vel` onto `/franco/command/last` and stores that last message for subscribers that start later. There is no motor, servo, or GPIO call in this process.

The preview and the detector both tolerate a slow partner. The detector does not wait for the page. The page does not wait for a detection with a matching stamp. Boxes can be a frame or two behind the image. That is acceptable for this check.

Shared files live in `/srv/franco/ros2_ws`. The `franco` package source is `/srv/franco/ros2_ws/src/franco`. `realsense-ros` is a sibling checkout, not a copy inside this repository.
