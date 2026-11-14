# The franco package is the Python half of the starting ROS 2 graph.
#
# The RealSense driver lives in the separate realsense2_camera package and is
# started from launch/franco.launch.py. The modules in this package are the
# nodes that sit on top of that driver: detection, a localhost preview, a
# diagnostics publisher, and a command placeholder. None of them open the
# camera device. That split is what lets the driver, the model, and the page
# be restarted or replaced on their own.
