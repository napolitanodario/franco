"""HTTP preview of the latest color and depth JPEGs.

The page and the two streams are plain HTTP so a phone or laptop on the same
Wi-Fi network can open them in a browser. Each stream is an MJPEG response:
the browser renders a multipart body in an img tag and keeps the connection
open.

Every route requires HTTP Basic Auth before the camera is touched. Set
STREAM_USERNAME and STREAM_PASSWORD to change the gate. When either variable
is unset, both default to "franco". The process listens on 0.0.0.0 from
run.py, so cloudflared on this machine can reach 127.0.0.1:8080.
"""

from __future__ import annotations

import hmac
import logging
import os
from collections.abc import Iterator

from flask import Flask, Response, jsonify, render_template, request

from realsense_web.camera import RealSenseCamera

logger = logging.getLogger(__name__)

_BOUNDARY = "frame"
_DEFAULT_AUTH = "franco"


def create_app(camera: RealSenseCamera) -> Flask:
    """Build the Flask application around an already started camera.

    The routes are the preview page, the two streams, a JSON status, and an
    empty favicon. This process has no shell, no file browser, and no admin API.
    """

    username = _env_or_default("STREAM_USERNAME", _DEFAULT_AUTH)
    password = _env_or_default("STREAM_PASSWORD", _DEFAULT_AUTH)
    app = Flask(__name__, template_folder="templates")

    @app.before_request
    def require_basic_auth() -> Response | None:
        if _basic_auth_ok(username, password):
            return None
        return Response(
            "Authentication required.\n",
            status=401,
            headers={"WWW-Authenticate": 'Basic realm="RealSense"'},
        )

    @app.get("/")
    def index() -> str:
        status = camera.snapshot()
        return render_template(
            "index.html",
            device_name=status["device_name"],
            width=status["width"],
            height=status["height"],
            fps=status["fps"],
        )

    @app.get("/stream/color")
    def color_stream() -> Response:
        return _mjpeg_response(camera, "color")

    @app.get("/stream/depth")
    def depth_stream() -> Response:
        return _mjpeg_response(camera, "depth")

    @app.get("/status")
    def status() -> Response:
        return jsonify(camera.snapshot())

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status=204)

    return app


def _env_or_default(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _basic_auth_ok(username: str, password: str) -> bool:
    """Return True when the request carries the expected Basic credentials."""

    try:
        supplied = request.authorization
    except Exception:
        logger.info("Rejected a request with a malformed Authorization header.")
        return False
    if supplied is None or supplied.type != "basic":
        return False
    if supplied.username is None or supplied.password is None:
        return False
    user_ok = hmac.compare_digest(supplied.username, username)
    password_ok = hmac.compare_digest(supplied.password, password)
    return user_ok and password_ok


def _mjpeg_response(camera: RealSenseCamera, kind: str) -> Response:
    return Response(
        _mjpeg_frames(camera, kind),
        mimetype=f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


def _mjpeg_frames(camera: RealSenseCamera, kind: str) -> Iterator[bytes]:
    """Yield one JPEG part each time the camera publishes a new frame."""

    last_id = -1
    while True:
        frame_id, jpeg = camera.wait_for_jpeg(kind, last_id, timeout=2.0)
        if jpeg is None:
            if not camera.snapshot()["running"]:
                logger.info("%s stream client disconnected because capture stopped.", kind)
                return
            continue
        last_id = frame_id
        header = (
            f"--{_BOUNDARY}\r\n"
            "Content-Type: image/jpeg\r\n"
            f"Content-Length: {len(jpeg)}\r\n\r\n"
        )
        yield header.encode("ascii") + jpeg + b"\r\n"
