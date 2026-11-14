# Local preview node.
#
# Subscribes to the color image, the depth image, and /franco/detections.
# It encodes the latest pair to JPEG and serves two MJPEG streams on every
# network interface, so a browser on the same Wi-Fi can open the page. There
# is no account and no tunnel. Nothing on the page writes back to the camera.
#
# Depth is colorized here, not in the driver. Alignment stays off. The two
# pictures are a side by side check, not a fused image.

from __future__ import annotations

import socket
import threading
from io import BytesIO
from pathlib import Path

import numpy as np
import rclpy
from cv_bridge import CvBridge
from flask import Flask, Response, jsonify, render_template
from PIL import Image, ImageDraw
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image as ImageMsg
from vision_msgs.msg import Detection2DArray

from franco.runtime import spin_until_shutdown

_BOUNDARY = "frame"
_LAN = "0.0.0.0"


class PreviewNode(Node):
    """Holds the latest JPEGs and serves them to browsers on the local network.

    The subscriptions update the bytes under a condition. HTTP handlers wait
    on that condition, so a slow browser does not change what the camera does.
    """

    def __init__(self) -> None:
        """Subscribe, encode, and start the page.

        color_topic and depth_topic come from realsense2_camera. host is the
        interface to bind. The default 0.0.0.0 accepts every interface,
        including Wi-Fi. port is the TCP port. jpeg_quality is the encode
        quality from 1 to 95.
        """

        super().__init__("franco_preview")
        self.declare_parameter("color_topic", "/camera/camera/color/image_raw")
        self.declare_parameter("depth_topic", "/camera/camera/depth/image_rect_raw")
        self.declare_parameter("port", 8080)
        self.declare_parameter("jpeg_quality", 75)
        self.declare_parameter("host", _LAN)

        self._host = self.get_parameter("host").get_parameter_value().string_value or _LAN
        self._port = int(self.get_parameter("port").value)
        self._quality = int(self.get_parameter("jpeg_quality").value)
        self._bridge = CvBridge()
        self._condition = threading.Condition()
        self._color_id = 0
        self._depth_id = 0
        self._color_jpeg: bytes | None = None
        self._depth_jpeg: bytes | None = None
        self._boxes: tuple[tuple[int, int, int, int, str, float], ...] = ()
        self._color_count = 0
        self._depth_count = 0

        color_topic = self.get_parameter("color_topic").get_parameter_value().string_value
        depth_topic = self.get_parameter("depth_topic").get_parameter_value().string_value
        self.create_subscription(ImageMsg, color_topic, self._on_color, qos_profile_sensor_data)
        self.create_subscription(ImageMsg, depth_topic, self._on_depth, qos_profile_sensor_data)
        self.create_subscription(Detection2DArray, "/franco/detections", self._on_detections, 10)

        template_folder = str(_template_directory())
        self._app = _build_app(self, template_folder)
        self._http = threading.Thread(target=self._serve, name="franco-preview", daemon=True)
        self._http.start()
        for address in _ipv4_addresses():
            self.get_logger().info("Preview on http://%s:%s" % (address, self._port))

    def wait_jpeg(self, kind: str, previous_id: int, timeout: float) -> tuple[int, bytes | None]:
        """Block until a newer JPEG of the requested kind is ready.

        kind is "color" or "depth". previous_id is the frame id the caller
        already sent. timeout is the wait in seconds. Returns the current
        frame id and the JPEG bytes, or None when nothing new arrived.
        """

        with self._condition:
            self._condition.wait_for(
                lambda: (self._color_id if kind == "color" else self._depth_id) != previous_id,
                timeout=timeout,
            )
            current = self._color_id if kind == "color" else self._depth_id
            if current == previous_id:
                return previous_id, None
            frame = self._color_jpeg if kind == "color" else self._depth_jpeg
            return current, frame

    def status(self) -> dict[str, int]:
        """Return counters for the status page.

        The counts are how many color and depth images this node has encoded
        since it started. They are the quick check that the driver is publishing.
        """

        with self._condition:
            return {
                "color_frames": self._color_count,
                "depth_frames": self._depth_count,
                "detections": len(self._boxes),
                "port": self._port,
            }

    def _on_color(self, msg: ImageMsg) -> None:
        """Encode the color image with the latest boxes drawn on it.

        msg is the driver color image. Boxes come from the detection topic and
        may be a frame or two old. The preview does not wait for a matching
        detection, same as the first prototype.
        """

        rgb = self._bridge.imgmsg_to_cv2(msg, desired_encoding="rgb8")
        with self._condition:
            boxes = self._boxes
        jpeg = _encode_rgb(rgb, self._quality, boxes)
        with self._condition:
            self._color_jpeg = jpeg
            self._color_count += 1
            self._color_id += 1
            self._condition.notify_all()

    def _on_depth(self, msg: ImageMsg) -> None:
        """Colorize the 16-bit depth image and store its JPEG.

        msg is the rectified depth image in millimeters. Zero pixels are
        missing measurements and stay dark. The scale stretches across the
        distances in this frame so the picture stays readable without a fixed
        near and far setting.
        """

        depth = self._bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
        jpeg = _encode_rgb(_colorize_depth(np.asarray(depth)), self._quality)
        with self._condition:
            self._depth_jpeg = jpeg
            self._depth_count += 1
            self._depth_id += 1
            self._condition.notify_all()

    def _on_detections(self, msg: Detection2DArray) -> None:
        """Store the latest boxes in pixel corners for the next color encode.

        msg is the Detection2DArray from franco_detect. The center and size
        fields are converted back to corners because the drawing code uses
        corners. An empty message clears the boxes.
        """

        boxes = tuple(_box_tuple(detection) for detection in msg.detections)
        with self._condition:
            self._boxes = boxes

    def _serve(self) -> None:
        """Run the Flask development server until the process exits.

        The reloader is off so this process is not forked. The thread is a
        daemon: when rclpy shuts down, the process exit closes the port.
        host 0.0.0.0 listens on Wi-Fi as well as on loopback.
        """

        self._app.run(
            host=self._host,
            port=self._port,
            threaded=True,
            use_reloader=False,
        )


