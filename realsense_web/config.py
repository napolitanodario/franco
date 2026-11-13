"""Command line settings for the preview server.

The defaults target a Raspberry Pi 4. A D415 can run faster and at higher
resolution, but 640x480 at 15 fps leaves room for JPEG encoding and a couple
of browsers on the same Wi-Fi network.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings. Construct this once at startup."""

    host: str
    port: int
    width: int
    height: int
    fps: int
    jpeg_quality: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive.")
        if not 1 <= self.fps <= 90:
            raise ValueError("fps must be between 1 and 90.")
        if not 1 <= self.jpeg_quality <= 95:
            raise ValueError("jpeg quality must be between 1 and 95.")
        if not 0 <= self.port <= 65535:
            raise ValueError("port must be between 0 and 65535.")
        if not self.host:
            raise ValueError("host must not be empty.")


def parse_args(argv: list[str] | None = None) -> Settings:
    """Parse process arguments into a Settings object."""

    parser = argparse.ArgumentParser(
        description="Serve RealSense color and depth as a local web page.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Interface to bind. 0.0.0.0 accepts other devices on the LAN.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="TCP port for the preview page. Default: 8080.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=640,
        help="Width of both streams, in pixels. Default: 640.",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=480,
        help="Height of both streams, in pixels. Default: 480.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=15,
        help="Requested frame rate for both streams. Default: 15.",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=75,
        help="JPEG quality from 1 to 95. Default: 75.",
    )
    args = parser.parse_args(argv)
    return Settings(
        host=args.host,
        port=args.port,
        width=args.width,
        height=args.height,
        fps=args.fps,
        jpeg_quality=args.jpeg_quality,
    )
