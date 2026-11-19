# Franco-global-planning
## What do we need to do
1) Use GPS coordinate to command the robot. The waypoints of the robot (intersections) need to be defined
as GPS coordinate. Subdivide each link between two waypoints as a gps coordinate (every 5 meters).


2) Create a software to download a particular section of the map, so the user can select parameters to download 
the desired map (adding information such as memory storage to make a conscious choice).


3) Understand how to implement all in ROS.


---
## Result of the meeting
-Verify our global planner exposes gps coordinates.
-Telemetry

GPS coordinates (compared with sensor of the robot)
Ros utilities to integrate global planning in ros nod.
System to send new coordinates to robot (native ros implementation) changing destination (set of waypoints)

Setup robot to work in a city (downloading the map)
2nd part ;
Every 5 meters GPS points (GPS coordinate)