def _box_tuple(detection) -> tuple[int, int, int, int, str, float]:
    """Convert one Detection2D into the tuple the drawer expects.

    The return value is x1, y1, x2, y2, label, score. The label is the first
    hypothesis class id. A detection with no hypothesis is labeled "object".
    """

    center = detection.bbox.center.position
    half_x = detection.bbox.size_x / 2.0
    half_y = detection.bbox.size_y / 2.0
    label = "object"
    score = 0.0
    if detection.results:
        label = detection.results[0].hypothesis.class_id or "object"
        score = float(detection.results[0].hypothesis.score)
    return (
        int(center.x - half_x),
        int(center.y - half_y),
        int(center.x + half_x),
        int(center.y + half_y),
        label,
        score,
    )


def _encode_rgb(
    array: np.ndarray,
    quality: int,
    boxes: tuple[tuple[int, int, int, int, str, float], ...] = (),
) -> bytes:
    """Encode an RGB uint8 image as JPEG, drawing boxes when they are present.

    array has shape (height, width, 3). quality is the JPEG quality. boxes
    use original image pixels. Returns the encoded bytes.
    """

    image = Image.fromarray(np.ascontiguousarray(array[:, :, :3]), mode="RGB")
    if boxes:
        draw = ImageDraw.Draw(image)
        for x1, y1, x2, y2, label, score in boxes:
            draw.rectangle((x1, y1, x2, y2), outline=(255, 220, 0), width=2)
            text_y = y1 - 12 if y1 >= 14 else y1 + 2
            draw.text((x1 + 2, text_y), f"{label} {score:.2f}", fill=(255, 220, 0))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _colorize_depth(depth: np.ndarray) -> np.ndarray:
    """Map a uint16 depth image in millimeters to an RGB preview.

    depth is the raw array. Valid pixels are stretched between the 5th and
    95th percentile so a few extreme ranges do not wash the picture out.
    Near values lean red and far values lean blue. Returns uint8 RGB.
    """

    rgb = np.zeros((depth.shape[0], depth.shape[1], 3), dtype=np.uint8)
    valid = depth > 0
    if not np.any(valid):
        return rgb
    samples = depth[valid].astype(np.float32)
    near = float(np.percentile(samples, 5))
    far = float(np.percentile(samples, 95))
    if far <= near:
        far = near + 1.0
    scale = np.clip((depth.astype(np.float32) - near) / (far - near), 0.0, 1.0)
    rgb[..., 0] = np.where(valid, (1.0 - scale) * 255.0, 0).astype(np.uint8)
    rgb[..., 1] = np.where(valid, 40, 0).astype(np.uint8)
    rgb[..., 2] = np.where(valid, scale * 255.0, 0).astype(np.uint8)
    return rgb


