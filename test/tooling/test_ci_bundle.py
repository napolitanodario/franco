import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from ci_bundle import verified_run

SHA = "a" * 40


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.run = {"status": "completed", "conclusion": "success", "event": "push",
                    "head_branch": "main", "workflow_id": 9, "head_sha": SHA,
                    "head_repository": {"full_name": "owner/franco"}}
        self.artifacts = [{"name": "franco-" + SHA, "expired": False, "id": 123}]

    def verify(self, run=None, artifacts=None):
        return verified_run(self.run if run is None else run, {"id": 9},
                            self.artifacts if artifacts is None else artifacts, "owner/franco")

    def test_main_ci_run_selects_one_immutable_artifact(self):
        self.assertEqual(self.verify(), (SHA, 123))

    def test_pr_fork_failed_or_other_workflow_cannot_reach_the_bench(self):
        for key, value in (("event", "pull_request"), ("head_branch", "feature"),
                           ("conclusion", "failure"), ("workflow_id", 8),
                           ("head_repository", {"full_name": "fork/franco"})):
            with self.subTest(key=key):
                run = copy.deepcopy(self.run)
                run[key] = value
                with self.assertRaises(ValueError):
                    self.verify(run=run)

    def test_missing_expired_or_ambiguous_artifact_fails_closed(self):
        for artifacts in ([], [{**self.artifacts[0], "expired": True}], self.artifacts * 2):
            with self.subTest(artifacts=artifacts), self.assertRaises(ValueError):
                self.verify(artifacts=artifacts)
