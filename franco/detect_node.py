# Detection node.
#
# Subscribes to the color image from realsense2_camera, runs YOLO11n, and
# publishes vision_msgs/Detection2DArray on /franco/detections. A pass that is
# still running does not queue frames: the next image replaces the one that
# was waiting, and the finished boxes are published on the executor thread.
#
# Missing weights and inference failures are reported on /diagnostics. Only
# completed, fresh inference results are published, including valid empty lists.

from __future__ import annotations

import math
import threading
from pathlib import Path

import numpy as np
import rclpy
from cv_bridge import CvBridge
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import Header
from vision_msgs.msg import (
    Detection2D,
    Detection2DArray,
    ObjectHypothesis,
    ObjectHypothesisWithPose,
)

from franco.runtime import spin_until_shutdown
from franco.health import DetectionHealth, is_fresh
from franco.yolo import Box, YoloDetector

_DEFAULT_MODEL = "/srv/franco/ros2_ws/src/franco/models/yolo11n.onnx"


class DetectNode(Node):
    """ROS 2 wrapper around YoloDetector.

    The camera callback only keeps the newest frame. A worker thread runs the
    model. A timer publishes the last finished result so publish() is called
    from the executor rather than from the worker.
    """

    def __init__(self) -> None:
        """Declare parameters, open the model when it is present, and subscribe.

        Parameters:
        color_topic is the sensor_msgs/Image topic from the driver.
        model_path is the onnx file. input_size, confidence, and iou match the
        prototype (320 px, 0.45, 0.45). max_detections caps one message.
        """

        super().__init__("franco_detect")
        self.declare_parameter("color_topic", "/camera/camera/color/image_raw")
        self.declare_parameter("model_path", _DEFAULT_MODEL)
        self.declare_parameter("input_size", 320)
        self.declare_parameter("confidence", 0.45)
        self.declare_parameter("iou", 0.45)
        self.declare_parameter("max_detections", 20)
        self.declare_parameter("result_timeout", 2.0)
        self.declare_parameter("class_agnostic_nms", False)
        self._timeout = float(self.get_parameter("result_timeout").value)
        if not math.isfinite(self._timeout) or self._timeout <= 0:
            raise ValueError("result_timeout must be finite and positive.")
        self._max_detections = int(self.get_parameter("max_detections").value)

        self._bridge = CvBridge()
        self._lock = threading.Lock()
        self._pending: tuple[Header, np.ndarray] | None = None
        self._latest: tuple[Header, list[Box]] | None = None
        self._stop = threading.Event()
        self._health = DetectionHealth()
        self._warned = False

        model_path = Path(self.get_parameter("model_path").get_parameter_value().string_value)
        self._detector = YoloDetector(
            model_path,
            int(self.get_parameter("input_size").value),
            float(self.get_parameter("confidence").value),
            float(self.get_parameter("iou").value),
            class_agnostic_nms=bool(self.get_parameter("class_agnostic_nms").value),
        )
        try:
            self._detector.load()
            self._health.model_ready = True
        except Exception as exc:
            self._health.error = "Model unavailable: %s" % exc
            self.get_logger().error(self._health.error)

        color_topic = self.get_parameter("color_topic").get_parameter_value().string_value
        self._publisher = self.create_publisher(Detection2DArray, "/franco/detections", 10)
        self._status_publisher = self.create_publisher(DiagnosticArray, "/diagnostics", 10)
        # Best effort accepts both best-effort and reliable image publishers.
        self.create_subscription(Image, color_topic, self._on_image, qos_profile_sensor_data)
        self._worker = threading.Thread(target=self._loop, name="franco-yolo", daemon=True)
        self._worker.start()
        self.create_timer(0.05, self._publish_latest)
        self.create_timer(1.0, self._publish_status)
        self.get_logger().info("Detection listening on %s." % color_topic)

    def destroy_node(self) -> bool:
        """Stop the worker before the node tears the publisher down.

        Returns the bool from the base class. The worker is a daemon, so a
        stuck inference pass still cannot keep the process alive.
        """

        self._stop.set()
        self._worker.join(timeout=2.0)
        return super().destroy_node()

    def _on_image(self, msg: Image) -> None:
        """Keep the newest color frame and drop the one that was waiting.

        msg is the raw color image. The callback does not run the model, so a
        slow pass cannot stall the subscription.
        """

        if not self._health.model_ready:
            return
        try:
            image = np.array(
                self._bridge.imgmsg_to_cv2(msg, desired_encoding="rgb8"), copy=True
            )
        except Exception as exc:
            self._record_error("Image conversion failed: %s" % exc)
            return
        with self._lock:
            self._pending = (msg.header, image)

    def _loop(self) -> None:
        """Pull the pending frame, run YOLO, and store the boxes.

        The loop sleeps briefly when no frame is waiting. The stored header is
        the header of the image that was classified, so a consumer can match
        boxes to a frame by stamp.
        """

        while not self._stop.is_set():
            with self._lock:
                pending = self._pending
                self._pending = None
            if pending is None:
                self._stop.wait(0.05)
                continue
            header, image = pending
            try:
                boxes = self._detector.detect(image, self._max_detections)
            except Exception as exc:
                if self._stop.is_set():
                    return
                self._record_error("Inference failed: %s" % exc)
                continue
            if self._stop.is_set():
                return
            with self._lock:
                self._latest = (header, boxes)
            if not self._warned:
                self._warned = True
                self.get_logger().info(
                    "First detection pass found %s objects." % len(boxes)
                )

    def _publish_latest(self) -> None:
        """Consume one finished result; never repeat it or invent an empty result."""

        with self._lock:
            latest = self._latest
            self._latest = None
            if latest is None:
                return
            header, boxes = latest
            stamp = header.stamp.sec + header.stamp.nanosec / 1e9
            self._health.result_stamp = stamp
            self._health.count = len(boxes)
            self._health.error = None
        now = self.get_clock().now().nanoseconds / 1e9
        if not is_fresh(stamp, now, self._timeout):
            return
        message = Detection2DArray()
        message.header = header
        message.detections = [_to_detection(header, box) for box in boxes]
        self._publisher.publish(message)

    def _record_error(self, message: str) -> None:
        with self._lock:
            changed = self._health.error != message
            self._health.error = message
            self._latest = None
        if changed:
            self.get_logger().error(message)

    def _publish_status(self) -> None:
        """Own the detector diagnostic status; telemetry owns the other statuses."""

        now = self.get_clock().now()
        with self._lock:
            level, message = self._health.status(now.nanoseconds / 1e9, self._timeout)
            count = self._health.count
            stamp = self._health.result_stamp
        status = DiagnosticStatus()
        status.name = "franco_detect"
        status.level = (DiagnosticStatus.OK, DiagnosticStatus.WARN, DiagnosticStatus.ERROR)[level]
        status.message = message
        status.values = [KeyValue(key="count", value=str(count))]
        if stamp is not None:
            status.values.append(
                KeyValue(key="result_age_seconds", value=f"{now.nanoseconds / 1e9 - stamp:.3f}")
            )
        array = DiagnosticArray()
        array.header.stamp = now.to_msg()
        array.status = [status]
        self._status_publisher.publish(array)


def _to_detection(header, box: Box) -> Detection2D:
    """Build one Detection2D from a pixel box.

    header is copied so the detection carries the source image stamp and frame.
    class_id is the COCO name. That is a shortcut for this prototype: a later
    metadata database can replace the string with a stable id. The pose is left
    empty because this node does not estimate a 6D pose. id is empty because
    boxes are not tracked across frames.
    """

    detection = Detection2D()
    detection.header = header
    hypothesis = ObjectHypothesis()
    hypothesis.class_id = box.label
    hypothesis.score = float(box.score)
    result = ObjectHypothesisWithPose()
    result.hypothesis = hypothesis
    detection.results.append(result)
    detection.bbox.center.position.x = (box.x1 + box.x2) / 2.0
    detection.bbox.center.position.y = (box.y1 + box.y2) / 2.0
    detection.bbox.center.theta = 0.0
    detection.bbox.size_x = float(box.x2 - box.x1)
    detection.bbox.size_y = float(box.y2 - box.y1)
    detection.id = ""
    return detection


def main() -> None:
    """Start the detection node and spin until the process is asked to stop."""

    rclpy.init()
    spin_until_shutdown(DetectNode())


if __name__ == "__main__":
    main()
