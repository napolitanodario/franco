import unittest

from franco_tools.health_check import HealthWindow


class HealthCheckTests(unittest.TestCase):
    def healthy_window(self):
        window = HealthWindow()
        for kind in ("color", "depth", "detections"):
            window.sample(kind, 9.0, 9.1)
            window.sample(kind, 9.5, 9.6)
        for name in ("franco_camera", "franco_detect", "franco_command", "franco_usbfs"):
            window.diagnostic(name, 0, 9.5)
        return window

    def test_fresh_distinct_data_and_diagnostics_are_required(self):
        self.assertEqual(self.healthy_window().problems(10.0, 10.0), [])
        self.assertTrue(HealthWindow().problems(10.0, 10.0))

    def test_repeated_detection_stamp_does_not_prove_fresh_inferences(self):
        window = self.healthy_window()
        window.samples["detections"] = {9.5}
        for _ in range(10):
            window.sample("detections", 9.5, 9.9)
        self.assertIn("detections: waiting for two distinct frames", window.problems(10, 10))

    def test_stale_frames_and_missing_heartbeats_fail(self):
        self.assertTrue(self.healthy_window().problems(13.0, 13.0))

    def test_detector_error_cannot_be_hidden_by_live_images(self):
        window = self.healthy_window()
        window.diagnostic("franco_detect", 2, 9.9)
        self.assertIn("franco_detect: non-OK diagnostic", window.problems(10, 10))

    def test_depth_is_optional_only_when_explicitly_disabled(self):
        window = self.healthy_window()
        window.samples["depth"].clear()
        self.assertTrue(window.problems(10, 10))
        window.require_depth = False
        self.assertEqual(window.problems(10, 10), [])
