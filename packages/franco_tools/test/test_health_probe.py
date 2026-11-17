"""Exercise the installed read-only probe with synthetic ROS publishers."""

import json
import subprocess
import sys
import time
import unittest

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray


class HealthProbeTests(unittest.TestCase):
    def probe(self, emit_frames):
        rclpy.init()
        node = Node("health_probe_publisher", namespace="probe_test", enable_rosout=False)
        color = node.create_publisher(Image, "camera/camera/color/image_raw", 10)
        depth = node.create_publisher(Image, "camera/camera/depth/image_rect_raw", 10)
        detections = node.create_publisher(Detection2DArray, "franco/detections", 10)
        diagnostics = node.create_publisher(DiagnosticArray, "diagnostics", 10)
        process = subprocess.Popen([sys.executable, "-m", "franco_tools.health_check",
            "--namespace", "/probe_test", "--timeout", "2"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5.0
            while process.poll() is None and time.monotonic() < deadline:
                stamp = node.get_clock().now().to_msg()
                status = DiagnosticArray()
                status.status = [DiagnosticStatus(name=name, level=DiagnosticStatus.OK) for name in (
                    "franco_camera", "franco_detect", "franco_command", "franco_usbfs")]
                diagnostics.publish(status)
                if emit_frames:
                    rgb = Image(width=1, height=1, step=3, encoding="rgb8", data=[0, 0, 0])
                    rgb.header.stamp = stamp
                    color.publish(rgb)
                    distance = Image(width=1, height=1, step=2, encoding="16UC1", data=[1, 0])
                    distance.header.stamp = stamp
                    depth.publish(distance)
                    result = Detection2DArray()
                    result.header.stamp = stamp
                    detections.publish(result)
                rclpy.spin_once(node, timeout_sec=0.05)
            output, errors = process.communicate(timeout=2.0)
            return process.returncode, json.loads(output.strip()), errors
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            node.destroy_node()
            rclpy.shutdown()

    def test_live_data_and_ok_diagnostics_pass(self):
        code, result, errors = self.probe(emit_frames=True)
        self.assertEqual(code, 0, errors)
        self.assertTrue(result["healthy"])

    def test_ok_diagnostics_without_images_do_not_pass(self):
        code, result, _ = self.probe(emit_frames=False)
        self.assertEqual(code, 1)
        self.assertFalse(result["healthy"])
        self.assertIn("color: waiting for two distinct frames", result["problems"])
