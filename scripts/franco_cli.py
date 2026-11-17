"""Local bench commands and transactional activation of CI-verified releases."""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, replace
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tarfile

from ci_bundle import SHA

PACKAGES = ["franco_diagnostics", "franco_perception", "franco_tools", "franco_bringup"]
SERVICE = "franco.service"
MARKER = "# Managed by scripts/franco"
ROS_EXEC = 'source "$1" || exit; shift; exec "$@"'
RUNTIME_KEYS = {"FRANCO_CONFIG", "FRANCO_MODEL_PATH", "FRANCO_NAMESPACE", "FRANCO_ROS_PREFIX",
                "FRANCO_BASE_INSTALL", "FRANCO_PYTHON_PREFIX", "FRANCO_ROS_OVERLAY",
                "ROS_DOMAIN_ID", "RMW_IMPLEMENTATION", "ROS_AUTOMATIC_DISCOVERY_RANGE"}


def run(command, **kwargs):
    return subprocess.run([str(value) for value in command], check=True, **kwargs)


@dataclass
class Settings:
    repo: Path
    env: dict
    state: Path
    config_home: Path
    env_file: Path
    workspace: Path

    @classmethod
    def load(cls):
        repo = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        config_home = Path(env.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))).expanduser()
        env_file = Path(env.get("FRANCO_ENV_FILE", str(config_home / "franco/bench.env"))).expanduser()
        if env_file.is_file():
            for line in env_file.read_text().splitlines():
                tokens = shlex.split(line, comments=True)
                if not tokens:
                    continue
                if len(tokens) != 1 or "=" not in tokens[0]:
                    raise ValueError("bench.env requires one KEY=value assignment per line.")
                key, value = tokens[0].split("=", 1)
                if not (key.startswith("FRANCO_") or key in {
                    "ROS_DOMAIN_ID", "RMW_IMPLEMENTATION", "ROS_AUTOMATIC_DISCOVERY_RANGE",
                }):
                    raise ValueError("Unsupported bench environment key: " + key)
                env.setdefault(key, value)
        state = Path(env.get("FRANCO_STATE_DIR", str(Path.home() / ".local/share/franco"))).expanduser().resolve()
        workspace = Path(env.get("FRANCO_WORKSPACE", str(repo))).expanduser().resolve()
        return cls(repo, env, state, config_home, env_file, workspace)

    @property
    def unit(self):
        return self.config_home / "systemd/user" / SERVICE


def ros(settings, repo, install, command, *, env=None, capture=False, timeout=None):
    environment = {**settings.env, "FRANCO_INSTALL": str(install) if install else "", **(env or {})}
    return run(["bash", "-c", ROS_EXEC, "franco",
                repo / "deploy/env.sh", *command], env=environment, text=True,
               stdout=subprocess.PIPE if capture else None, timeout=timeout)


