# Raspberry Pi 4 setup

This project was prepared on a Raspberry Pi 4 with 8 GB of RAM, Debian 13 (trixie), aarch64, and CPython 3.13.5. The RealSense D415 is not a supported target of the upstream Pi kernel modules. The practical backend on this board is the SDK's userspace libuvc path (`FORCE_LIBUVC`), which talks to the camera through libusb and does not need a patched kernel.

## Python packages

The repository virtual environment is `.venv`, created with the system Python 3.13. Install the web dependencies there:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` lists Flask, NumPy, and Pillow. It does not list `pyrealsense2`.

## Why the SDK is built from source

`pip install pyrealsense2` on this interpreter reports that no distribution matches. Official wheels for aarch64 do not cover CPython 3.13 here. Librealsense 2.59.1 does support building the Python wrapper for 3.13, so the wrapper is compiled against `.venv/bin/python` and installed into that environment.

The Raspberry Pi itself remains outside the SDK's validated platform list. The streams this project uses, color and depth, are the part that commonly works. Treat the build below as the installation method, and confirm it with the import check at the end.

## Build librealsense 2.59.1

Unplug the camera before building. Install the compilers and libraries, then build the tag rather than the moving default branch:

```bash
sudo apt-get update
sudo apt-get install -y git cmake libssl-dev libusb-1.0-0-dev pkg-config python3-dev libudev-dev

mkdir -p "$HOME/src"
git clone --depth 1 --branch v2.59.1 https://github.com/realsenseai/librealsense.git "$HOME/src/librealsense"
cd "$HOME/src/librealsense"
mkdir build && cd build
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DFORCE_LIBUVC=true \
  -DBUILD_EXAMPLES=OFF \
  -DBUILD_GRAPHICAL_EXAMPLES=OFF \
  -DBUILD_PYTHON_BINDINGS=ON \
  -DPYTHON_EXECUTABLE="$HOME/franco/.venv/bin/python"
make -j2
sudo make install
```

`make -j2` is the job count to use on this Pi. The source tree stays in `$HOME/src/librealsense`, outside the project repository. Graphical examples stay off so the build does not need GTK or a desktop OpenGL stack.

If the compiler is killed, the machine ran out of memory. Add swap, then run `make -j2` again in the same `build` directory.

Check that this virtual environment can see the wrapper:

```bash
"$HOME/franco/.venv/bin/python" -c "import pyrealsense2 as rs; print(rs.__file__)"
```

If that import fails after `sudo make install`, find the extension module and note the directory that contains the `pyrealsense2` package:

```bash
find "$HOME/src/librealsense/build" -name 'pyrealsense2*.so'
```

Point `PYTHONPATH` at the directory that contains the package, or copy that package into `.venv/lib/python3.13/site-packages/`. The process that runs `python run.py` has to import `pyrealsense2` with no extra path after the setup is finished.

## udev and the USB port

Copy the SDK permission rules, reload udev, and plug the camera into a blue USB 3 port with a data cable that supports USB 3:

```bash
sudo cp "$HOME/src/librealsense/config/99-realsense-libusb.rules" /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug the camera and plug it back in after the rules are installed. The rules allow a normal user to open the device, so run `python run.py` as that user.

The kernel USB filesystem buffer defaults to a size that is tight for RealSense. Raise it before streaming:

```bash
echo 128 | sudo tee /sys/module/usbcore/parameters/usbfs_memory_mb
```

That value resets on reboot. `run.py` logs a warning when it sees a value below 128. The oneshot `deploy/realsense-usbfs.service` writes 128 on every boot.

## Keep the stream reachable

`deploy/realsense-preview.service` runs the preview as user `dario`, listens on `0.0.0.0:8080`, and starts again at boot. `Restart=always` also brings it back after a crash or a USB dropout. There is no start-rate limit, so the unit keeps retrying while `pyrealsense2` is still missing. The gap between tries is 20 seconds.

Install both units once:

```bash
sudo cp "$HOME/franco/deploy/realsense-usbfs.service" /etc/systemd/system/
sudo cp "$HOME/franco/deploy/realsense-preview.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now realsense-usbfs.service realsense-preview.service
```

The browser asks for HTTP Basic Auth before the page or either stream. The default user and password are both `franco`. Set `STREAM_USERNAME` and `STREAM_PASSWORD` on the service to change them. On this Pi the Wi-Fi address is the one to give out. The host firewall here accepts inbound TCP, so port 8080 does not need an extra rule.

Until `import pyrealsense2` works, the unit stays in `activating (auto-restart)` and nothing listens on 8080. After `sudo make install` puts the wrapper on the virtualenv path, the next retry opens the port by itself. Follow it with:

```bash
systemctl status realsense-preview.service
journalctl -u realsense-preview.service -f
```

`Active: active (running)` and a log line `Open http://...:8080` mean the page is up. `/status` then reports `running`, a rising `frames` count, and `last_error` set to null.

`sudo systemctl stop realsense-preview.service` keeps it stopped until the next start or boot. `sudo systemctl restart realsense-preview.service` picks up code changes.

## Watch the stream from a terminal

A foreground run uses the same program the service runs:

```bash
cd "$HOME/franco"
source .venv/bin/activate
python run.py
```

Stop that process before starting the service, because both would open the camera. The page shows color and colorized depth. `/status` returns JSON, including `frames` and `last_error`.

A refused stream mode fails at startup and the process exits with a traceback from the SDK. The default 640x480 at 15 fps is a mode the D415 publishes for both sensors. A USB 2 enumeration is logged as a warning. The preview can still run at the default size. Larger sizes want the USB 3 port.

An empty page with `frames` stuck at 0 means the pipeline started and no pair has been published yet. Read `last_error` in `/status` and the warnings in the terminal. A permissions problem usually shows up earlier, as no visible device.
