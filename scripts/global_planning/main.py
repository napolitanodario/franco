from pathlib import Path

import geopandas as gpd
import osmnx as ox
import matplotlib.pyplot as plt
import networkx as nx


if __name__ == '__main__':
    # Enable OSMnx caching to speed up repeated queries
    ox.settings.use_cache = True

    # 1. Get the boundary polygon for Milan proper, project it, and plot it
    city = ox.geocoder.geocode_to_gdf("Milan, Lombardy, Italy")
    city_proj = ox.projection.project_gdf(city)

    fig, ax = plt.subplots(figsize=(8, 8))
    city_proj.plot(ax=ax, fc="lightgray", ec="black")
    ax.set_title("Milan Boundary Polygon", fontsize=14)
    _ = ax.axis("off")
    plt.show()

    # 2. Get boundaries for Milan and key surrounding municipalities (Greater Milan Area)
    place_names = [
        "Milan, Italy",
        "Sesto San Giovanni, Italy",
        "Cinisello Balsamo, Italy",
        "Monza, Italy",
        "Rho, Italy",
    ]

    milan_metro = ox.geocoder.geocode_to_gdf(place_names)

    # Save the boundaries to a GeoPackage file for future use in your app
    Path("data").mkdir(parents=True, exist_ok=True)
    milan_metro.to_file("./data/milan_metro.gpkg", driver="GPKG")
    print("Saved Milan metropolitan boundaries to ./data/milan_metro.gpkg")

    # Project and plot the multi-city boundary dataset
    metro_proj = ox.projection.project_gdf(milan_metro)
    fig, ax = plt.subplots(figsize=(10, 10))
    metro_proj.plot(ax=ax, column="name", cmap="Set3", edgecolor="black", alpha=0.8)
    ax.set_title("Milan Metropolitan Area Boundaries", fontsize=14)
    _ = ax.axis("off")
    plt.show()

    # 3. Optional: Query Milan's boundary directly via its OpenStreetMap Relation ID (R44880)
    milan_by_id = ox.geocoder.geocode_to_gdf(["R44880"], by_osmid=True)
    print(f"Successfully fetched Milan via OSM ID. Area name: {milan_by_id.iloc[0]['display_name']}")

    G = ox.graph_from_place("Milan, Italy", network_type="drive")


    # ---------------------------------------------------------------------------------------------
    origin_address = "Piazza Leonardo da Vinci, Milan, Italy"
    dest_address = "Duomo di Milano, Milan, Italy"

    # 3. Geocode the addresses to latitude/longitude points
    origin_point = ox.geocoder.geocode(origin_address)
    dest_point = ox.geocoder.geocode(dest_address)

    # 4. Find the nearest graph nodes to those lat/lon points
    origin_node = ox.distance.nearest_nodes(G, X=origin_point[1], Y=origin_point[0])
    dest_node = ox.distance.nearest_nodes(G, X=dest_point[1], Y=dest_point[0])

    # 5. Calculate the shortest path using NetworkX
    # We use weight="length" to find the physically shortest geographic path in meters
    print("Calculating shortest path...")
    route = nx.shortest_path(G, source=origin_node, target=dest_node, weight="length")

    # Optional: Calculate total walking distance in meters
    edge_lengths = ox.routing.route_to_gdf(G, route)['length']
    total_distance_meters = edge_lengths.sum()
    print(f"Total walking distance: {total_distance_meters:.2f} meters")

    # 6. Plot the graph with the route highlighted
    print("Plotting route...")
    fig, ax = ox.plot.plot_graph_route(
        G,
        route,
        route_color="red",
        route_linewidth=4,
        node_size=0,
        bgcolor="white"
    )
    plt.show()