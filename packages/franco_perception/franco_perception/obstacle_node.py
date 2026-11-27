# Obstacle node.
#
# Subscribes to the rectified depth image from realsense2_camera and publishes
# std_msgs/Bool on franco/obstacle. True means the depth window in front of
# the camera has enough pixels inside the stop distance. The check does not
# read the color image and does not read /franco/detections. The bench leaves
# align_depth off, so the window is in the depth image, not the color image.
#
# A frame with no valid depth in the window is not reported as clear. The
# Bool is withheld and franco_obstacle on /diagnostics says the window is
# empty. The Bool has no header; the source stamp is used only to drop a
# stale frame and to age the diagnostic.

from __future__ import annotations

import math
import threading

import numpy as np
import rclpy
from cv_bridge import CvBridge
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import Bool

from franco_diagnostics.health import is_fresh
from franco_diagnostics.runtime import spin_until_shutdown
from franco_perception.obstacle import ObstacleHealth, parse_roi, read_obstacle


class ObstacleNode(Node):
    """Publish a near-field obstacle flag from one depth image.

    The callback measures the newest frame and publishes immediately. The
    work is a windowed minimum, so there is no worker thread and no queue.
    """

    def __init__(self, **kwargs) -> None:
        """Declare the depth window and subscribe to the rectified depth topic.

        depth_topic is the uint16 image in millimeters. The launch remaps the
        default name onto the camera identity in the bench profile. stop,
        min, and max are millimeters. The ROI edges are fractions of the
        image. min_pixels is how many near pixels make the window blocked.
        """

        super().__init__("franco_obstacle", **kwargs)
        self.declare_parameter("depth_topic", "camera/camera/depth/image_rect_raw")
        self.declare_parameter("stop_distance_mm", 800)
        self.declare_parameter("min_valid_mm", 100)
        self.declare_parameter("max_valid_mm", 4000)
        self.declare_parameter("min_pixels", 50)
        self.declare_parameter("roi_top", 0.35)
        self.declare_parameter("roi_bottom", 0.95)
        self.declare_parameter("roi_left", 0.25)
        self.declare_parameter("roi_right", 0.75)
        self.declare_parameter("result_timeout", 2.0)

        self._timeout = float(self.get_parameter("result_timeout").value)
        if not math.isfinite(self._timeout) or self._timeout <= 0:
            raise ValueError("result_timeout must be finite and positive.")
        self._stop_mm = _positive_int(self, "stop_distance_mm")
        self._min_mm = _positive_int(self, "min_valid_mm")
        self._max_mm = _positive_int(self, "max_valid_mm")
        self._min_pixels = _positive_int(self, "min_pixels")
        if not (self._min_mm <= self._stop_mm <= self._max_mm):
            raise ValueError("Depth limits must satisfy min_valid_mm <= stop_distance_mm <= max_valid_mm.")
        self._roi = parse_roi(
            self.get_parameter("roi_top").value,
            self.get_parameter("roi_bottom").value,
            self.get_parameter("roi_left").value,
            self.get_parameter("roi_right").value,
        )

        self._bridge = CvBridge()
        self._lock = threading.Lock()
        self._health = ObstacleHealth(stop_mm=self._stop_mm)
        self._blocked: bool | None = None

        depth_topic = self.get_parameter("depth_topic").get_parameter_value().string_value
        self._publisher = self.create_publisher(Bool, "franco/obstacle", 10)
        self._status_publisher = self.create_publisher(DiagnosticArray, "diagnostics", 10)
        # Best effort accepts both best-effort and reliable image publishers.
        self.create_subscription(Image, depth_topic, self._on_depth, qos_profile_sensor_data)
        self.create_timer(1.0, self._publish_status)
        self.get_logger().info(
            "Obstacle check listening on %s; stop distance %s mm." % (depth_topic, self._stop_mm)
        )

    def _on_depth(self, msg: Image) -> None:
        """Measure one depth frame and publish the flag when the window is valid.

        msg is the rectified depth image. A stamp older than result_timeout,
        or a stamp in the future, is ignored. An empty window updates the
        diagnostic and does not publish a Bool.
        """

        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        now = self.get_clock().now().nanoseconds / 1e9
        if not is_fresh(stamp, now, self._timeout):
            return
        try:
            depth = np.asarray(self._bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough"))
            reading = read_obstacle(
                depth,
                roi=self._roi,
                stop_mm=self._stop_mm,
                min_mm=self._min_mm,
                max_mm=self._max_mm,
                min_pixels=self._min_pixels,
            )
        except Exception as exc:
            self._record_error("Depth check failed: %s" % exc)
            return
        with self._lock:
            self._health.error = None
            self._health.result_stamp = stamp
            self._health.nearest_mm = reading.nearest_mm
            self._health.blocked = reading.blocked
        if reading.nearest_mm is None:
            return
        if reading.blocked != self._blocked:
            self._blocked = reading.blocked
            self.get_logger().info(
                "Obstacle %s; nearest %s mm." % ("blocked" if reading.blocked else "clear", reading.nearest_mm)
            )
        self._publisher.publish(Bool(data=reading.blocked))

    def _record_error(self, message: str) -> None:
        with self._lock:
            changed = self._health.error != message
            self._health.error = message
        if changed:
            self.get_logger().error(message)

    def _publish_status(self) -> None:
        """Own the franco_obstacle diagnostic. Telemetry does not publish it."""

        now = self.get_clock().now()
        with self._lock:
            level, message = self._health.status(now.nanoseconds / 1e9, self._timeout)
            nearest = self._health.nearest_mm
            blocked = self._health.blocked
        status = DiagnosticStatus()
        status.name = "franco_obstacle"
        status.level = (DiagnosticStatus.OK, DiagnosticStatus.WARN, DiagnosticStatus.ERROR)[level]
        status.message = message
        status.values = [
            KeyValue(key="blocked", value=str(blocked).lower()),
            KeyValue(key="stop_distance_mm", value=str(self._stop_mm)),
        ]
        if nearest is not None:
            status.values.append(KeyValue(key="nearest_mm", value=str(nearest)))
        array = DiagnosticArray()
        array.header.stamp = now.to_msg()
        array.status = [status]
        self._status_publisher.publish(array)


def _positive_int(node: Node, name: str) -> int:
    value = int(node.get_parameter(name).value)
    if value <= 0:
        raise ValueError("%s must be positive." % name)
    return value


def main() -> None:
    """Start the obstacle node and spin until the process is asked to stop."""

    rclpy.init()
    spin_until_shutdown(ObstacleNode())


if __name__ == "__main__":
    main()
