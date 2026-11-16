"""Use real Jazzy nodes/messages with synthetic images and a fake model."""

import time
import unittest
from unittest.mock import patch

import numpy as np

try:
    import rclpy
except ModuleNotFoundError:
    raise unittest.SkipTest("ROS 2 is required for node tests.")

from cv_bridge import CvBridge
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from vision_msgs.msg import Detection2DArray

from franco_perception.detect_node import DetectNode, _to_detection
from franco_tools.preview_node import PreviewNode
from franco_diagnostics.telemetry_node import TelemetryNode
from franco_perception.yolo import Box


class NodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def detector(self, *, load_error=None, detect_results=None, **kwargs):
        model = self.enterContext(patch("franco_perception.detect_node.YoloDetector"))
        model.return_value.load.side_effect = load_error
        model.return_value.detect.side_effect = detect_results
        model.return_value.detect.return_value = []
        node = DetectNode(**kwargs)
        self.addCleanup(node.destroy_node)
        return node

    def preview(self):
        self.enterContext(patch.object(PreviewNode, "_serve"))
        self.enterContext(patch("franco_tools.preview_node._ipv4_addresses", return_value=[]))
        node = PreviewNode()
        self.addCleanup(node.destroy_node)
        return node

    def image(self, node, *, depth=False, age=0.0):
        array = np.zeros((8, 8), dtype=np.uint16) if depth else np.zeros((8, 8, 3), dtype=np.uint8)
        image = CvBridge().cv2_to_imgmsg(array, encoding="16UC1" if depth else "rgb8")
        stamp = node.get_clock().now().nanoseconds - int(age * 1e9)
        image.header.stamp.sec, image.header.stamp.nanosec = divmod(stamp, 10**9)
        image.header.frame_id = "camera_color_optical_frame"
        return image

    def status(self, node):
        with patch.object(node._status_publisher, "publish") as publish:
            node._publish_status()
            return publish.call_args.args[0].status[0]

    def wait_for(self, predicate, timeout=2.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Worker did not reach the expected state.")

    def test_model_failure_reports_error_without_fake_empty_detections(self):
        node = self.detector(load_error=FileNotFoundError("missing weights"))
        with patch.object(node._publisher, "publish") as publish:
            node._publish_latest()
            self.assertEqual(publish.call_count, 0)
        self.assertEqual(self.status(node).level, DiagnosticStatus.ERROR)

    def test_result_is_published_once_with_the_source_header(self):
        node = self.detector()
        header = self.image(node).header
        node._latest = (header, [Box(1, 2, 6, 7, "person", 0.9)])
        with patch.object(node._publisher, "publish") as publish:
            node._publish_latest()
            node._publish_latest()
            self.assertEqual(publish.call_count, 1)
            result = publish.call_args.args[0]
        self.assertEqual(result.header, header)
        self.assertEqual(result.detections[0].results[0].hypothesis.class_id, "person")

    def test_expired_result_is_dropped_and_diagnostic_warns(self):
        node = self.detector()
        node._latest = (self.image(node, age=3.0).header, [])
        with patch.object(node._publisher, "publish") as publish:
            node._publish_latest()
            self.assertEqual(publish.call_count, 0)
        self.assertEqual(self.status(node).level, DiagnosticStatus.WARN)

    def test_inference_error_recovers_only_after_a_new_successful_result(self):
        node = self.detector(detect_results=[RuntimeError("broken inference"), []])
        node._on_image(self.image(node))
        self.wait_for(lambda: node._health.error is not None)
        self.assertEqual(self.status(node).level, DiagnosticStatus.ERROR)
        self.assertIsNone(node._latest)
        node._on_image(self.image(node))
        self.wait_for(lambda: node._latest is not None)
        with patch.object(node._publisher, "publish") as publish:
            node._publish_latest()
            self.assertEqual(publish.call_args.args[0].detections, [])
        self.assertEqual(self.status(node).level, DiagnosticStatus.OK)

    def test_telemetry_does_not_publish_a_second_detector_status(self):
        node = TelemetryNode()
        self.addCleanup(node.destroy_node)
        with patch.object(node._publisher, "publish") as publish:
            node._publish()
        names = [status.name for status in publish.call_args.args[0].status]
        self.assertEqual(set(names), {"franco_camera", "franco_command", "franco_usbfs"})

    def test_preview_caps_color_and_depth_independently(self):
        node = self.preview()
        color, depth = self.image(node), self.image(node, depth=True)
        with patch("franco_tools.preview_node.time.monotonic", side_effect=[10, 10.05, 10.3]):
            for _ in range(3):
                node._on_color(color)
        with patch("franco_tools.preview_node.time.monotonic", side_effect=[10, 10.05, 10.3]):
            for _ in range(3):
                node._on_depth(depth)
        self.assertEqual(node.status()["color_frames"], 2)
        self.assertEqual(node.status()["depth_frames"], 2)

    def test_preview_serves_the_installed_template(self):
        response = self.preview()._app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/stream/color", response.data)
        self.assertIn(b"/stream/depth", response.data)

    def test_preview_omits_stale_and_wrong_frame_boxes(self):
        node = self.preview()
        for age, frame, expected in [(0.0, "camera_color_optical_frame", True),
                                     (3.0, "camera_color_optical_frame", False),
                                     (0.0, "another_camera", False)]:
            with self.subTest(age=age, frame=frame):
                result = Detection2DArray()
                result.header = self.image(node, age=age).header
                result.header.frame_id = frame
                result.detections = [_to_detection(result.header, Box(1, 1, 6, 6, "person", 0.9))]
                node._on_detections(result)
                node._last_color_encode = None
                with patch("franco_tools.preview_node._encode_rgb", return_value=b"jpeg") as encode:
                    node._on_color(self.image(node))
                self.assertEqual(bool(encode.call_args.args[2]), expected)

    def test_synthetic_frame_produces_one_result_and_health_over_ros(self):
        node = self.detector(namespace="bench")
        observer = Node("franco_test_observer")
        self.addCleanup(observer.destroy_node)
        results, statuses = [], []
        _subscriptions = [
            observer.create_subscription(Detection2DArray, "/bench/franco/detections", results.append, 10),
            observer.create_subscription(DiagnosticArray, "/bench/diagnostics", statuses.append, 10),
        ]
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        executor.add_node(observer)
        self.addCleanup(executor.shutdown)
        deadline = time.monotonic() + 3.0
        while node._publisher.get_subscription_count() == 0 and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.05)
        self.assertGreater(node._publisher.get_subscription_count(), 0)
        image = self.image(node)
        node._on_image(image)
        while (not results or not statuses) and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.05)
        self.assertTrue(results)
        self.assertTrue(statuses)
        self.assertEqual(results[0].header, image.header)
        self.assertEqual(statuses[-1].status[0].level, DiagnosticStatus.OK)
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.05)
        self.assertEqual(len(results), 1)
