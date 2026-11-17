"""Create source bundles and validate their GitHub CI provenance."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

SHA = re.compile(r"[0-9a-f]{40}\Z")


def pack(sha, destination):
    if not SHA.fullmatch(sha) or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip() != sha:
        raise ValueError("The bundle SHA must match the tested checkout.")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "source.tar.gz"
    with archive.open("wb") as output:
        subprocess.run(["git", "archive", "--format=tar.gz", sha], stdout=output, check=True)
    manifest = {"schema": 1, "commit": sha,
                "source_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
    (destination / "manifest.json").write_text(json.dumps(manifest) + "\n")


def api(path):
    request = urllib.request.Request(
        os.environ.get("GITHUB_API_URL", "https://api.github.com") + path,
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def verified_run(run, workflow, artifacts, repository):
    if (run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("event") not in {"push", "workflow_dispatch"}
            or run.get("head_branch") != "main" or run.get("workflow_id") != workflow["id"]
            or run.get("head_repository", {}).get("full_name") != repository):
        raise ValueError("A successful CI run from this repository's main branch is required.")
    sha = run["head_sha"]
    if not SHA.fullmatch(sha):
        raise ValueError("Invalid CI commit SHA.")
    matches = [artifact for artifact in artifacts
               if artifact["name"] == "franco-" + sha and not artifact["expired"]]
    if len(matches) != 1:
        raise ValueError("Expected exactly one unexpired source artifact for the CI commit.")
    return sha, int(matches[0]["id"])


def verify(run_id):
    if not run_id.isdigit():
        raise ValueError("CI run ID must be numeric.")
    repository = os.environ["GITHUB_REPOSITORY"]
    prefix = "/repos/" + repository
    run = api(prefix + "/actions/runs/" + run_id)
    workflow = api(prefix + "/actions/workflows/ci.yml")
    artifacts = api(prefix + "/actions/runs/" + run_id + "/artifacts?per_page=100")["artifacts"]
    sha, artifact_id = verified_run(run, workflow, artifacts, repository)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"sha={sha}\nartifact_id={artifact_id}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["pack", "verify"])
    parser.add_argument("value")
    parser.add_argument("destination", nargs="?")
    args = parser.parse_args()
    try:
        if args.command == "pack":
            if args.destination is None:
                parser.error("pack requires a destination")
            pack(args.value, args.destination)
        else:
            verify(args.value)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")