def profile(settings, repo):
    module_path = repo / "packages/franco_bringup/franco_bringup/configuration.py"
    spec = importlib.util.spec_from_file_location("franco_configuration", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = Path(settings.env.get("FRANCO_CONFIG", str(repo / "packages/franco_bringup/config/bench.yaml")))
    return module.load_profile(path), module.namespace_path


def doctor(settings, repo):
    for key in ("FRANCO_CONFIG", "FRANCO_MODEL_PATH"):
        if settings.env.get(key) and not Path(settings.env[key]).is_absolute():
            raise ValueError(key + " must be an absolute path.")
    data, _ = profile(settings, repo)
    model = settings.env.get("FRANCO_MODEL_PATH") or data["perception"].get("model_path", "")
    if not model or not Path(model).expanduser().is_file():
        raise ValueError("Set FRANCO_MODEL_PATH or the profile's model_path to an existing ONNX file.")
    result = ros(settings, repo, None, ["python3", "-c",
        "import sys,shutil,numpy,PIL,flask,onnxruntime,cv_bridge,rclpy,vision_msgs,diagnostic_msgs\n"
        "missing=[name for name in ('colcon','ros2','systemctl') if shutil.which(name) is None]\n"
        "if missing: raise SystemExit('Missing commands: '+', '.join(missing))\n"
        "print('Python',sys.version.split()[0],'NumPy',numpy.__version__,'ONNX Runtime',onnxruntime.__version__)"],
        capture=True, timeout=30)
    print(result.stdout.strip())
    print("Model:", Path(model).expanduser().resolve())


def build(settings, repo, workspace, *, test=False):
    common = ["colcon", "--log-base", workspace / "log"]
    paths = ["--base-paths", repo / "packages", "--build-base", workspace / "build",
             "--install-base", workspace / "install", "--packages-select", *PACKAGES]
    if test:
        if not (workspace / "install/setup.bash").is_file():
            raise ValueError("Build the project before running tests.")
        run(["python3", "-m", "unittest", "discover", "-s", repo / "test/tooling", "-v"])
        domain = 202 if int(settings.env.get("ROS_DOMAIN_ID", "0")) == 201 else 201
        isolated = {"ROS_DOMAIN_ID": str(domain), "ROS_AUTOMATIC_DISCOVERY_RANGE": "LOCALHOST",
                    "ROS_STATIC_PEERS": ""}
        try:
            ros(settings, repo, workspace / "install", [*common, "test", *paths,
                "--return-code-on-test-failure"], env=isolated)
        finally:
            ros(settings, repo, workspace / "install", [*common, "test-result",
                "--test-result-base", workspace / "build", "--verbose"], env=isolated)
    else:
        ros(settings, repo, None, [*common, "build", *paths])
        verify_install(workspace)


def verify_install(workspace):
    files = [workspace / "install/setup.bash"] + [workspace / "install" / package /
        "share/ament_index/resource_index/packages" / package for package in PACKAGES]
    if not all(path.is_file() for path in files):
        raise ValueError("The build did not install all four project packages.")


def current(settings, name="current"):
    link = settings.state / name
    if not link.is_symlink():
        if link.exists():
            raise ValueError(str(link) + " must be a symlink.")
        return None
    target = link.resolve(strict=True)
    if target.parent != (settings.state / "releases").resolve() or not SHA.fullmatch(target.name):
        raise ValueError("Release pointer escapes the managed releases directory.")
    if not (target / ".ready.json").is_file():
        raise ValueError("Release is not ready: " + str(target))
    return target


def set_pointer(settings, name, target):
    link = settings.state / name
    if target is None:
        link.unlink(missing_ok=True)
        return
    temporary = settings.state / ("." + name + ".next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, link)


@contextmanager
def locked(settings):
    settings.state.mkdir(parents=True, exist_ok=True)
    with (settings.state / "operation.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def service_state():
    result = run(["systemctl", "--user", "show", SERVICE, "--property=LoadState,ActiveState"],
                 text=True, stdout=subprocess.PIPE, timeout=5)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def service(action):
    run(["systemctl", "--user", action, SERVICE], timeout=30)


def require_managed(settings):
    text = settings.unit.read_text() if settings.unit.is_file() else ""
    if MARKER not in text or str(settings.state / "current/source/deploy/run-graph.sh") not in text:
        raise ValueError("Stop the old service and run install-service before activating releases.")


def check(settings, release, timeout=15):
    settings = runtime_settings(settings, release)
    repo = release / "source"
    data, namespace_path = profile(settings, repo)
    namespace = namespace_path(settings.env.get("FRANCO_NAMESPACE", ""))
    camera = data["camera"]
    camera_root = namespace_path(namespace, camera["camera_namespace"], camera["camera_name"])
    command = ["python3", "-m", "franco_tools.health_check", "--timeout", str(timeout),
               "--namespace", namespace, "--color-topic", camera_root + "/color/image_raw",
               "--depth-topic", camera_root + "/depth/image_rect_raw",
               "--result-timeout", str(data["perception"].get("result_timeout", 2.0))]
    if not camera.get("enable_depth", True):
        command.append("--no-depth")
    ros(settings, repo, release / "install", command, timeout=timeout + 5)


def freeze_runtime(settings, repo, release):
    data, _ = profile(settings, repo)
    model = settings.env.get("FRANCO_MODEL_PATH") or data["perception"].get("model_path", "")
    shutil.copy2(Path(model).expanduser(), release / "model.onnx")
    data["perception"]["model_path"] = str(release / "model.onnx")
    (release / "bench.yaml").write_text(json.dumps(data, indent=2) + "\n")
    environment = {key: value for key, value in settings.env.items() if key in RUNTIME_KEYS}
    environment.update(FRANCO_CONFIG=str(release / "bench.yaml"),
                       FRANCO_MODEL_PATH=str(release / "model.onnx"))
    frozen = {"env": environment,
              "model_sha256": hashlib.sha256((release / "model.onnx").read_bytes()).hexdigest(),
              "profile_sha256": hashlib.sha256((release / "bench.yaml").read_bytes()).hexdigest()}
    (release / "runtime.json").write_text(json.dumps(frozen) + "\n")


def runtime_settings(settings, release):
    frozen = json.loads((release / "runtime.json").read_text())
    for name, key in (("model.onnx", "model_sha256"), ("bench.yaml", "profile_sha256")):
        if hashlib.sha256((release / name).read_bytes()).hexdigest() != frozen[key]:
            raise ValueError("Frozen release checksum mismatch: " + name)
    environment = {key: value for key, value in settings.env.items() if key not in RUNTIME_KEYS}
    environment.update(frozen["env"])
    return replace(settings, env=environment)


def verify_bundle(bundle, expected_sha):
    if not SHA.fullmatch(expected_sha):
        raise ValueError("Expected a full commit SHA from the verified CI run.")
    manifest = json.loads((bundle / "manifest.json").read_text())
    if manifest.get("schema") != 1 or manifest.get("commit") != expected_sha:
        raise ValueError("Bundle does not match the verified CI commit.")
    digest = hashlib.sha256((bundle / "source.tar.gz").read_bytes()).hexdigest()
    if manifest.get("source_sha256") != digest:
        raise ValueError("Source archive checksum mismatch.")
    return manifest


def prepare(settings, bundle, sha):
    if platform.system() != "Linux" or platform.machine() not in {"aarch64", "arm64"}:
        raise ValueError("Bench releases must be built on Linux ARM64.")
    manifest = verify_bundle(bundle, sha)
    release = settings.state / "releases" / sha
    ready = release / ".ready.json"
    if ready.is_file() and json.loads(ready.read_text()) == manifest:
        if not (release / "install/setup.bash").is_file():
            raise ValueError("Ready release is missing its installation.")
        doctor(runtime_settings(settings, release), release / "source")
        print("Reusing frozen release settings:", sha)
        return release
    if release.exists():
        if (not (release / ".franco-release").is_file()
                or release in {current(settings), current(settings, "previous")}):
            raise ValueError("Refusing to replace an existing or active release.")
        shutil.rmtree(release)
    (release / "source").mkdir(parents=True)
    (release / ".franco-release").touch()
    with tarfile.open(bundle / "source.tar.gz", "r:gz") as archive:
        archive.extractall(release / "source", filter="data")
    doctor(settings, release / "source")
    freeze_runtime(settings, release / "source", release)
    build(settings, release / "source", release)
    verify_install(release)
    ready.write_text(json.dumps(manifest) + "\n")
    return release


def activate(settings, release):
    require_managed(settings)
    old = current(settings)
    if old == release:
        check(settings, release)
        return
    state = service_state()
    if state.get("LoadState") != "loaded":
        raise ValueError("The managed user service is not loaded.")
    was_active = state.get("ActiveState") == "active"
    if old is None and was_active:
        raise ValueError("Stop the unmanaged runtime before the first release.")
    try:
        service("stop")
        set_pointer(settings, "current", release)
        service("start")
        check(settings, release)
        set_pointer(settings, "previous", old)
    except (Exception, KeyboardInterrupt) as error:
        try:
            service("stop")
            set_pointer(settings, "current", old)
            if was_active and old is not None:
                service("start")
                check(settings, old)
        except Exception as rollback_error:
            raise RuntimeError(f"Activation failed: {error}; rollback also failed: {rollback_error}") from error
        raise RuntimeError(f"Activation failed; previous state restored: {error}") from error


def install_service(settings):
    if service_state().get("ActiveState") not in {"inactive", "failed"}:
        raise ValueError("Stop the existing service before installing the managed unit.")
    quote = lambda value: json.dumps(str(value)).replace("%", "%%")
    text = (settings.repo / "deploy/franco.service").read_text()
    for token, value in {
        "@RUN_GRAPH@": settings.state / "current/source/deploy/run-graph.sh",
        "@WORKING_DIRECTORY@": settings.state / "current",
        "@INSTALL@": "FRANCO_INSTALL=" + str(settings.state / "current/install"),
    }.items():
        text = text.replace(token, quote(value))
    settings.unit.parent.mkdir(parents=True, exist_ok=True)
    if settings.unit.is_file() and MARKER not in settings.unit.read_text():
        backup = settings.unit.with_name(SERVICE + ".before-franco")
        if backup.exists():
            raise ValueError("Original service backup already exists: " + str(backup))
        shutil.copy2(settings.unit, backup)
    pending = settings.unit.with_name("." + SERVICE + ".next")
    pending.write_text(text)
    os.replace(pending, settings.unit)
    run(["systemctl", "--user", "daemon-reload"])
    print("Installed", settings.unit, "(not started or enabled)")


def run_release(release):
    """Run only the frozen release environment; do not load mutable bench.env."""

    release = release.resolve(strict=True)
    if not (release / ".ready.json").is_file():
        raise ValueError("Release is not ready.")
    verify_install(release)
    settings = Settings(release / "source", dict(os.environ), release.parent.parent,
                        Path.home() / ".config", Path("/dev/null"), release)
    settings = runtime_settings(settings, release)
    environment = {**settings.env, "FRANCO_INSTALL": str(release / "install")}
    command = ["bash", "-c", ROS_EXEC, "franco",
               str(release / "source/deploy/env.sh"), "ros2", "launch", "franco_bringup", "bench.launch.py",
               "config:=" + environment["FRANCO_CONFIG"],
               "namespace:=" + environment.get("FRANCO_NAMESPACE", "")]
    os.execvpe("bash", command, environment)


def foreground(settings):
    if service_state().get("ActiveState") not in {"inactive", "failed"}:
        raise ValueError("Stop the service before running a foreground bench.")
    if not (settings.workspace / "install/setup.bash").is_file():
        raise ValueError("Build the project before running it.")
    doctor(settings, settings.repo)
    data, _ = profile(settings, settings.repo)
    config = settings.env.get("FRANCO_CONFIG", str(settings.repo / "packages/franco_bringup/config/bench.yaml"))
    model = settings.env.get("FRANCO_MODEL_PATH") or data["perception"].get("model_path", "")
    ros(settings, settings.repo, settings.workspace / "install", ["ros2", "launch",
        "franco_bringup", "bench.launch.py", "config:=" + config, "model_path:=" + model,
        "namespace:=" + settings.env.get("FRANCO_NAMESPACE", "")])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["doctor", "build", "test", "run", "start", "stop", "restart",
        "status", "logs", "preview", "check", "install-service", "prepare", "deploy", "rollback", "run-release"])
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args()
    try:
        if args.command == "run-release":
            if len(args.arguments) != 1:
                parser.error("run-release requires a release directory")
            run_release(Path(args.arguments[0]))
            return 0
        settings = Settings.load()
        command = args.command
        if command in {"prepare", "deploy"}:
            if len(args.arguments) != 2:
                parser.error(command + " requires BUNDLE_DIR and VERIFIED_SHA")
            with locked(settings):
                release = prepare(settings, Path(args.arguments[0]).resolve(), args.arguments[1])
                if command == "deploy":
                    activate(settings, release)
                print(command + ":", release)
            return 0
        if args.arguments and not (command in {"start", "run"} and args.arguments == ["bench"]):
            parser.error("Unexpected arguments")
        if command == "doctor":
            doctor(settings, settings.repo)
        elif command in {"build", "test"}:
            with locked(settings):
                build(settings, settings.repo, settings.workspace, test=command == "test")
        elif command == "run":
            with locked(settings):
                foreground(settings)
        elif command == "install-service":
            with locked(settings):
                install_service(settings)
        elif command in {"start", "stop", "restart", "rollback"}:
            with locked(settings):
                if command == "stop":
                    service("stop")
                elif command == "rollback":
                    release = current(settings, "previous")
                    if release is None:
                        raise ValueError("No previous release is available.")
                    activate(settings, release)
                else:
                    require_managed(settings)
                    release = current(settings)
                    if release is None:
                        raise ValueError("No active release; prepare and deploy one first.")
                    service(command)
                    check(settings, release)
        elif command in {"check", "status"}:
            state = service_state()
            print(json.dumps(state))
            release = current(settings)
            if state.get("ActiveState") != "active" or release is None:
                raise ValueError("No managed runtime is active.")
            check(settings, release, timeout=5 if command == "status" else 15)
        elif command == "logs":
            run(["journalctl", "--user", "-u", SERVICE, "-f"])
        elif command == "preview":
            release = current(settings)
            if release:
                settings = runtime_settings(settings, release)
            data, _ = profile(settings, release / "source" if release else settings.repo)
            hosts = {"127.0.0.1"}
            hosts.update(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
            for host in sorted(hosts):
                print(f"http://{host}:{data['preview'].get('port', 8080)}")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
