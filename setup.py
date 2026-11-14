# setuptools entry point for the franco ament_python package.
#
# colcon reads this file and installs the Python modules, the launch file,
# and the ament resource marker. The YOLO weights are not installed. They stay
# in models/ at the source checkout and the detection node is given that path.

import os
from glob import glob

from setuptools import find_packages, setup

package_name = "franco"


def _launch_files() -> list[str]:
    """Return the launch files that must be installed next to the package.

    An empty list would make the data_files entry illegal, so a missing launch
    directory fails here instead of producing a package that cannot be started.
    """

    files = glob("launch/*.launch.py")
    if not files:
        raise RuntimeError("launch/franco.launch.py is missing.")
    return files


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), _launch_files()),
    ],
    package_data={"franco": ["templates/*.html"]},
    install_requires=["setuptools"],
    zip_safe=False,
    maintainer="Dario Napolitano",
    maintainer_email="darionapo2.0@gmail.com",
    description="Starting ROS 2 graph for a RealSense D415: detection, loopback preview, diagnostics, and a command placeholder.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "detect = franco.detect_node:main",
            "preview = franco.preview_node:main",
            "telemetry = franco.telemetry_node:main",
            "command = franco.command_node:main",
        ],
    },
)
