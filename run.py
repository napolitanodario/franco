"""Start the RealSense preview server.

Run this from the project directory, inside the virtual environment:

    python run.py
"""

from __future__ import annotations

import logging
import socket
import sys
from pathlib import Path

from realsense_web.config import Settings, parse_args

logger = logging.getLogger("realsense_web")

_USBFS_MEMORY = Path("/sys/module/usbcore/parameters/usbfs_memory_mb")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        settings = parse_args(argv)
    except ValueError as exc:
        logger.error("%s", exc)
        return 2

    try:
        from realsense_web.camera import RealSenseCamera
        from realsense_web.server import create_app
    except ImportError as exc:
        logger.error("%s", _missing_dependency_message(exc))
        return 1

    _warn_usbfs_memory()
    camera = RealSenseCamera(settings)
    try:
        camera.start()
    except ImportError as exc:
        logger.error("%s", _missing_dependency_message(exc))
        camera.stop()
        return 1
    except Exception:
        logger.exception("Could not start the RealSense camera.")
        camera.stop()
        return 1

    app = create_app(camera)
    _log_urls(settings)
    try:
        # The reloader would open the camera twice. Keep it off.
        app.run(
            host=settings.host,
            port=settings.port,
            threaded=True,
            use_reloader=False,
        )
    finally:
        camera.stop()
    return 0


def _missing_dependency_message(exc: ImportError) -> str:
    name = exc.name or ""
    if name == "pyrealsense2":
        return (
            "pyrealsense2 is not installed in this virtual environment. "
            "On this Raspberry Pi it has to be built from librealsense. "
            "Follow .agents/raspberry-pi.md, then run this command again."
        )
    if name in {"flask", "numpy", "PIL"}:
        return (
            f"Python package {name!r} is missing. From the project directory run: "
            "source .venv/bin/activate && pip install -r requirements.txt"
        )
    return f"Missing Python module: {exc}"


def _warn_usbfs_memory() -> None:
    try:
        value = int(_USBFS_MEMORY.read_text().strip())
    except (OSError, ValueError):
        return
    if value < 128:
        logger.warning(
            "usbfs_memory_mb is %s. RealSense transfers are more reliable at 128. "
            "See .agents/raspberry-pi.md.",
            value,
        )


def _log_urls(settings: Settings) -> None:
    addresses = _ipv4_addresses()
    if not addresses:
        logger.info("Open http://%s:%s on this Pi.", settings.host, settings.port)
        return
    for address in addresses:
        logger.info("Open http://%s:%s", address, settings.port)


def _ipv4_addresses() -> list[str]:
    """Return LAN IPv4 addresses the preview is likely to be reached on."""

    found: list[str] = []

    def add(address: str) -> None:
        if address.startswith("127."):
            return
        if address not in found:
            found.append(address)

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except socket.gaierror:
        pass

    # UDP connect selects the outbound interface and does not send a packet.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            add(sock.getsockname()[0])
    except OSError:
        pass
    return found


if __name__ == "__main__":
    sys.exit(main())
