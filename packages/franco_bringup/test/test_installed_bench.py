"""Smoke-test installed entry points with camera and HTTP disabled."""

import os
import signal
import subprocess
import time
import unittest

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from rclpy.node import Node


class InstalledBenchTests(unittest.TestCase):
    def test_installed_launch_starts_the_namespaced_graph(self):
        process = subprocess.Popen([
            "ros2", "launch", "franco_bringup", "bench.launch.py",
            "with_camera:=false", "with_preview:=false", "namespace:=installed_test",
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True,
            env={**os.environ, "FRANCO_MODEL_PATH": ""})
        rclpy.init()
        observer = Node("installed_bench_observer", enable_rosout=False)
        statuses = {}

        def receive(message):
            statuses.update({status.name: status for status in message.status})

        observer.create_subscription(DiagnosticArray, "/installed_test/diagnostics", receive, 10)
        try:
            deadline = time.monotonic() + 6.0
            while len(statuses) < 4 and time.monotonic() < deadline and process.poll() is None:
                rclpy.spin_once(observer, timeout_sec=0.1)
            names = {name for name, namespace in observer.get_node_names_and_namespaces()
                     if namespace == "/installed_test"}
            self.assertEqual(names, {"franco_detect", "franco_telemetry", "franco_command"})
            self.assertEqual(statuses["franco_detect"].level, DiagnosticStatus.ERROR)
            self.assertEqual(statuses["franco_camera"].level, DiagnosticStatus.WARN)
            self.assertNotIn("franco_preview", names)
        finally:
            observer.destroy_node()
            rclpy.shutdown()
            process.send_signal(signal.SIGINT)
            try:
                output, _ = process.communicate(timeout=4.0)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                output, _ = process.communicate()
                self.fail("Bench launch did not shut down: " + output)
        self.assertEqual(process.returncode, 0, output)
