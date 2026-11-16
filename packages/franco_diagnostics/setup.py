from setuptools import find_packages, setup

package_name = 'franco_diagnostics'

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
    description='Health reporting and shared ROS lifecycle helpers.',
    license='Apache-2.0',
    entry_points={'console_scripts': ["telemetry = franco_diagnostics.telemetry_node:main"]},
)
