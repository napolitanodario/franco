import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from franco_perception.yolo import YoloDetector


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
