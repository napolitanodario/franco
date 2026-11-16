"""Commands from one bench namespace must not reach another bench."""

import time
import unittest

import rclpy
from geometry_msgs.msg import Twist
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node

from franco_tools.command_node import CommandNode


class CommandNamespaceTests(unittest.TestCase):
    def test_commands_are_isolated_between_namespaces(self):
        rclpy.init()
        self.addCleanup(rclpy.shutdown)
        front, rear = CommandNode(namespace="front"), CommandNode(namespace="rear")
        observer = Node("command_test_observer")
        for node in (front, rear, observer):
            self.addCleanup(node.destroy_node)
        executor = SingleThreadedExecutor()
        self.addCleanup(executor.shutdown)
        for node in (front, rear, observer):
            executor.add_node(node)
        front_results, rear_results = [], []
        observer.create_subscription(Twist, "/front/franco/command/last", front_results.append, 10)
        observer.create_subscription(Twist, "/rear/franco/command/last", rear_results.append, 10)
        publisher = observer.create_publisher(Twist, "/front/franco/cmd_vel", 10)
        deadline = time.monotonic() + 4.0
        while (publisher.get_subscription_count() == 0 or front._last.get_subscription_count() == 0
               or rear._last.get_subscription_count() == 0) and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.05)
        self.assertGreater(publisher.get_subscription_count(), 0)
        command = Twist()
        command.linear.x = 0.2
        publisher.publish(command)
        while not front_results and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.05)
        self.assertTrue(front_results)
        self.assertAlmostEqual(front_results[0].linear.x, 0.2)
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.05)
        self.assertEqual(rear_results, [])
