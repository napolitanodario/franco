# Architecture

The program is one process with two jobs: read the camera, and hand the latest images to browsers on the LAN.

## Capture

`RealSenseCamera` in `realsense_web/camera.py` opens the first device returned by the SDK. It enables two streams:

- color, RGB8, default 640x480 at 15 fps
- depth, Z16, the same size and rate

`wait_for_frames` delivers a matched color and depth pair. Depth pixels stay 16-bit in the SDK. The SDK colorizer converts that frame to an RGB picture before this program encodes it. The color scale follows the distances currently in view, which is what makes a live preview readable without a fixed near and far setting.

The capture thread encodes both images to JPEG immediately. The numpy arrays returned by the SDK borrow frame memory, so they are not stored. The thread keeps only the JPEG bytes, under a condition variable. Each new pair wakes every waiting HTTP handler.

Geometric alignment of depth onto the color sensor is left off. On a Pi 4 that step is a large share of the CPU budget, and this preview only needs the two images side by side.

## HTTP

`realsense_web/server.py` is a Flask app served by the Flask development server. That server is enough for a couple of browsers on a trusted Wi-Fi network. It listens on `0.0.0.0` and port `8080` unless the command line says otherwise.

| Path | Response |
| --- | --- |
| `/` | HTML page with the two previews |
| `/stream/color` | MJPEG color stream |
| `/stream/depth` | MJPEG colorized depth stream |
| `/status` | JSON: device, frame count, last capture error |

An MJPEG response is a long-lived `multipart/x-mixed-replace` body. The browser paints each JPEG part into the `img` element. Handlers block on the capture condition, so they send a part when a new frame exists and they do not poll the camera.

JPEG encoding happens once per frame pair. Extra browsers read the same bytes. The expensive work does not grow with the number of viewers. The Pi still spends CPU on the SDK and on two JPEG encodes at the chosen frame rate.

`--jpeg-quality` defaults to 75. Higher values cost more CPU and more Wi-Fi bandwidth for a modest gain on a 640x480 image.

## Defaults for a Pi 4 with 8 GB

640x480 at 15 fps is a mode the D415 accepts on both sensors, including when the camera falls back to USB 2. It is also small enough that capture, colorization, and two JPEG encodes can share the Pi with the desktop and the browser that might be open on the Pi itself.

Raise `--fps` toward 30, or the resolution toward 848x480 or 1280x720, only after the default stream is stable. USB 3 is the right port for those larger modes. `/status` and the process log are the place to see a mode the device refused: the SDK raises during `pipeline.start` and the process exits.

## Object detection

`realsense_web/detector.py` runs YOLO11n on a copy of the latest color frame. The weights are `models/yolo11n.onnx`, input 320 pixels, on two CPU threads. The worker keeps one waiting frame and the last finished list of boxes. The capture thread draws those boxes onto the color JPEG and does not wait for the next pass. Depth is unchanged.

`YOLO_MODEL`, `YOLO_IMGSZ`, and `YOLO_CONFIDENCE` override the model path, the input size, and the score cutoff. `/status` includes `detections`, the number of boxes from the last finished pass.

## What this project leaves out

There is no recording, no point cloud, and no camera control panel. `before_request` in `server.py` requires HTTP Basic Auth on every route, including the streams and `/status`. The default user and password are both `franco`. `STREAM_USERNAME` and `STREAM_PASSWORD` replace them. A failed check returns 401 and does not call the camera. The process does not expose a shell, a filesystem, or an admin API.
