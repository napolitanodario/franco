import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import franco_cli as cli

ROOT = Path(__file__).resolve().parents[2]
OLD, NEW, PREVIOUS = "a" * 40, "b" * 40, "c" * 40


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.settings = cli.Settings(ROOT, {}, self.root / "state", self.root / "config",
                                     self.root / "bench.env", self.root / "workspace")
        self.settings.unit.parent.mkdir(parents=True)
        self.settings.unit.write_text(cli.MARKER + "\n" + str(
            self.settings.state / "current/source/deploy/run-graph.sh"))
        self.service = self.enterContext(patch.object(cli, "service"))
        self.state = self.enterContext(patch.object(cli, "service_state", return_value={
            "LoadState": "loaded", "ActiveState": "active"}))
        self.check = self.enterContext(patch.object(cli, "check"))
        self.enterContext(patch.object(cli.platform, "system", return_value="Linux"))
        self.enterContext(patch.object(cli.platform, "machine", return_value="aarch64"))
        self.enterContext(patch.object(cli, "freeze_runtime"))

    def release(self, sha):
        release = self.settings.state / "releases" / sha
        (release / "install").mkdir(parents=True)
        (release / "install/setup.bash").touch()
        (release / ".ready.json").write_text("{}")
        return release

    def bundle(self, *, unsafe=False):
        bundle = self.root / "bundle"
        bundle.mkdir()
        with tarfile.open(bundle / "source.tar.gz", "w:gz") as archive:
            info = tarfile.TarInfo("../../escaped" if unsafe else "source.txt")
            info.size = 4
            archive.addfile(info, io.BytesIO(b"test"))
        manifest = {"schema": 1, "commit": NEW, "source_sha256": hashlib.sha256(
            (bundle / "source.tar.gz").read_bytes()).hexdigest()}
        (bundle / "manifest.json").write_text(json.dumps(manifest))
        return bundle

    def test_checksum_failure_never_stops_the_runtime(self):
        bundle = self.bundle()
        (bundle / "source.tar.gz").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "checksum"):
            cli.prepare(self.settings, bundle, NEW)
        self.service.assert_not_called()

    def test_ci_commit_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "CI commit"):
            cli.verify_bundle(self.bundle(), OLD)

    def test_build_failure_preserves_current_and_never_marks_release_ready(self):
        old = self.release(OLD)
        cli.set_pointer(self.settings, "current", old)
        with patch.object(cli, "doctor"), patch.object(cli, "build", side_effect=RuntimeError("build failed")):
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                cli.prepare(self.settings, self.bundle(), NEW)
        self.assertEqual(cli.current(self.settings), old)
        self.assertFalse((self.settings.state / "releases" / NEW / ".ready.json").exists())
        self.service.assert_not_called()

    def test_prepare_builds_at_its_final_path_before_activation(self):
        def build(settings, source, workspace):
            self.assertEqual(workspace, self.settings.state / "releases" / NEW)
            self.assertEqual(source, workspace / "source")
            (workspace / "install").mkdir()
            (workspace / "install/setup.bash").touch()
            for package in cli.PACKAGES:
                marker = workspace / "install" / package / "share/ament_index/resource_index/packages" / package
                marker.parent.mkdir(parents=True)
                marker.touch()
        with patch.object(cli, "doctor") as doctor, patch.object(cli, "build", side_effect=build):
            release = cli.prepare(self.settings, self.bundle(), NEW)
        self.assertTrue((release / ".ready.json").is_file())
        doctor.assert_called_once()
        self.assertIsNone(cli.current(self.settings))
        self.service.assert_not_called()

    def test_success_exit_without_installation_is_not_a_ready_release(self):
        with patch.object(cli, "doctor"), patch.object(cli, "build"):
            with self.assertRaisesRegex(ValueError, "all four"):
                cli.prepare(self.settings, self.bundle(), NEW)
        self.assertFalse((self.settings.state / "releases" / NEW / ".ready.json").exists())

    def test_archive_cannot_escape_the_release(self):
        with self.assertRaises(tarfile.TarError):
            cli.prepare(self.settings, self.bundle(unsafe=True), NEW)
        self.assertFalse((self.settings.state / "releases/escaped").exists())
        self.service.assert_not_called()

    def test_successful_activation_updates_current_and_previous(self):
        old, new = self.release(OLD), self.release(NEW)
        cli.set_pointer(self.settings, "current", old)
        cli.activate(self.settings, new)
        self.assertEqual(cli.current(self.settings), new)
        self.assertEqual(cli.current(self.settings, "previous"), old)
        self.assertEqual([call.args[0] for call in self.service.call_args_list], ["stop", "start"])

    def test_failed_health_check_restores_and_checks_the_old_runtime(self):
        old, new, previous = self.release(OLD), self.release(NEW), self.release(PREVIOUS)
        cli.set_pointer(self.settings, "current", old)
        cli.set_pointer(self.settings, "previous", previous)
        self.check.side_effect = [RuntimeError("stale data"), None]
        with self.assertRaisesRegex(RuntimeError, "previous state restored"):
            cli.activate(self.settings, new)
        self.assertEqual(cli.current(self.settings), old)
        self.assertEqual(cli.current(self.settings, "previous"), previous)
        self.assertEqual([call.args[1] for call in self.check.call_args_list], [new, old])
        self.assertEqual([call.args[0] for call in self.service.call_args_list],
                         ["stop", "start", "stop", "start"])

    def test_start_failure_rolls_back(self):
        old, new = self.release(OLD), self.release(NEW)
        cli.set_pointer(self.settings, "current", old)
        self.service.side_effect = [None, RuntimeError("cannot start"), None, None]
        with self.assertRaisesRegex(RuntimeError, "previous state restored"):
            cli.activate(self.settings, new)
        self.assertEqual(cli.current(self.settings), old)

    def test_first_release_failure_leaves_service_stopped(self):
        self.state.return_value["ActiveState"] = "inactive"
        self.check.side_effect = RuntimeError("bad camera")
        with self.assertRaisesRegex(RuntimeError, "previous state restored"):
            cli.activate(self.settings, self.release(NEW))
        self.assertIsNone(cli.current(self.settings))
        self.assertEqual([call.args[0] for call in self.service.call_args_list], ["stop", "start", "stop"])

    def test_rechecking_current_preserves_previous(self):
        old, previous = self.release(OLD), self.release(PREVIOUS)
        cli.set_pointer(self.settings, "current", old)
        cli.set_pointer(self.settings, "previous", previous)
        cli.activate(self.settings, old)
        self.assertEqual(cli.current(self.settings, "previous"), previous)
        self.service.assert_not_called()

    def test_rollback_failure_is_reported_as_failure(self):
        old, new = self.release(OLD), self.release(NEW)
        cli.set_pointer(self.settings, "current", old)
        self.check.side_effect = RuntimeError("unhealthy")
        with self.assertRaisesRegex(RuntimeError, "rollback also failed"):
            cli.activate(self.settings, new)

    def test_unit_install_is_explicit_and_requires_stopped_service(self):
        self.settings.unit.unlink()
        with self.assertRaisesRegex(ValueError, "Stop"):
            cli.install_service(self.settings)
        self.assertFalse(self.settings.unit.exists())
        self.state.return_value["ActiveState"] = "inactive"
        with patch.object(cli, "run") as run:
            cli.install_service(self.settings)
        run.assert_called_once_with(["systemctl", "--user", "daemon-reload"])
        text = self.settings.unit.read_text()
        self.assertNotIn("@", text)
        self.assertIn(cli.MARKER, text)
        self.assertIn(str(self.settings.state / "current/install"), text)

    def test_release_pointer_cannot_escape_state_directory(self):
        self.settings.state.mkdir()
        (self.settings.state / "current").symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, "escapes"):
            cli.current(self.settings)

    def test_original_unit_is_preserved_during_explicit_installation(self):
        self.settings.unit.write_text("original unit")
        self.state.return_value["ActiveState"] = "inactive"
        with patch.object(cli, "run"):
            cli.install_service(self.settings)
        self.assertEqual(self.settings.unit.with_name(cli.SERVICE + ".before-franco").read_text(),
                         "original unit")

    def test_concurrent_operations_are_rejected(self):
        with cli.locked(self.settings):
            with self.assertRaises(BlockingIOError):
                with cli.locked(self.settings):
                    self.fail("Concurrent operation acquired the lock")


