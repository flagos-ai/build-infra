#!/usr/bin/env python3

# Copyright 2026 FlagOS Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Build FlagOS base container images.

The image version comes from the Containerfile's ``LABEL org.opencontainers.image.version``
plus a per-backend git revision count since that version's tag — so only
Containerfile changes bump the version, not unrelated repo edits.

Image tag convention:
    flagos-base-{name}:{version}-{n}   (n = commits to base/{name} since v{version})

Usage:
    python scripts/build_base.py <name> [options]

Examples:
    python scripts/build_base.py nvidia-cuda12.8 --dry-run
    python scripts/build_base.py ascend-cann9.0.0 --push
    python scripts/build_base.py metax-maca3.7.2.1 --tag my-registry/flagos-base-metax:custom
"""

import argparse
import subprocess
import sys
from pathlib import Path

from version import image_version

IMAGE_PREFIX = "flagos-base"


def find_repo_root() -> Path:
    """Find the repository root (directory containing base/)."""
    d = Path(__file__).resolve().parent.parent
    if (d / "base").is_dir():
        return d
    sys.exit("Error: cannot locate repository root (base/ not found)")


def git(repo_root: Path, *args: str) -> str | None:
    """Run a git command in repo_root; return stripped stdout or None."""
    try:
        r = subprocess.run(
            ["git", *args], cwd=repo_root, capture_output=True, text=True
        )
    except FileNotFoundError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def git_version(repo_root: Path) -> str:
    """Release version from the build-infra Git tag via `git describe --tags`.

    "v2.1.0" -> "2.1.0"; "v2.1.0-3-gabc123" -> "2.1.0-3-gabc123". Both are valid
    Docker tag strings. Falls back to "0.0.0" with a warning when no tag is
    reachable (e.g. a shallow CI checkout without tags — use fetch-depth: 0).
    """
    desc = git(repo_root, "describe", "--tags", "--always")
    if not desc:
        print(
            "warning: no git tag reachable (shallow checkout?) — version=0.0.0",
            file=sys.stderr,
        )
        return "0.0.0"
    if desc and desc[0] == "v" and desc[1:2].isdigit():
        desc = desc[1:]
    return desc


def default_registry(repo_root: Path) -> str | None:
    """Registry prefix for base images from .github/build-config.yml.

    Returns "{host}/{prefixes.base}" (the single source of truth for the
    registry) or None when unavailable — e.g. a local build with no config or
    no PyYAML installed, in which case the image is tagged without a registry.
    """
    config_path = repo_root / ".github" / "build-config.yml"
    if not config_path.exists():
        return None
    try:
        import yaml
    except ImportError:
        return None
    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}
    reg = cfg.get("registry") or {}
    host = reg.get("host")
    prefix = (reg.get("prefixes") or {}).get("base")
    if host and prefix:
        return f"{host}/{prefix}"
    return host or None


def main():
    parser = argparse.ArgumentParser(
        description="Build FlagOS base container images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "name",
        help="Base containerfile name (e.g. nvidia-cuda12.8, ascend-cann9.0.0)",
    )
    parser.add_argument(
        "--registry",
        help="Container registry prefix (default: from .github/build-config.yml)",
    )
    parser.add_argument("--tag", "-t", help="Override image tag")
    parser.add_argument("--push", action="store_true", help="Push after building")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print command without executing"
    )

    args = parser.parse_args()

    repo_root = find_repo_root()
    containerfile = repo_root / "base" / args.name

    if not containerfile.exists():
        available = sorted(p.name for p in (repo_root / "base").iterdir() if p.is_file())
        sys.exit(
            f"Error: '{args.name}' not found in base/\n"
            f"Available: {', '.join(available)}"
        )

    version = image_version(repo_root, args.name) or git_version(repo_root)
    commit = git(repo_root, "rev-parse", "HEAD") or ""
    created = git(repo_root, "show", "-s", "--format=%cI", "HEAD") or ""

    image_name = f"{IMAGE_PREFIX}-{args.name}"

    registry = args.registry or default_registry(repo_root)
    if args.tag:
        tag = args.tag
    elif registry:
        tag = f"{registry}/{image_name}:{version}"
    else:
        tag = f"{image_name}:{version}"

    # OCI provenance stamped onto the built image (git is the source of truth).
    labels = {
        "org.opencontainers.image.version": version,
        "org.opencontainers.image.revision": commit,
        "org.opencontainers.image.created": created,
        "org.opencontainers.image.source": "https://github.com/flagos-ai/build-infra",
    }

    cmd = ["docker", "build", "-f", str(containerfile)]
    for k, v in labels.items():
        if v:
            cmd += ["--label", f"{k}={v}"]
    cmd += ["-t", tag, str(repo_root)]

    if args.dry_run:
        print("Would run:")
        print("  " + " \\\n    ".join(cmd))
        print()
        print(f"Image tag: {tag}")
        print(f"  version={version}, revision={commit[:12]}")
        return

    print(f"Building {tag}...")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"docker build failed with exit code {result.returncode}")

    if args.push:
        print(f"Pushing {tag}...")
        result = subprocess.run(["docker", "push", tag])
        if result.returncode != 0:
            sys.exit(f"docker push failed with exit code {result.returncode}")

    print(f"Done: {tag}")


if __name__ == "__main__":
    main()
