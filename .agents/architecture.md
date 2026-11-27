# Architecture

Four ROS packages, six processes, one camera owner.

`franco_perception` owns detection; `franco_diagnostics` owns telemetry and shared health/lifecycle helpers; `franco_tools` owns preview and the command monitor. `franco_bringup` depends on those packages and the external camera driver. The dependency graph has no cycles.

`realsense2_camera` is the only process that opens the D415. It publishes color on `/camera/camera/color/image_raw` and depth on `/camera/camera/depth/image_rect_raw`. Depth values are millimeters in a 16-bit image. The launch file asks for 640x480 at 15 fps and leaves alignment, the point cloud, and the driver colorizer off.

`franco_detect` subscribes with sensor-data QoS, compatible with both best-effort and reliable image publishers. The callback keeps only the newest frame. A worker runs YOLO11n (ONNX, CPU, two threads, 320 px input), and a timer consumes each completed result once. Missing weights and inference failures produce ERROR diagnostics without fabricated empty detections. Results older than `result_timeout` are dropped. NMS preserves different classes unless class-agnostic mode is explicitly enabled.

`franco_obstacle` subscribes only to the rectified depth image. A fixed fractional window counts pixels inside a stop distance, and `std_msgs/Bool` on `/franco/obstacle` is true when enough of those pixels agree. It does not read color or YOLO detections. A window with no valid depth is not published as clear. The node owns the `franco_obstacle` diagnostic.

`franco_preview` subscribes to color, depth, and detections. It JPEG-encodes the latest color image with the latest boxes drawn on it, and a colorized copy of the depth image. Flask serves those bytes as MJPEG on `0.0.0.0:8080`, so browsers on the same Wi-Fi can open the page. Handlers wait for the next frame. They do not call the camera SDK.

`franco_telemetry` counts color images for one second, reads the latched command and the USB buffer size, and publishes its statuses on `/diagnostics`. The detector owns and publishes the `franco_detect` status on that topic.

`franco_command` is a placeholder. It copies `/franco/cmd_vel` onto `/franco/command/last` and stores that last message for subscribers that start later. There is no motor, servo, or GPIO call in this process.

The preview does not wait for matching detection timestamps, but rejects expired boxes and different optical frames. JPEG encoding is capped at `preview_fps` per stream. Unexpected component process exits shut down the launch for systemd to restart; stale data from a live process is reported through diagnostics.

Sources live under `packages/`; each directory is an independent ament_python package. The installed `franco_bringup/config/bench.yaml` and `bench.launch.py` compose the graph. Topic names are relative so namespace isolation works. The external RealSense driver is reused through its vendor launch, without a version change. The Raspberry has not been migrated by this source change.

Hosted CI validates changes; the manual main-only Bench workflow prepares or activates a verified source artifact. Releases freeze the profile and model and use atomic current/previous pointers. See `docs/design.md#deploy` for activation, rollback and one-time setup. No Raspberry deployment has been performed.
