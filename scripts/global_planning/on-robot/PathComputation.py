"""
Global path computation, meant to run on the robot (offline).

It receives an OSMnx graph G (nodes have GPS coordinates: "y" = latitude,
"x" = longitude; edges have "length" in meters and, when the street is curved,
a "geometry" with its shape).

Input: a start and a goal as GPS coordinates (latitude, longitude).
Output: the path the robot must follow, as GPS coordinates.
"""

from typing import Callable, List, Optional, Tuple

import networkx as nx
import osmnx as ox

from heuristics import haversine

# A GPS position: (latitude, longitude)
GpsPoint = Tuple[float, float]

# A heuristic: (lat1, lon1, lat2, lon2) -> estimated distance in meters
Heuristic = Callable[[float, float, float, float], float]


def load_map(path: str) -> nx.MultiDiGraph:
    """Load a map previously saved with the on-laptop tool (works offline)."""
    return ox.load_graphml(path)


class PathComputation:
    def __init__(self, G: nx.MultiDiGraph, heuristic: Heuristic = haversine):
        # the graph and the heuristic are saved locally, used by all methods
        self.G = G
        self.heuristic = heuristic

    # ------------------------------------------------------------------ helpers

    def node_gps(self, node: int) -> GpsPoint:
        """GPS coordinates (latitude, longitude) of a graph node."""
        data = self.G.nodes[node]
        return data["y"], data["x"]

    def nearest_node(self, point: GpsPoint) -> int:
        """ID of the graph node (intersection) closest to a GPS point."""
        lat, lon = point
        return ox.distance.nearest_nodes(self.G, X=lon, Y=lat)

    def _best_edge(self, u: int, v: int) -> dict:
        """
        Attributes of the edge u -> v. If there are parallel edges
        (e.g. two lanes), the shortest one is chosen, like A* does.
        """
        edge_data = self.G.get_edge_data(u, v)
        if edge_data is None:
            raise ValueError(f"No edge between nodes {u} and {v}")
        if isinstance(self.G, nx.MultiGraph):
            return min(edge_data.values(), key=lambda attrs: attrs.get("length", 0.0))
        return edge_data

    def _edge_coords(self, u: int, v: int) -> List[GpsPoint]:
        """
        Shape of the street from u to v, as a list of (latitude, longitude).
        Straight streets have no "geometry" in OSMnx: in that case the shape
        is just the straight line between the two nodes.
        """
        attrs = self._best_edge(u, v)
        start, end = self.node_gps(u), self.node_gps(v)
        if "geometry" not in attrs:
            return [start, end]

        # shapely stores (longitude, latitude): swap to (latitude, longitude)
        coords = [(lat, lon) for lon, lat in attrs["geometry"].coords]
        # make sure the shape goes from u to v
        if haversine(*coords[0], *start) > haversine(*coords[-1], *start):
            coords.reverse()
        return coords

    # -------------------------------------------------------------- main logic

    def change_graph(self, node: GpsPoint, cost: float) -> bool:
        # function to be used if there is a change in the map cost
        # (e.g. a blocked street). TODO: future work, together with D* Lite.
        pass

    def compute_path(self, start: GpsPoint, goal: GpsPoint) -> Tuple[List[int], Optional[float]]:
        """
        :param start: start position, as (latitude, longitude)
        :param goal: goal position, as (latitude, longitude)
        :return: (list of node IDs visited, total length in meters),
                 or ([], None) if no path exists
        """
        # A* works on graph nodes: find the intersections closest to start and goal
        start_node = self.nearest_node(start)
        goal_node = self.nearest_node(goal)

        # A* calls this with two node IDs: read their coordinates from the graph
        def h(a: int, b: int) -> float:
            return self.heuristic(*self.node_gps(a), *self.node_gps(b))

        try:
            # weight="length": each street costs its real length in meters
            path = nx.astar_path(self.G, start_node, goal_node, heuristic=h, weight="length")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            # no path to reach the destination
            return [], None

        path_length = sum(self._best_edge(u, v)["length"] for u, v in zip(path, path[1:]))
        return path, path_length

    def path_to_gps(self, path: List[int]) -> List[GpsPoint]:
        """Waypoints of the path (the intersections), as GPS coordinates."""
        return [self.node_gps(node) for node in path]

    def compute_precise_path(self, path: List[int], min_step: float = 5.0) -> List[GpsPoint]:
        """
        :param path: list of node IDs, as returned by compute_path
        :param min_step: distance in meters between two consecutive points
                         (configurable, 5 m by default)
        :return: one single list of GPS points the robot should follow:
                 a point every min_step meters along each street, plus every
                 intersection. Intersections are not repeated.

        Distances are computed in meters with the haversine formula, so the
        graph does not need to be projected.
        """
        if not path:
            return []
        if len(path) == 1:
            return [self.node_gps(path[0])]

        result_path: List[GpsPoint] = [self.node_gps(path[0])]
        for node, node_next in zip(path, path[1:]):
            coords = self._edge_coords(node, node_next)
            # points along this street, without its first point (already added)
            result_path.extend(self._points_every(coords, min_step)[1:])
        return result_path

    @staticmethod
    def _points_every(coords: List[GpsPoint], step: float) -> List[GpsPoint]:
        """
        Walk along a polyline and return a point every `step` meters,
        always including its first and last point.
        """
        points = [coords[0]]
        next_mark = step          # distance (from the start) of the next point
        walked = 0.0              # distance walked so far
        for (lat1, lon1), (lat2, lon2) in zip(coords, coords[1:]):
            seg = haversine(lat1, lon1, lat2, lon2)
            # add all the points that fall inside this segment
            while seg > 0 and next_mark <= walked + seg:
                t = (next_mark - walked) / seg   # fraction of the segment
                points.append((lat1 + t * (lat2 - lat1), lon1 + t * (lon2 - lon1)))
                next_mark += step
            walked += seg
        # always end exactly at the last point of the street
        if points[-1] != coords[-1]:
            if haversine(*points[-1], *coords[-1]) < 1e-6:
                points[-1] = coords[-1]
            else:
                points.append(coords[-1])
        return points
