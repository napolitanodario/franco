# Launch file for the starting franco graph.
#
# Starts the RealSense driver and the four franco nodes as separate processes.
# The driver is the realsense2_camera package already built in this workspace.
# This file does not copy or wrap the camera SDK. Profiles match the first
# prototype: 640x480 at 15 fps, color and depth, alignment and point cloud off,
# because those filters dominate the CPU of a Raspberry Pi 4.

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Return the launch description for the camera and the four franco nodes.

    The RealSense arguments are the profile strings the driver parses as
    width x height x fps. The franco nodes use the default topic names the
    driver publishes under camera namespace "camera" and camera name "camera".
    """

    realsense_launch = os.path.join(
        get_package_share_directory("realsense2_camera"),
        "launch",
        "rs_launch.py",
    )
    driver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(realsense_launch),
        launch_arguments={
            "enable_color": "true",
            "enable_depth": "true",
            "rgb_camera.color_profile": "640x480x15",
            "depth_module.depth_profile": "640x480x15",
            "align_depth.enable": "false",
            "pointcloud.enable": "false",
            "colorizer.enable": "false",
            "enable_gyro": "false",
            "enable_accel": "false",
        }.items(),
    )
    return LaunchDescription(
        [
            driver,
            Node(package="franco", executable="detect", name="franco_detect", output="screen"),
            Node(package="franco", executable="preview", name="franco_preview", output="screen"),
            Node(package="franco", executable="telemetry", name="franco_telemetry", output="screen"),
            Node(package="franco", executable="command", name="franco_command", output="screen"),
        ]
    )
