from setuptools import find_packages, setup

package_name = 'franco_tools'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    package_data={package_name: ['templates/*.html']},
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=False,
    maintainer='Dario Napolitano',
    maintainer_email='darionapo2.0@gmail.com',
    description='Camera preview and bench command monitor.',
    license='Apache-2.0',
    entry_points={'console_scripts': ["preview = franco_tools.preview_node:main",
                                     "command = franco_tools.command_node:main",
                                     "check = franco_tools.health_check:main"]},
)
