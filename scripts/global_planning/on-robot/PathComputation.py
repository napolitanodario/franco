from typing import List, Tuple, Optional

import networkx as nx
import osmnx as ox
import numpy as np

# it receives in input a G graph (from OSMNX)
# Then it computes the pathfinding algorithm associated to the request
# (needs also a source and a destination in polar coordinates).
# It returns the path following polar coordinates (each node visited's GPS coordinates)

# to simplify reading, Node is to represent a position in polar coordinates
Node = Tuple[float, float]

class PathComputation:
    def __init__(self, G):
        # the graph is saved locally
        self.G = G
        pass

    def change_graph(self, node: Node, cost: float) -> bool:
        # function to be used if there is a change in the map cost
        pass

    def compute_path(self, start: Node, goal: Node) -> Tuple[List[Node], Optional[float]]:
        # start & goal are in polar coordinates
        # it returns a list of each visited node in polar coordinates
        """
        :param start: start node, in polar coordinates
        :param goal: goal node, in polar coordinates
        :return: List of Nodes, indicating the path the robot must follow
        """

        # Admissible heuristic

        def heuristic(a: Node, b: Node) -> float:
            # implementation idea: to not hard code it -> class for heuristic functions? Interface Heuristic
            # implemented by each type of function

            # idea: number of nodes from the solution
            return 0.2

        try:
            # A* algorithm (to be improved, a new algorithm needs to be implemented by hand)
            path = nx.astar_path(self.G, start, goal, heuristic=heuristic, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            # no path to reach the destination
            return [], None
        # total length of the whole path
        path_length = ox.routing.route_to_gdf(self.G, path)['length'].sum()
        return path, path_length

    # IDEA: List of tuple (Node, bool) to identify if a Node is a way-point? (like intersections)
    def compute_precise_path(self, path, min_step = 5.0) -> List[Node]:
        """"
        :param path: List of Nodes, indicating the path the robot must follow
        :param min_step: step # TODO: modify
        :return: List of Nodes, indicating the path the robot should follow, indicating also coordinates
            of points between nodes
        """
        # starting from the computed path, iterating through it to get two nodes.
        # In this two nodes, compute the distance each min_step meters. Return the
        # path with more Nodes
        result_path = []
        for node, node_next in zip(path, path[1:]):
            # take the node and its successor, in the internal loop compute the distance each min_step meters
            edge_data = self.G.get_edge_data(node, node_next)
            attrs = next(iter(edge_data.values())) if isinstance(edge_data, dict) else edge_data
            # TODO: if edge_data is None -> it crashes -> handle this case
            line = attrs["geometry"]

            total_length = line.length

            step_distances = list(np.arange(0, total_length, min_step))

            if not step_distances or step_distances[-1] < total_length:
                step_distances.append(total_length)


            points_along_curve = [line.interpolate(d) for d in step_distances]
            result_path.append(points_along_curve)

        return result_path