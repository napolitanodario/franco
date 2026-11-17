from glob import glob
from setuptools import find_packages, setup

package_name = 'franco_bringup'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=False,
    maintainer='Dario Napolitano',
    maintainer_email='darionapo2.0@gmail.com',
    description='Launch and configuration for the Franco perception bench.',
    license='Apache-2.0',
    entry_points={'console_scripts': []},
)
