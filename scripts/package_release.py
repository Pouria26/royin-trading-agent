"""Export an allowlisted committed runtime; private artifacts never enter the build context."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def package(root, destination, *, app):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=root, text=True).strip():
        raise ValueError("Tracked source must be committed before packaging")
    names = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", revision], cwd=root, text=True
    ).splitlines()
    exact = {
        "pyproject.toml",
        "requirements.lock",
        ".dockerignore",
        "deploy/Dockerfile",
        "deploy/entrypoint.py",
    }
    selected = [
        name
        for name in names
        if name in exact
        or (name.startswith(("src/royin/", "scripts/")) and name.endswith(".py"))
        or (name.startswith("config/") and name.endswith(".json"))
    ]
    if not exact.issubset(selected):
        raise ValueError("Committed deployment files missing")
    destination.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name in selected:
        raw = subprocess.check_output(["git", "show", f"{revision}:{name}"], cwd=root)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    record = dict(revision=revision, files=hashes, secrets_included=False)
    (destination / "release-manifest.json").write_text(json.dumps(record, sort_keys=True, indent=2))
    (destination / "liara.json").write_text(
        json.dumps(
            dict(
                app=app,
                platform="docker",
                port=3000,
            build=dict(dockerfile="deploy/Dockerfile", args=["RELEASE_REVISION="+revision]),
                disks=[dict(name="royin-state", mountTo="/state")],
                envs={"ROYIN_MAINTENANCE": "true", "ROYIN_MAINTENANCE_SECONDS": "3600"},
            ),
            indent=2,
        )
    )
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--app", default="royin-trading-agent")
    args = parser.parse_args()
    record = package(Path(__file__).resolve().parents[1], args.output, app=args.app)
    print(
        json.dumps(
            dict(
                status="PACKAGED_NO_STATE", revision=record["revision"], files=len(record["files"])
            )
        )
    )


if __name__ == "__main__":
    main()
