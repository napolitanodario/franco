"""Check installed profiles, model paths and camera-topic wiring."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml
from ament_index_python.packages import get_package_share_directory

from franco_bringup.bringup import build_graph
from franco_bringup.configuration import load_profile, namespace_path


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile(
            Path(get_package_share_directory("franco_bringup")) / "config/bench.yaml"
        )

    def test_installed_profile_keeps_the_bench_defaults(self):
        self.assertEqual(self.profile["camera"]["rgb_camera.color_profile"], "640x480x15")
        self.assertEqual(self.profile["preview"]["preview_fps"], 5.0)
        self.assertEqual(self.profile["perception"]["model_path"], "")

    def test_relative_model_path_is_relative_to_the_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bench.yaml"
            self.profile["perception"]["model_path"] = "weights/model.onnx"
            path.write_text(yaml.safe_dump(self.profile))
            loaded = load_profile(path)
            self.assertEqual(loaded["perception"]["model_path"], str(Path(directory) / "weights/model.onnx"))

    def test_invalid_profiles_fail_before_starting_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bench.yaml"
            for section, value in (("perceptoin", {}), ("preview", []), ("camera", {"serial_no": 123})):
                with self.subTest(section=section):
                    invalid = deepcopy(self.profile)
                    invalid[section] = value
                    path.write_text(yaml.safe_dump(invalid))
                    with self.assertRaises(ValueError):
                        load_profile(path)
        with self.assertRaises(ValueError):
            namespace_path("robot/../camera")

    def test_namespace_and_camera_identity_determine_image_topics(self):
        self.profile["camera"].update(camera_namespace="sensors", camera_name="front", serial_no="001234")
        original = deepcopy(self.profile)
        with patch("franco_bringup.bringup.get_package_share_directory", return_value="/tmp"), \
             patch("franco_bringup.bringup.IncludeLaunchDescription", side_effect=lambda *args, **kwargs:
                   {"driver": dict(kwargs["launch_arguments"])}), \
             patch("franco_bringup.bringup.Node", side_effect=lambda **kwargs: kwargs):
            actions = build_graph(self.profile, namespace="robot_a", model_path="/tmp/model.onnx")
        nodes = [action for action in actions if isinstance(action, dict)]
        camera, detector = nodes[:2]
        self.assertEqual(camera["driver"]["camera_namespace"], "/robot_a/sensors")
        self.assertEqual(camera["driver"]["camera_name"], "front")
        self.assertEqual(camera["driver"]["serial_no"], '"001234"')
        self.assertEqual(detector["namespace"], "/robot_a")
        self.assertIn(("camera/camera/color/image_raw", "/robot_a/sensors/front/color/image_raw"),
                      detector["remappings"])
        self.assertEqual(detector["parameters"][0]["model_path"], "/tmp/model.onnx")
        self.assertEqual(self.profile, original)

    def test_camera_and_http_preview_can_be_disabled(self):
        with patch("franco_bringup.bringup.Node", side_effect=lambda **kwargs: kwargs):
            actions = build_graph(self.profile, with_camera=False, with_preview=False)
        executables = [action["executable"] for action in actions if isinstance(action, dict)]
        self.assertEqual(executables, ["detect", "obstacle", "telemetry", "command"])
