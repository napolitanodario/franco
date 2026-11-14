# Command placeholder.
#
# Subscribes to geometry_msgs/Twist on /franco/cmd_vel and republishes the
# latest message on /franco/command/last with transient local durability.
# A teleop tool, a gamepad node, or a later autonomy node can publish the
# input topic. A later base driver should subscribe to that same input topic.
#
# This node does not talk to motors, servos, or the camera. It exists so the
# topic names and the QoS are already in the graph while the robot base is
# still undecided.

from __future__ import annotations

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile

from franco.runtime import spin_until_shutdown


class CommandNode(Node):
    """Stores the latest velocity command and keeps it available to late subscribers.

    The republished message uses transient local durability and a depth of one.
    A node that starts after the command was sent still sees the last Twist
    instead of waiting for the next one.
    """

    def __init__(self) -> None:
        """Subscribe to /franco/cmd_vel and advertise /franco/command/last."""

        super().__init__("franco_command")
        last_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._last = self.create_publisher(Twist, "/franco/command/last", last_qos)
        self.create_subscription(Twist, "/franco/cmd_vel", self._on_command, 10)
        self.get_logger().info("Command placeholder listening on /franco/cmd_vel.")

    def _on_command(self, msg: Twist) -> None:
        """Store one Twist and log the two fields a base would use.

        msg is the incoming command. linear.x is forward speed and angular.z
        is yaw rate, both in ROS standard units. The full message is forwarded
        unchanged so a future base sees every field the sender set.
        """

        self._last.publish(msg)
        self.get_logger().info(
            "Command linear.x=%.3f angular.z=%.3f. No actuator is connected."
            % (msg.linear.x, msg.angular.z)
        )


def main() -> None:
    """Start the command node and spin until the process is asked to stop."""

    rclpy.init()
    spin_until_shutdown(CommandNode())


if __name__ == "__main__":
    main()
