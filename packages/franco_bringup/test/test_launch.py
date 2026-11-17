"""Check graph shutdown with real launch events and harmless child processes."""

from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

try:
    from launch import LaunchDescription, LaunchService
except ImportError:
    raise unittest.SkipTest("ROS 2 launch is required for supervision tests.")

from launch.actions import EmitEvent, ExecuteProcess, RegisterEventHandler, TimerAction
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from ament_index_python.packages import get_package_share_directory

from franco_bringup import bringup as franco_launch
from franco_bringup.configuration import load_profile



class LaunchTests(unittest.TestCase):
    def test_component_exit_stops_other_processes(self):
        def sleeper():
            return ExecuteProcess(cmd=[sys.executable, "-c", "import time; time.sleep(60)"])

        failing = ExecuteProcess(cmd=[sys.executable, "-c", "raise SystemExit(7)"])
        exits = []

        def record(event, context):
            exits.append(event.returncode)

        service = LaunchService()
        service.include_launch_description(LaunchDescription([
            RegisterEventHandler(OnProcessExit(on_exit=record)),
            TimerAction(period=3.0, actions=[EmitEvent(event=Shutdown(reason="Test timeout"))]),
        ]))
        # Replace hardware/application processes, retaining the actual launch policy.
        profile = load_profile(Path(get_package_share_directory("franco_bringup")) / "config/bench.yaml")
        with patch.object(franco_launch, "get_package_share_directory", return_value="/tmp"), \
             patch.object(franco_launch, "IncludeLaunchDescription", return_value=sleeper()), \
             patch.object(franco_launch, "Node", side_effect=[
                 TimerAction(period=0.2, actions=[failing]), sleeper(), sleeper(), sleeper(),
             ]):
            service.include_launch_description(LaunchDescription(franco_launch.build_graph(profile)))
        started = time.monotonic()
        service.run()
        self.assertIn(7, exits)
        self.assertEqual(len(exits), 5)
        self.assertLess(time.monotonic() - started, 2.5)
