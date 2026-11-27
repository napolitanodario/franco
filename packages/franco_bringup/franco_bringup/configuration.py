"""Load the bench profile without depending on a source checkout or device path."""

from copy import deepcopy
from pathlib import Path
import re

import yaml

_SECTIONS = {"camera", "perception", "obstacle", "preview", "diagnostics", "command"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def namespace_path(*parts: str) -> str:
    segments = [segment for part in parts for segment in part.strip("/").split("/") if segment]
    if any(not _NAME.fullmatch(segment) for segment in segments):
        raise ValueError("Namespaces must contain valid ROS name segments.")
    return "/" + "/".join(segments)


def load_profile(path: str | Path) -> dict:
    path = Path(path).expanduser().resolve()
    with path.open() as source:
        data = yaml.safe_load(source)
    if not isinstance(data, dict) or "camera" not in data:
        raise ValueError("The profile must be a mapping with a camera section.")
    unknown = set(data) - _SECTIONS
    if unknown:
        raise ValueError("Unknown profile sections: %s" % sorted(unknown))
    for section in _SECTIONS:
        data.setdefault(section, {})
        if not isinstance(data[section], dict):
            raise ValueError("Profile section %s must be a mapping." % section)
    camera = data["camera"]
    for key in ("camera_namespace", "camera_name", "serial_no"):
        if not isinstance(camera.get(key), str):
            raise ValueError("camera.%s must be a string." % key)
    if not _NAME.fullmatch(camera["camera_name"]):
        raise ValueError("camera.camera_name must be a valid ROS node name.")
    namespace_path(camera["camera_namespace"])
    model = data["perception"].get("model_path", "")
    if not isinstance(model, str):
        raise ValueError("perception.model_path must be a string.")
    if model:
        model_path = Path(model).expanduser()
        if not model_path.is_absolute():
            model_path = path.parent / model_path
        data["perception"]["model_path"] = str(model_path.resolve())
    return deepcopy(data)
