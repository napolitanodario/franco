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

With ROS Jazzy, the driver/SDK and ONNX weights available:

```bash
./scripts/franco doctor       # Check dependencies and model
./scripts/franco build
./scripts/franco test         # Isolated ROS domain; no hardware tests
./scripts/franco run bench    # Foreground development; service must be stopped
./scripts/franco start bench  # Start the installed release
./scripts/franco status       # Service and fresh ROS data
./scripts/franco logs
./scripts/franco preview      # Print preview URLs
./scripts/franco stop         # Also available: restart, check, rollback
```

Enable the shared pre-push hook in each clone with `git config --local core.hooksPath .githooks`.
It requires Docker and runs the CI test suite against the commits being pushed.
Require the **CI / test** check on `main` to enforce tests for every contributor.

CI runs on GitHub ARM64 runners. Manual **Bench** accepts a successful main CI run;
it builds only unless `activate` is selected, then checks live data and rolls back on failure.
One-time service setup and release behavior: [bench setup](docs/design.md#bench-setup).
The installed `config/bench.yaml` defines the bench; `FRANCO_CONFIG` can override it.
