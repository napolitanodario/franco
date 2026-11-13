"""Background capture of RealSense color and depth frames.

One thread owns the SDK pipeline. It publishes the latest JPEG bytes for each
stream. HTTP handlers only wait for those bytes, so a slow browser cannot
stall the camera and the SDK is never called from the web threads.
"""

from __future__ import annotations

import logging
import threading
import time
from io import BytesIO
from typing import Any

import numpy as np
from PIL import Image

from realsense_web.config import Settings

logger = logging.getLogger(__name__)

# wait_for_frames blocks until the device delivers a matched pair, or until
# this timeout. Stop waits slightly longer than this so the thread can exit.
_FRAME_TIMEOUT_MS = 2000
_STOP_JOIN_SECONDS = 3.0


class RealSenseCamera:
    """Color plus colorized depth from a single RealSense device."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.device_name = "RealSense"
        self.serial_number = ""
        self.usb_type = ""

        # The SDK objects are created in start() so importing this module does
        # not require pyrealsense2 to be built yet.
        self._rs: Any = None
        self._pipeline: Any = None
        self._config: Any = None
        self._colorizer: Any = None
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._running = False
        self._streaming = False

        self._frame_id = 0
        self._frames = 0
        self._color_jpeg: bytes | None = None
        self._depth_jpeg: bytes | None = None
        self._last_error: str | None = None
        self._repeated_error = 0

    def start(self) -> None:
        """Open the first visible RealSense device and start the capture thread."""

        import pyrealsense2 as rs

        self._rs = rs
        # The colorizer turns the 16-bit depth image into an RGB preview.
        # Its default scheme stretches the colors across the distances in view.
        self._pipeline = rs.pipeline()
        self._config = rs.config()
        self._colorizer = rs.colorizer()

        device = self._first_device()
        self.device_name = _device_text(device, rs.camera_info.name, "RealSense")
        self.serial_number = _device_text(device, rs.camera_info.serial_number, "")
        self.usb_type = _device_text(device, rs.camera_info.usb_type_descriptor, "")

        logger.info(
            "Using %s serial %s on USB %s",
            self.device_name,
            self.serial_number or "unknown",
            self.usb_type or "unknown",
        )
        if self.usb_type.startswith("2"):
            logger.warning(
                "The camera enumerated as USB %s. A blue USB 3 port and a USB 3 "
                "cable give the D415 the bandwidth these streams expect.",
                self.usb_type,
            )

        self._config.enable_stream(
            rs.stream.color,
            self.settings.width,
            self.settings.height,
            rs.format.rgb8,
            self.settings.fps,
        )
        self._config.enable_stream(
            rs.stream.depth,
            self.settings.width,
            self.settings.height,
            rs.format.z16,
            self.settings.fps,
        )
        self._pipeline.start(self._config)
        self._streaming = True
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="realsense-capture",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the capture thread and release the device."""

        self._running = False
        with self._condition:
            self._condition.notify_all()

        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=_STOP_JOIN_SECONDS)

        if self._streaming and self._pipeline is not None:
            self._pipeline.stop()
            self._streaming = False

        if thread is not None and thread.is_alive():
            thread.join(timeout=_STOP_JOIN_SECONDS)

    def wait_for_jpeg(
        self,
        kind: str,
        previous_id: int,
        timeout: float,
    ) -> tuple[int, bytes | None]:
        """Block until a new frame is published or the timeout elapses.

        ``kind`` is ``color`` or ``depth``. Returns the current frame id and
        the JPEG bytes. The bytes are None when nothing new arrived.
        """

        if kind not in ("color", "depth"):
            raise ValueError(f"Unknown stream {kind!r}.")

        with self._condition:
            self._condition.wait_for(
                lambda: self._frame_id != previous_id or not self._running,
                timeout=timeout,
            )
            if self._frame_id == previous_id:
                return previous_id, None
            frame = self._color_jpeg if kind == "color" else self._depth_jpeg
            return self._frame_id, frame

    def snapshot(self) -> dict[str, Any]:
        """Return a small status dictionary for the /status page."""

        with self._condition:
            frames = self._frames
            last_error = self._last_error
            running = self._running
        return {
            "device_name": self.device_name,
            "serial_number": self.serial_number,
            "usb_type": self.usb_type,
            "width": self.settings.width,
            "height": self.settings.height,
            "fps": self.settings.fps,
            "frames": frames,
            "running": running,
            "last_error": last_error,
        }

    def _first_device(self) -> Any:
        rs = self._rs
        devices = rs.context().query_devices()
        if len(devices) == 0:
            raise RuntimeError(
                "No RealSense device is visible. Plug the D415 into a USB 3 "
                "port, install the udev rules from .agents/raspberry-pi.md, "
                "and replug the camera."
            )
        if len(devices) > 1:
            logger.info("Found %s RealSense devices. Using the first one.", len(devices))
        return devices[0]

    def _capture_loop(self) -> None:
        while self._running:
            try:
                frames = self._pipeline.wait_for_frames(timeout_ms=_FRAME_TIMEOUT_MS)
                color_frame = frames.get_color_frame()
                depth_frame = frames.get_depth_frame()
                if not color_frame or not depth_frame:
                    continue

                # Encode before the next wait. The numpy views borrow memory
                # owned by these frame objects and are invalid after that.
                color_jpeg = encode_rgb(
                    np.asanyarray(color_frame.get_data()),
                    self.settings.jpeg_quality,
                )
                colorized = self._colorizer.colorize(depth_frame)
                depth_jpeg = encode_rgb(
                    np.asanyarray(colorized.get_data()),
                    self.settings.jpeg_quality,
                )
            except Exception as exc:
                self._note_error(str(exc))
                time.sleep(0.2)
                continue

            with self._condition:
                self._color_jpeg = color_jpeg
                self._depth_jpeg = depth_jpeg
                self._frame_id += 1
                self._frames += 1
                first_frame = self._frames == 1
                self._last_error = None
                self._repeated_error = 0
                self._condition.notify_all()

            if first_frame:
                logger.info("Receiving color and depth frames.")

    def _note_error(self, message: str) -> None:
        with self._condition:
            repeated = message == self._last_error
            self._last_error = message
            self._repeated_error = self._repeated_error + 1 if repeated else 1
            should_log = self._repeated_error == 1 or self._repeated_error % 30 == 0
        if should_log:
            logger.warning("Capture interrupted: %s", message)


def encode_rgb(array: np.ndarray, quality: int) -> bytes:
    """Encode an RGB uint8 image as JPEG."""

    if array.ndim != 3 or array.shape[2] not in (3, 4):
        raise ValueError(f"Expected an RGB frame, got shape {array.shape}.")
    if array.dtype != np.uint8:
        raise ValueError(f"Expected uint8 pixels, got {array.dtype}.")
    if array.shape[2] == 4:
        array = array[:, :, :3]
    if not array.flags["C_CONTIGUOUS"]:
        array = np.ascontiguousarray(array)

    image = Image.fromarray(array, mode="RGB")
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _device_text(device: Any, info: Any, default: str) -> str:
    if device.supports(info):
        return device.get_info(info)
    return default
