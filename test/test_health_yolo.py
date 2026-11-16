"""Regression tests that also run without ROS or model weights."""

import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from franco.health import DetectionHealth, is_fresh
from franco.yolo import YoloDetector


class FreshnessTests(unittest.TestCase):
    def test_expired_future_and_nonfinite_stamps_are_rejected(self):
        for stamp in (7.9, 10.1, float("nan"), float("inf")):
            with self.subTest(stamp=stamp):
                self.assertFalse(is_fresh(stamp, now=10.0, timeout=2.0))
        self.assertTrue(is_fresh(8.0, now=10.0, timeout=2.0))

    def test_empty_results_are_healthy_only_after_successful_inference(self):
        state = DetectionHealth()
        self.assertEqual(state.status(10.0, 2.0)[0], 2)
        state.model_ready = True
        self.assertEqual(state.status(10.0, 2.0)[0], 1)
        state.result_stamp = 9.5
        self.assertEqual(state.status(10.0, 2.0)[0], 0)
        self.assertEqual(state.status(12.0, 2.0)[0], 1)
        state.error = "Inference failed"
        self.assertEqual(state.status(10.0, 2.0), (2, "Inference failed"))


class NmsTests(unittest.TestCase):
    def detect(self, classes, *, agnostic=False):
        detector = YoloDetector(Path("unused.onnx"), 320, 0.45, 0.45,
                                class_agnostic_nms=agnostic)
        predictions = np.zeros((1, len(classes), 84), dtype=np.float32)
        predictions[0, :, :4] = [160, 160, 100, 100]
        for index, class_id in enumerate(classes):
            predictions[0, index, 4 + class_id] = 0.9 - index * 0.1
        detector._session = Mock()
        detector._session.run.return_value = [predictions]
        return detector.detect(np.zeros((320, 320, 3), dtype=np.uint8), limit=20)

    def test_overlapping_different_classes_survive(self):
        self.assertEqual([box.label for box in self.detect([0, 1])], ["person", "bicycle"])

    def test_overlapping_same_class_is_suppressed(self):
        self.assertEqual(len(self.detect([0, 0])), 1)

    def test_class_agnostic_mode_is_explicit(self):
        self.assertEqual(len(self.detect([0, 1], agnostic=True)), 1)

    def test_no_candidates_is_a_valid_empty_result(self):
        self.assertEqual(self.detect([]), [])
