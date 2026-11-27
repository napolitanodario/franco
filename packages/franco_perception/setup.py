from setuptools import find_packages, setup

package_name = 'franco_perception'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=False,
    maintainer='Dario Napolitano',
    maintainer_email='darionapo2.0@gmail.com',
    description='Camera perception: YOLO inference and a depth obstacle check.',
    license='Apache-2.0',
    entry_points={'console_scripts': [
        "detect = franco_perception.detect_node:main",
        "obstacle = franco_perception.obstacle_node:main",
    ]},
)
