# Depth obstacle check used by the obstacle node.
#
# The input is one uint16 depth image in millimeters. Zero is a missing
# measurement, the same convention as the RealSense rectified depth topic.
# A fixed fractional window stands in for "in front of the robot". Pixels
# inside a near band are counted, and the band counts as blocked only when
# enough of them agree. One speckle does not.
#
# This module does not subscribe, publish, or know about color frames or
# YOLO boxes. The obstacle node is the caller.

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from franco_diagnostics.health import is_fresh


@dataclass(frozen=True)
class ObstacleReading:
    """One look at the depth window.

    nearest_mm is the closest accepted pixel, or None when the window has no
    measurement inside the accepted range. near_pixels counts pixels at or
    closer than the stop distance. blocked is true when that count reaches
    the minimum the caller asked for.
    """

    nearest_mm: int | None
    near_pixels: int
    blocked: bool


@dataclass
class ObstacleHealth:
    """Last depth check; levels follow diagnostic_msgs/DiagnosticStatus."""

    error: str | None = None
    result_stamp: float | None = None
    nearest_mm: int | None = None
    blocked: bool = False
    stop_mm: int = 0

    def status(self, now: float, timeout: float) -> tuple[int, str]:
        if self.error is not None:
            return 2, self.error
        if self.result_stamp is None:
            return 1, "Waiting for the first depth frame."
        if not is_fresh(self.result_stamp, now, timeout):
            return 1, "Depth frame is stale or its timestamp is invalid."
        if self.nearest_mm is None:
            return 1, "Depth window has no valid measurement."
        if self.blocked:
            return 0, "Obstacle at %s mm." % self.nearest_mm
        return 0, "Clear inside %s mm; nearest is %s mm." % (self.stop_mm, self.nearest_mm)


def parse_roi(top: float, bottom: float, left: float, right: float) -> tuple[float, float, float, float]:
    """Check the four window edges and return them as fractions of the image.

    Each value is a fraction of height or width. The top and left edges are
    included; the bottom and right edges are excluded when the window is sliced.
    """

    edges = (float(top), float(bottom), float(left), float(right))
    if any(not math.isfinite(edge) or edge < 0.0 or edge > 1.0 for edge in edges):
        raise ValueError("ROI fractions must be finite and inside [0, 1].")
    if not (edges[0] < edges[1] and edges[2] < edges[3]):
        raise ValueError("ROI start must be less than ROI end.")
    return edges


def read_obstacle(
    depth: np.ndarray,
    *,
    roi: tuple[float, float, float, float],
    stop_mm: int,
    min_mm: int,
    max_mm: int,
    min_pixels: int,
) -> ObstacleReading:
    """Measure the nearest depth inside a fractional window.

    depth is uint16 millimeters. roi is the tuple from parse_roi. Pixels
    outside [min_mm, max_mm] are ignored, which drops missing zeros and
    readings past the range this check trusts. Returns the nearest accepted
    millimeter, how many pixels fall inside the stop distance, and whether
    that count reaches min_pixels.
    """

    if depth.ndim != 2 or depth.dtype != np.uint16:
        raise ValueError("Depth must be a uint16 image.")
    if min_mm <= 0 or stop_mm < min_mm or max_mm < stop_mm or min_pixels <= 0:
        raise ValueError("Depth limits must satisfy 0 < min_mm <= stop_mm <= max_mm, and min_pixels > 0.")
    height, width = depth.shape
    top, bottom, left, right = parse_roi(*roi)
    row0, row1 = int(height * top), int(height * bottom)
    col0, col1 = int(width * left), int(width * right)
    if row1 <= row0 or col1 <= col0:
        raise ValueError("ROI fractions select an empty window.")
    window = depth[row0:row1, col0:col1]
    valid = (window >= min_mm) & (window <= max_mm)
    if not np.any(valid):
        return ObstacleReading(None, 0, False)
    nearest = int(window[valid].min())
    near_pixels = int(np.count_nonzero(valid & (window <= stop_mm)))
    return ObstacleReading(nearest, near_pixels, near_pixels >= min_pixels)
