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

"""Collect version TSVs from extract jobs and saved state into ``versions/``.

On a fresh run (retry=0), wipes ``versions/`` first so stale TSVs from a
previous cycle don't mask a missing backend. Retries restore from the state
branch, then merge freshly-fetched TSVs on top.

After merging, checks completeness against the expected backend list (via
``generate_matrix.py``) and saves accumulated state to a git branch.

Outputs a single JSON line to stdout consumed by GHA step outputs::

    {"done": true|false, "count": N, "label": "X.Y.Z", "missing": "b1 b2"}

Usage: python scripts/collect_version_tsvs.py \\
         --versions <dir> --remote <dir> --retry <N>
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _label() -> str:
    r = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().lstrip("v")
    return "unknown"


def _missing(versions_dir: Path) -> tuple[list[str], int]:
    """Return (missing_names, expected_count)."""
    # gen_data.py must run first so images.yaml includes system packages.
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "docs" / "gen_data.py")],
        capture_output=True, cwd=REPO_ROOT,
    )
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "docs" / "missing_versions.py")],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    # Shell's missing_versions.py writes lines; parse COUNT and MISSING.
    missing = []
    expected = 14
    for line in r.stdout.strip().splitlines():
        if line.startswith("COUNT "):
            parts = line.split()
            if len(parts) >= 3:
                expected = int(parts[2])
        elif line.startswith("MISSING "):
            missing.append(line.split(None, 1)[1])
    return missing, expected


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", required=True, help="Path to versions/ directory")
    ap.add_argument("--remote", required=True, help="Path to versions-remote/ directory")
    ap.add_argument("--retry", type=int, default=0, help="Retry count (0 = fresh run)")
    args = ap.parse_args()

    versions_dir = Path(args.versions)
    remote_dir = Path(args.remote)
    retry = args.retry
    label = _label()

    # Fresh run: wipe versions/ so stale TSVs from a previous cycle
    # don't mask a missing backend.
    if retry == 0:
        if versions_dir.exists():
            shutil.rmtree(versions_dir)
    versions_dir.mkdir(parents=True, exist_ok=True)

    # Merge TSVs from per-backend branches. On retry, previously-collected
    # backends are still present as per-backend branches (fetch_version_tsvs
    # discovers all of them), so we always merge the full set from remote.
    prev = len(list(versions_dir.glob("*.tsv"))) if retry > 0 else 0
    for tsv in remote_dir.glob("*.tsv"):
        shutil.copy2(tsv, versions_dir / tsv.name)
    now = len(list(versions_dir.glob("*.tsv")))
    print(f"After merging: {now} (was {prev})", file=sys.stderr)

    # Check completeness.
    missing_names, expected = _missing(versions_dir)
    done = (not missing_names) and now >= expected

    if done:
        print(f"=== ALL {now}/{expected} BACKENDS COLLECTED ===", file=sys.stderr)
    else:
        print(f"=== INCOMPLETE: {now}/{expected} after retry {retry} ===", file=sys.stderr)
        print(f"Missing: {' '.join(missing_names)}", file=sys.stderr)

    # Output JSON for GHA step outputs.  Use "true"/"false" strings rather than
    # Python bool so that downstream `--done` parsing in finalize_descriptions.py
    # matches the argparse choices (lowercase).
    result = {
        "done": "true" if done else "false",
        "count": now,
        "label": label,
        "missing": " ".join(missing_names),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
