# Shared process lifecycle for the franco nodes.
#
# Each node module keeps its own main(), and each main() calls
# spin_until_shutdown. The helper exists so a SIGINT from the terminal and the
# SIGTERM from systemd both tear the context down once. Calling rclpy.shutdown
# twice raises, and that traceback would hide the real reason the process stopped.

from __future__ import annotations

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


def spin_until_shutdown(node: Node) -> None:
    """Spin one node and shut the ROS context down a single time.

    node is already constructed and rclpy.init has already been called.
    KeyboardInterrupt is the Ctrl+C path. ExternalShutdownException is the
    path where the context was shut down while spin was waiting, which is
    what a service stop looks like. The node is destroyed first so publishers
    disconnect cleanly.
    """

    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
