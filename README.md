# RealSense D415 preview

This project reads color and depth from an Intel RealSense D415 and serves both images on a small web page. It is meant to run on a Raspberry Pi 4, with the page opened from another device on the same Wi-Fi network.

The page is a local preview. One process captures frames and each browser on the LAN watches the latest JPEG.

## Run

From this directory, with the virtual environment activated and `pyrealsense2` built for it:

```bash
source .venv/bin/activate
python run.py
```

Then open `http://<pi-address>:8080`. The process prints the address it detected. Stop it with Ctrl+C.

Useful overrides, all optional:

```bash
python run.py --port 8080 --width 640 --height 480 --fps 15 --jpeg-quality 75
```

`/stream/color` and `/stream/depth` are the MJPEG streams. `/status` is a JSON snapshot of the capture thread.

## Always on

`deploy/realsense-preview.service` is the systemd unit that keeps the page on port 8080 across reboots and crashes. `deploy/realsense-usbfs.service` raises the USB buffer the camera needs. Install steps and the status checks are in `.agents/raspberry-pi.md`. Every route asks for HTTP Basic Auth. The default user and password are both `franco`. Override them with `STREAM_USERNAME` and `STREAM_PASSWORD`. The process serves the preview, the two streams, and `/status`. It has no shell and no file access.

## Layout

```text
run.py                         Process entry point
realsense_web/config.py        Command line settings
realsense_web/camera.py        RealSense capture thread
realsense_web/server.py        HTTP page and streams
realsense_web/templates/       Preview page
.agents/                       Design notes and the Pi setup
```

## Setup on this Pi

Python dependencies for the web server live in `.venv`. The RealSense SDK does not. PyPI has no `pyrealsense2` build for CPython 3.13 on aarch64, so the wrapper is compiled from librealsense into this same virtual environment.

The build, udev rules, and USB notes are in `.agents/raspberry-pi.md`. How the threads and the page fit together is in `.agents/architecture.md`.
