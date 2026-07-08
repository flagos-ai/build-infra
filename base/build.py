#!/usr/bin/env python3
"""Build FlagOS base container images.

Reads the version and revision from LABEL directives in the containerfile,
then invokes `docker build` with the derived image tag.

Image tag convention:
    flagos-base-{name}:{version}-{revision}

Usage:
    python base/build.py <name> [options]

Examples:
    python base/build.py nvidia-cuda12.8 --dry-run
    python base/build.py ascend-cann9.0.0 --push
    python base/build.py metax-maca3.7.2.1 --tag my-registry/flagos-base-metax:custom
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

IMAGE_PREFIX = "flagos-base"


def find_repo_root() -> Path:
    """Find the repository root (directory containing base/)."""
    d = Path(__file__).resolve().parent.parent
    if (d / "base").is_dir():
        return d
    sys.exit("Error: cannot locate repository root (base/ not found)")


def parse_labels(containerfile: Path) -> dict[str, str]:
    """Extract OCI LABEL values from a containerfile."""
    labels = {}
    with open(containerfile) as f:
        for line in f:
            m = re.match(
                r'LABEL\s+org\.opencontainers\.image\.(\w+)\s*=\s*"([^"]*)"', line
            )
            if m:
                labels[m.group(1)] = m.group(2)
    return labels


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

    labels = parse_labels(containerfile)
    version = labels.get("version")
    revision = labels.get("revision")

    if not version:
        sys.exit(
            f"Error: no LABEL org.opencontainers.image.version found in {containerfile}"
        )
    if revision is None:
        sys.exit(
            f"Error: no LABEL org.opencontainers.image.revision found in {containerfile}"
        )

    tag = args.tag or f"{IMAGE_PREFIX}-{args.name}:{version}-{revision}"

    cmd = ["docker", "build", "-f", str(containerfile), "-t", tag, str(repo_root)]

    if args.dry_run:
        print("Would run:")
        print("  " + " \\\n    ".join(cmd))
        print()
        print(f"Image tag: {tag}")
        print(f"  version={version}, revision={revision}")
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
