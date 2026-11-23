"""
Heuristic functions for A* on a graph whose nodes are GPS coordinates.

A heuristic estimates the remaining distance from a node to the goal.
To keep A* optimal (it always finds the shortest path), the heuristic must be
ADMISSIBLE: it must never overestimate the real remaining distance.

Every heuristic here has the same signature, so they are interchangeable:
    heuristic(lat1, lon1, lat2, lon2) -> estimated distance in meters
"""

import math

# Same Earth radius used by OSMnx to compute the "length" of each edge.
# Using the same value guarantees the heuristic never exceeds edge lengths.
EARTH_RADIUS_M = 6_371_009


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Straight-line ("as the crow flies") distance on the Earth's surface, in meters.

    Default heuristic. It is admissible because OSMnx computes every edge length
    with this same formula, and a street can never be shorter than the straight
    line between its two ends.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)

    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    h = min(1.0, h)  # protect against floating point errors
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def zero(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Always 0: A* becomes Dijkstra (no guidance towards the goal).
    Useful only as a baseline to compare against.
    """
    return 0.0


# Available heuristics, selectable by name
HEURISTICS = {
    "haversine": haversine,
    "zero": zero,
}
