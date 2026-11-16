"""Compose the bench from independently installed ROS packages."""

from copy import deepcopy
import json
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, EmitEvent, IncludeLaunchDescription, OpaqueFunction, RegisterEventHandler,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node

from franco_bringup.configuration import load_profile, namespace_path


def shutdown_on_exit(event, context):
    if context.is_shutdown:
        return []
    return [EmitEvent(event=Shutdown(reason="A graph component exited (%s)." % event.returncode))]


def build_graph(profile: dict, *, namespace="", model_path="", with_camera=True, with_preview=True):
    """Use one namespace for the graph and derive image topics from camera identity."""

    profile = deepcopy(profile)
    namespace = namespace_path(namespace)
    camera = profile["camera"]
    camera_namespace = namespace_path(namespace, camera["camera_namespace"])
    camera_name = camera["camera_name"]
    camera["camera_namespace"] = camera_namespace
    camera_root = namespace_path(camera_namespace, camera_name)
    remappings = [
        ("camera/camera/color/image_raw", camera_root + "/color/image_raw"),
        ("camera/camera/depth/image_rect_raw", camera_root + "/depth/image_rect_raw"),
    ]
    if model_path:
        profile["perception"]["model_path"] = str(Path(model_path).expanduser().resolve())
    actions = [RegisterEventHandler(OnProcessExit(on_exit=shutdown_on_exit))]
    if with_camera:
        arguments = {key: str(value).lower() if isinstance(value, bool) else str(value)
                     for key, value in camera.items()}
        # Preserve numeric serials as strings when the vendor launch evaluates YAML values.
        arguments["serial_no"] = json.dumps(camera["serial_no"])
        driver_launch = Path(get_package_share_directory("realsense2_camera")) / "launch/rs_launch.py"
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(driver_launch)), launch_arguments=arguments.items(),
        ))
    specs = [("franco_perception", "detect", "perception")]
    if with_preview:
        specs.append(("franco_tools", "preview", "preview"))
    specs += [("franco_diagnostics", "telemetry", "diagnostics"),
              ("franco_tools", "command", "command")]
    for package, executable, section in specs:
        actions.append(Node(
            package=package, executable=executable, name="franco_" + executable,
            namespace=namespace, parameters=[profile[section]], remappings=remappings,
            output="screen",
        ))
    return actions


def _launch_setup(context):
    return build_graph(
        load_profile(LaunchConfiguration("config").perform(context)),
        namespace=LaunchConfiguration("namespace").perform(context),
        model_path=LaunchConfiguration("model_path").perform(context),
        with_camera=IfCondition(LaunchConfiguration("with_camera")).evaluate(context),
        with_preview=IfCondition(LaunchConfiguration("with_preview")).evaluate(context),
    )


def generate_launch_description():
    share = Path(get_package_share_directory("franco_bringup"))
    return LaunchDescription([
        DeclareLaunchArgument("config", default_value=str(share / "config/bench.yaml"),
                              description="Bench profile YAML."),
        DeclareLaunchArgument("namespace", default_value="", description="Namespace for the graph."),
        DeclareLaunchArgument("model_path", default_value=EnvironmentVariable(
            "FRANCO_MODEL_PATH", default_value=""), description="ONNX model; overrides the profile."),
        DeclareLaunchArgument("with_camera", default_value="true", description="Start the RealSense driver."),
        DeclareLaunchArgument("with_preview", default_value="true", description="Start the HTTP preview."),
        OpaqueFunction(function=_launch_setup),
    ])
