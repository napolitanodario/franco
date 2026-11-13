# ROS 2, later

This experiment is one Python process with three roles:

- capture reads the D415 and publishes the latest color and depth JPEGs
- detection reads the latest color image and publishes the latest boxes
- the web page reads those two results and sends them to browsers

Those roles are the future ROS 2 graph. Capture becomes a camera node with a color image topic and a depth image topic. Detection becomes a node that subscribes to color and publishes a detection list. The preview becomes a node that subscribes to both. Nothing in the detector imports the camera SDK or Flask, so it can move into its own node without taking the web server with it.

Debian 13 on this Pi does not ship a ROS 2 distribution. The `ros-*` packages in apt are the ROS 1 stack, and the only ROS 2 package is a test-interface stub. The virtualenv is CPython 3.13. Official ROS 2 releases target Ubuntu and an older Python. Installing that stack into this environment would mix two middlewares on a board that is already serving the camera.

The practical way to add ROS 2 later is a separate Ubuntu 24.04 container or image with its own ROS 2 install, talking to this camera node over the topics above. The web preview can stay where it is until a ROS 2 viewer replaces it. This experiment does not start that container.
