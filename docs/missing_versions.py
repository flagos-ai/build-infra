#!/usr/bin/env python3
"""Report which backends are missing from the versions/ directory.  Reads the
expected backend list from ``scripts/generate_matrix.py`` and the collected TSV
files in ``versions/``, then prints a markdown summary for the PR body.

Usage: python3 docs/missing_versions.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_matrix.py")],
        capture_output=True, text=True, cwd=ROOT,
    )
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit("unable to determine expected backends")
    matrix = json.loads(r.stdout)
    expected = {i["name"] for i in matrix.get("include", [])}

    ver_dir = ROOT / "versions"
    got = {f.stem for f in ver_dir.glob("*.tsv")} if ver_dir.is_dir() else set()
    missing = expected - got

    # Machine line for the caller: COUNT len(got) len(expected)
    print(f"COUNT {len(got)} {len(expected)}")
    for n in sorted(missing):
        print(f"MISSING {n}")


if __name__ == "__main__":
    main()
