import unittest

import numpy as np

from franco_perception.obstacle import ObstacleHealth, parse_roi, read_obstacle


def depth(*rows):
    return np.array(rows, dtype=np.uint16)


class ObstacleTests(unittest.TestCase):
    def read(self, image, **kwargs):
        settings = dict(roi=(0.0, 1.0, 0.0, 1.0), stop_mm=800, min_mm=100,
                        max_mm=4000, min_pixels=2)
        settings.update(kwargs)
        return read_obstacle(image, **settings)

    def test_enough_near_pixels_block(self):
        reading = self.read(depth([0, 400, 500], [900, 0, 400]))
        self.assertTrue(reading.blocked)
        self.assertEqual(reading.nearest_mm, 400)
        self.assertEqual(reading.near_pixels, 3)

    def test_one_speckle_does_not_block(self):
        reading = self.read(depth([0, 200, 2000], [3000, 0, 2500]), min_pixels=2)
        self.assertFalse(reading.blocked)
        self.assertEqual(reading.nearest_mm, 200)
        self.assertEqual(reading.near_pixels, 1)

    def test_a_near_pixel_outside_the_window_is_ignored(self):
        # The only close pixel sits in the left column, outside the window.
        reading = self.read(depth([150, 2000, 2200], [150, 2100, 2300]),
                            roi=(0.0, 1.0, 0.34, 1.0))
        self.assertFalse(reading.blocked)
        self.assertEqual(reading.nearest_mm, 2000)
        self.assertEqual(reading.near_pixels, 0)

    def test_zeros_and_far_pixels_are_not_a_clear_reading(self):
        reading = self.read(depth([0, 0], [5000, 0]))
        self.assertIsNone(reading.nearest_mm)
        self.assertEqual(reading.near_pixels, 0)
        self.assertFalse(reading.blocked)

    def test_bad_limits_and_empty_windows_fail(self):
        image = depth([400])
        with self.assertRaises(ValueError):
            self.read(image, stop_mm=50, min_mm=100)
        with self.assertRaises(ValueError):
            parse_roi(0.8, 0.2, 0.0, 1.0)
        with self.assertRaises(ValueError):
            self.read(image, roi=(0.0, 0.1, 0.0, 1.0))

    def test_health_stays_a_warning_until_a_measurement_exists(self):
        health = ObstacleHealth(stop_mm=800)
        self.assertEqual(health.status(10.0, 2.0)[0], 1)
        health.result_stamp = 9.5
        self.assertEqual(health.status(10.0, 2.0)[0], 1)
        health.nearest_mm = 2500
        level, message = health.status(10.0, 2.0)
        self.assertEqual(level, 0)
        self.assertIn("2500", message)
        health.blocked = True
        health.nearest_mm = 400
        self.assertIn("Obstacle", health.status(10.0, 2.0)[1])
        health.result_stamp = 7.0
        self.assertEqual(health.status(10.0, 2.0)[0], 1)
