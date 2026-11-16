# Franco

ROS 2 autonomy software, currently focused on a Raspberry Pi 4 / RealSense perception bench.

Packages live under `packages/`. Planned packages are added when their implementation starts.

| Package | Responsibility | Status |
| --- | --- | --- |
| `franco_perception` | Object detection and inference | Current |
| `franco_diagnostics` | Component health and shared lifecycle helpers | Current |
| `franco_tools` | Camera preview and bench utilities | Current |
| `franco_bringup` | Launch files and hardware profiles | Current |
| `franco_description` | Robot model, sensor mounting and TF frames | Planned |
| `franco_base` | Motor-controller interface, encoders and wheel odometry | Planned |
| `franco_localization` | Pose estimation and sensor fusion | Planned |
| `franco_navigation` | Navigation goals and path planning | Planned |
| `franco_control` | Trajectory following and velocity commands | Planned |
| `franco_motion_guard` | Command arbitration, timeouts and motion enable | Planned |
| `franco_interfaces` | Custom ROS interfaces when standard types are insufficient | As needed |

Project packages share this repository. The RealSense driver, SDK and model weights are external.

With ROS Jazzy and dependencies available, from this repository:

```bash
colcon build --base-paths packages
source install/setup.bash
colcon test --base-paths packages --return-code-on-test-failure
colcon test-result
ros2 launch franco_bringup bench.launch.py model_path:=/absolute/path/yolo11n.onnx
```

The installed `config/bench.yaml` configures the camera, inference and preview.
Override it with `config:=/path/bench.yaml`; use `namespace:=bench_a` for an isolated graph.
`FRANCO_MODEL_PATH` can supply the model path. Missing weights produce an ERROR diagnostic.
