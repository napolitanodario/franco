FROM ros:jazzy-ros-base@sha256:00b8d47a6e6384a2834e3d01fa87ae767876543baa574f2d64a75c04ea33c698
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-jazzy-cv-bridge ros-jazzy-vision-msgs ros-jazzy-diagnostic-msgs \
    python3-pil python3-flask python3-pytest shellcheck \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
