# Telemetry node.
#
# Publishes a diagnostic_msgs/DiagnosticArray on /diagnostics once a second.
# The array has one status for the camera images this graph is receiving, one
# for the last command, and one for the USB filesystem buffer the RealSense
# driver needs. The detector publishes its own status on the same topic.
# Nothing here commands the camera or a robot. A later monitor can subscribe
# to /diagnostics without a
# new topic being invented for each signal.

from __future__ import annotations

from pathlib import Path

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import Image

from franco_diagnostics.runtime import spin_until_shutdown

_USBFS = Path("/sys/module/usbcore/parameters/usbfs_memory_mb")
_USBFS_WANTED = 128


class TelemetryNode(Node):
    """Collects a few counters and publishes them as diagnostics.

    Camera rate is estimated from the color images that arrive between two
    publishes. The last Twist is whatever its topic last said. The USB buffer
    is read from sysfs.
    """

    def __init__(self, **kwargs) -> None:
        """Subscribe to the three signals and start the one-second timer.

        color_topic is the same color image the detector uses. Counting those
        messages is enough to see that the driver is publishing. The command
        subscription uses transient local durability so the last Twist stored
        by franco_command is visible even if it was published earlier.
        """

        super().__init__("franco_telemetry", **kwargs)
        self.declare_parameter("color_topic", "camera/camera/color/image_raw")
        color_topic = self.get_parameter("color_topic").get_parameter_value().string_value

        self._color_count = 0
        self._window = 0
        self._has_command = False
        self._linear_x = 0.0
        self._angular_z = 0.0

        self._publisher = self.create_publisher(DiagnosticArray, "diagnostics", 10)
        self.create_subscription(Image, color_topic, self._on_color, qos_profile_sensor_data)
        command_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(Twist, "franco/command/last", self._on_command, command_qos)
        self.create_timer(1.0, self._publish)
        self.get_logger().info("Telemetry publishing /diagnostics.")

    def _on_color(self, msg: Image) -> None:
        """Count one color image. msg itself is not stored."""

        del msg
        self._color_count += 1
        self._window += 1

    def _on_command(self, msg: Twist) -> None:
        """Remember the linear x and angular z of the latest command.

        Those two fields are the ones a differential base would use later.
        The rest of the Twist is ignored until a base node exists.
        """

        self._has_command = True
        self._linear_x = float(msg.linear.x)
        self._angular_z = float(msg.angular.z)

    def _publish(self) -> None:
        """Publish one DiagnosticArray covering camera, command, and USB.

        The color window is reset after the publish, so the reported rate is
        the count over the last second. A silent camera is WARN. A USB buffer
        below 128 MB is WARN. An idle command topic is OK: nobody has to drive.
        """

        array = DiagnosticArray()
        array.header.stamp = self.get_clock().now().to_msg()
        rate = float(self._window)
        self._window = 0
        array.status.append(self._camera_status(rate))
        array.status.append(self._command_status())
        array.status.append(self._usbfs_status())
        self._publisher.publish(array)

    def _camera_status(self, rate: float) -> DiagnosticStatus:
        """Build the camera status from the images counted in the last second.

        rate is that count. Zero means the driver is not publishing, which is
        WARN. The total since startup is included so a short stall is visible
        against a node that has otherwise been receiving frames.
        """

        status = DiagnosticStatus()
        status.name = "franco_camera"
        status.hardware_id = "realsense-d415"
        if rate <= 0.0 and self._color_count == 0:
            status.level = DiagnosticStatus.WARN
            status.message = "No color frames yet."
        elif rate <= 0.0:
            status.level = DiagnosticStatus.WARN
            status.message = "Color frames stopped."
        else:
            status.level = DiagnosticStatus.OK
            status.message = "Color frames are arriving."
        status.values = [
            KeyValue(key="hz", value=f"{rate:.1f}"),
            KeyValue(key="frames", value=str(self._color_count)),
        ]
        return status

    def _command_status(self) -> DiagnosticStatus:
        """Build the command status from the last stored Twist.

        No command yet is OK. This node only reports the placeholder topic.
        It does not decide whether a base should be moving.
        """

        status = DiagnosticStatus()
        status.name = "franco_command"
        status.level = DiagnosticStatus.OK
        if not self._has_command:
            status.message = "No command received yet."
        else:
            status.message = "Last command stored."
        status.values = [
            KeyValue(key="linear_x", value=f"{self._linear_x:.3f}"),
            KeyValue(key="angular_z", value=f"{self._angular_z:.3f}"),
        ]
        return status

    def _usbfs_status(self) -> DiagnosticStatus:
        """Read usbfs_memory_mb and warn when it is below the RealSense value.

        The driver drops transfers when the kernel USB buffer is left at its
        default. The oneshot deploy/realsense-usbfs.service writes 128 at boot.
        """

        status = DiagnosticStatus()
        status.name = "franco_usbfs"
        try:
            value = int(_USBFS.read_text().strip())
        except (OSError, ValueError):
            status.level = DiagnosticStatus.WARN
            status.message = "usbfs_memory_mb could not be read."
            return status
        status.values = [KeyValue(key="usbfs_memory_mb", value=str(value))]
        if value < _USBFS_WANTED:
            status.level = DiagnosticStatus.WARN
            status.message = f"usbfs_memory_mb is {value}. RealSense wants {_USBFS_WANTED}."
        else:
            status.level = DiagnosticStatus.OK
            status.message = "USB buffer is large enough for the camera."
        return status


def main() -> None:
    """Start the telemetry node and spin until the process is asked to stop."""

    rclpy.init()
    spin_until_shutdown(TelemetryNode())


if __name__ == "__main__":
    main()