def _build_app(node: PreviewNode, template_folder: str) -> Flask:
    """Create the Flask app that reads JPEGs from the preview node.

    node is the running PreviewNode. template_folder is the directory that
    holds index.html. The routes are the page, the two streams, a JSON status,
    and an empty favicon. There is no other route.
    """

    app = Flask(__name__, template_folder=template_folder)

    @app.get("/")
    def index() -> str:
        """Render the page that shows the two streams side by side."""

        return render_template("index.html", port=node.status()["port"])

    @app.get("/stream/color")
    def color_stream() -> Response:
        """Stream the color JPEG as a long-lived MJPEG response."""

        return _mjpeg(node, "color")

    @app.get("/stream/depth")
    def depth_stream() -> Response:
        """Stream the colorized depth JPEG as a long-lived MJPEG response."""

        return _mjpeg(node, "depth")

    @app.get("/status")
    def status() -> Response:
        """Return the frame counters as JSON."""

        return jsonify(node.status())

    @app.get("/favicon.ico")
    def favicon() -> Response:
        """Answer the browser favicon probe with no content."""

        return Response(status=204)

    return app


def _mjpeg(node: PreviewNode, kind: str) -> Response:
    """Build the multipart response for one stream.

    node supplies the JPEGs. kind is "color" or "depth". The response stays
    open and yields a new part each time the matching image is encoded.
    """

    return Response(
        _parts(node, kind),
        mimetype=f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


def _parts(node: PreviewNode, kind: str):
    """Yield one JPEG part per new frame until the client goes away.

    node and kind are the same values _mjpeg received. A timeout with no new
    frame just tries again, so a paused camera does not close the page.
    """

    last_id = -1
    while True:
        frame_id, jpeg = node.wait_jpeg(kind, last_id, timeout=2.0)
        if jpeg is None:
            continue
        last_id = frame_id
        header = (
            f"--{_BOUNDARY}\r\n"
            "Content-Type: image/jpeg\r\n"
            f"Content-Length: {len(jpeg)}\r\n\r\n"
        )
        yield header.encode("ascii") + jpeg + b"\r\n"


def _ipv4_addresses() -> list[str]:
    """Return IPv4 addresses a browser on the LAN can use, plus loopback.

    Loopback is always included so a browser on the Pi still has a URL.
    Addresses that start with 127. are not duplicated. The list can be empty
    of LAN addresses when Wi-Fi is down. The function does not send packets.
    """

    found = ["127.0.0.1"]

    def add(address: str) -> None:
        """Append one LAN address when it is new and not a loopback address."""

        if address and not address.startswith("127.") and address not in found:
            found.append(address)

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except socket.gaierror:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            add(sock.getsockname()[0])
    except OSError:
        pass
    return found


def _template_directory() -> Path:
    """Return the directory that contains the preview HTML template.

    The template ships inside this package so an installed node and a source
    checkout both find it next to this file.
    """

    return Path(__file__).resolve().parent / "templates"


def main() -> None:
    """Start the preview node and spin until the process is asked to stop."""

    rclpy.init()
    spin_until_shutdown(PreviewNode())


if __name__ == "__main__":
    main()