class EnvironmentTests(unittest.TestCase):
    def test_failed_ros_setup_never_executes_the_requested_command(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "deploy").mkdir()
            (repo / "deploy/env.sh").write_text("return 1\n")
            marker = repo / "executed"
            settings = cli.Settings(repo, dict(os.environ), repo, repo, repo, repo)
            with self.assertRaises(subprocess.CalledProcessError):
                cli.ros(settings, repo, None, [sys.executable, "-c", "from pathlib import Path; Path('" + str(marker) + "').touch()"])
            self.assertFalse(marker.exists())

    def test_release_freezes_profile_model_and_runtime_domain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            model = root / "external.onnx"
            model.write_bytes(b"original model")
            release = root / "release"
            release.mkdir()
            settings = cli.Settings(ROOT, {"FRANCO_MODEL_PATH": str(model), "ROS_DOMAIN_ID": "7"},
                                    root, root, root / "bench.env", root)
            cli.freeze_runtime(settings, ROOT, release)
            model.write_bytes(b"new model")
            settings.env["ROS_DOMAIN_ID"] = "8"
            frozen = cli.runtime_settings(settings, release)
            self.assertEqual((release / "model.onnx").read_bytes(), b"original model")
            self.assertEqual(frozen.env["ROS_DOMAIN_ID"], "7")
            self.assertEqual(frozen.env["FRANCO_CONFIG"], str(release / "bench.yaml"))
            (release / "model.onnx").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum"):
                cli.runtime_settings(settings, release)

    def test_explicit_environment_overrides_the_local_file_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bench.env"
            path.write_text('FRANCO_NAMESPACE="from_file"\nROS_DOMAIN_ID=7\n')
            with patch.dict(os.environ, {"FRANCO_ENV_FILE": str(path), "FRANCO_NAMESPACE": "explicit"}):
                settings = cli.Settings.load()
            self.assertEqual(settings.env["FRANCO_NAMESPACE"], "explicit")
            self.assertEqual(settings.env["ROS_DOMAIN_ID"], "7")

    def test_build_failures_are_not_swallowed(self):
        with patch.object(cli, "ros", side_effect=subprocess.CalledProcessError(1, ["colcon"])):
            with self.assertRaises(subprocess.CalledProcessError):
                cli.build(Mock(), ROOT, Path("/tmp/workspace"))
