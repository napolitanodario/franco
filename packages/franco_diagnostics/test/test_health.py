import unittest

from franco_diagnostics.health import DetectionHealth, is_fresh


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
