# Detection node.
#
# Subscribes to the color image from realsense2_camera, runs YOLO11n, and
# publishes vision_msgs/Detection2DArray on /franco/detections. A pass that is
# still running does not queue frames: the next image replaces the one that
# was waiting, and the finished boxes are published on the executor thread.
#
# The node stays up when the weights file is missing. In that case it publishes
# an empty list once a second and logs the reason once, so the preview and the
# telemetry node have a publisher to follow.

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from vision_msgs.msg import (
    Detection2D,
    Detection2DArray,
    ObjectHypothesis,
    ObjectHypothesisWithPose,
)

from franco.runtime import spin_until_shutdown
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

        self._bridge = CvBridge()
        self._lock = threading.Lock()
        self._pending: tuple[Image, object] | None = None
        self._latest: tuple[Image, list[Box]] | None = None
        self._running = True
        self._model_ready = False
        self._warned = False

        model_path = Path(self.get_parameter("model_path").get_parameter_value().string_value)
        self._detector = YoloDetector(
            model_path,
            int(self.get_parameter("input_size").value),
            float(self.get_parameter("confidence").value),
            float(self.get_parameter("iou").value),
        )
        try:
            self._detector.load()
            self._model_ready = True
        except Exception as exc:
            self.get_logger().warning(
                "Detection is disabled (%s). Publishing an empty list." % exc
            )

        color_topic = self.get_parameter("color_topic").get_parameter_value().string_value
        self._publisher = self.create_publisher(Detection2DArray, "/franco/detections", 10)
        # Sensor data QoS matches the RealSense image publisher. A reliable
        # subscription would stay silent because the policies do not match.
        self.create_subscription(Image, color_topic, self._on_image, qos_profile_sensor_data)
        self._worker = threading.Thread(target=self._loop, name="franco-yolo", daemon=True)
        self._worker.start()
        self.create_timer(0.2, self._publish_latest)
        self.get_logger().info("Detection listening on %s." % color_topic)

    def destroy_node(self) -> bool:
        """Stop the worker before the node tears the publisher down.

        Returns the bool from the base class. The worker is a daemon, so a
        stuck inference pass still cannot keep the process alive.
        """

        self._running = False
        return super().destroy_node()

    def _on_image(self, msg: Image) -> None:
        """Keep the newest color frame and drop the one that was waiting.

        msg is the raw color image. The callback does not run the model, so a
        slow pass cannot stall the subscription.
        """

        if not self._model_ready:
            return
        image = np.array(
            self._bridge.imgmsg_to_cv2(msg, desired_encoding="rgb8"),
            copy=True,
        )
        with self._lock:
            self._pending = (msg, image)

    def _loop(self) -> None:
        """Pull the pending frame, run YOLO, and store the boxes.

        The loop sleeps briefly when no frame is waiting. The stored header is
        the header of the image that was classified, so a consumer can match
        boxes to a frame by stamp.
        """

        while self._running:
            with self._lock:
                pending = self._pending
                self._pending = None
            if pending is None:
                _sleep_briefly()
                continue
            header, image = pending
            try:
                boxes = self._detector.detect(
                    image, int(self.get_parameter("max_detections").value)
                )
            except Exception as exc:
                self.get_logger().warning("Detection pass failed: %s" % exc)
                continue
            with self._lock:
                self._latest = (header, boxes)
            if not self._warned:
                self._warned = True
                self.get_logger().info(
                    "First detection pass found %s objects." % len(boxes)
                )

    def _publish_latest(self) -> None:
        """Publish the last finished boxes, or an empty list when no model is loaded.

        The timer is the only publisher caller. An empty list is still a valid
        Detection2DArray, and it tells the rest of the graph that this node is alive.
        """

        message = Detection2DArray()
        message.header.stamp = self.get_clock().now().to_msg()
        with self._lock:
            latest = self._latest
        if latest is not None:
            header, boxes = latest
            message.header = header.header
            message.detections = [_to_detection(header.header, box) for box in boxes]
        self._publisher.publish(message)


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


def _sleep_briefly() -> None:
    """Wait 50 ms so an idle worker does not spin the core."""

    threading.Event().wait(0.05)


def main() -> None:
    """Start the detection node and spin until the process is asked to stop."""

    rclpy.init()
    spin_until_shutdown(DetectNode())


if __name__ == "__main__":
    main()
