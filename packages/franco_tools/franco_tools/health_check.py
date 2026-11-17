"""Observe fresh ROS data and diagnostics without publishing commands."""

import argparse
import json
import math
import time

from franco_diagnostics.health import is_fresh


class HealthWindow:
    def __init__(self, timeout=2.0, require_depth=True):
        self.timeout = timeout
        self.require_depth = require_depth
        self.samples = {kind: set() for kind in ("color", "depth", "detections")}
        self.latest = {}
        self.statuses = {}

    def sample(self, kind, stamp, received):
        self.samples[kind].add(stamp)
        # Keep memory bounded if a health check runs against a fast publisher.
        if len(self.samples[kind]) > 32:
            self.samples[kind] = set(sorted(self.samples[kind])[-32:])
        self.latest[kind] = (stamp, received)

    def diagnostic(self, name, level, received):
        self.statuses[name] = (level, received)

    def problems(self, ros_now, received_now):
        problems = []
        kinds = ["color", "detections"] + (["depth"] if self.require_depth else [])
        for kind in kinds:
            stamp, received = self.latest.get(kind, (None, None))
            if len(self.samples[kind]) < 2:
                problems.append(kind + ": waiting for two distinct frames")
            elif not is_fresh(stamp, ros_now, self.timeout) or not is_fresh(received, received_now, self.timeout):
                problems.append(kind + ": stale data")
        for name in ("franco_camera", "franco_detect", "franco_command", "franco_usbfs"):
            level, received = self.statuses.get(name, (None, None))
            if received is None or not is_fresh(received, received_now, self.timeout):
                problems.append(name + ": missing or stale diagnostic")
            elif level != 0:
                problems.append(name + ": non-OK diagnostic")
        return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="/")
    parser.add_argument("--color-topic", default="camera/camera/color/image_raw")
    parser.add_argument("--depth-topic", default="camera/camera/depth/image_rect_raw")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--result-timeout", type=float, default=2.0)
    parser.add_argument("--no-depth", action="store_true")
    args = parser.parse_args()
    if any(not math.isfinite(value) or value <= 0 for value in (args.timeout, args.result_timeout)):
        parser.error("Timeouts must be finite and positive.")
    import rclpy
    from diagnostic_msgs.msg import DiagnosticArray
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Image
    from vision_msgs.msg import Detection2DArray

    rclpy.init(args=[])
    node = Node("franco_check", namespace=args.namespace, enable_rosout=False)
    window = HealthWindow(args.result_timeout, require_depth=not args.no_depth)

    def sample(kind, message):
        if kind != "detections" and (message.width <= 0 or message.height <= 0 or not message.data):
            return
        stamp = message.header.stamp.sec + message.header.stamp.nanosec / 1e9
        window.sample(kind, stamp, time.monotonic())

    def diagnostic(message):
        for status in message.status:
            level = int.from_bytes(status.level, "little") if isinstance(status.level, bytes) else status.level
            window.diagnostic(status.name, level, time.monotonic())

    node.create_subscription(Image, args.color_topic, lambda msg: sample("color", msg), qos_profile_sensor_data)
    if not args.no_depth:
        node.create_subscription(Image, args.depth_topic, lambda msg: sample("depth", msg), qos_profile_sensor_data)
    node.create_subscription(Detection2DArray, "franco/detections", lambda msg: sample("detections", msg), 10)
    node.create_subscription(DiagnosticArray, "diagnostics", diagnostic, 10)
    deadline = time.monotonic() + args.timeout
    try:
        problems = window.problems(node.get_clock().now().nanoseconds / 1e9, time.monotonic())
        while problems and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            problems = window.problems(node.get_clock().now().nanoseconds / 1e9, time.monotonic())
        print(json.dumps({"healthy": not problems, "problems": problems,
                          "distinct_frames": {key: len(value) for key, value in window.samples.items()}}))
        return 1 if problems else 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
