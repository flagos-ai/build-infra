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

"""Collect version TSVs from extract jobs into ``versions/``.

The ``accumulate`` job manages state persistence across retries via a git
state branch (``auto/versions-<label>``). On retry>0 it restores the state
branch into ``versions/`` *before* calling this script. On retry=0
``versions/`` starts empty — the cleanse step in the workflow has already
deleted any stale branches from a previous cycle.

This script always merges freshly-fetched TSVs from the remote directory
(produced by ``fetch_version_tsvs.py``) into ``versions/``, overwriting any
previously-collected entries for backends that just produced fresh data.

Each TSV carries two metadata headers prepended by ``upload_version_tsv.py``::

    # run: <github_run_id>
    # verify: success|failure|skipped

After merging, checks completeness against the expected backend list (via
``generate_matrix.py``) and reports a verify summary.

Outputs a single JSON line to stdout consumed by GHA step outputs::

    {"done": "true", "count": 14, "label": "2.1.1",
     "missing": "", "verify_ok": 12, "verify_fail": 2, "verify_skip": 0}

Usage: python scripts/collect_version_tsvs.py \\
         --versions <dir> --remote <dir> --retry <N>
"""

from __future__ import annotations

import json
import re
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


def _missing(versions_dir: Path, expected_backends: list[str] | None = None) -> tuple[list[str], int]:
    """Return (missing_names, expected_count).

    When *expected_backends* is given, compute missing directly.  Otherwise
    delegate to ``missing_versions.py`` (which runs ``generate_matrix.py`` and
    enumerates every backend — correct for a full run, wrong for a scoped one)."""
    if expected_backends is not None:
        expected_set = set(expected_backends)
        got = {f.stem for f in versions_dir.glob("*.tsv")} if versions_dir.is_dir() else set()
        missing = sorted(expected_set - got)
        return missing, len(expected_set)

    # Full run: discover expected backends from generate_matrix.py.
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "docs" / "gen_data.py")],
        capture_output=True, cwd=REPO_ROOT,
    )
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "docs" / "missing_versions.py")],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
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
    ap.add_argument("--expected", default="",
                    help="Space-separated expected backend names (from set-matrix). "
                         "When empty, discover from generate_matrix.py.")
    args = ap.parse_args()

    versions_dir = Path(args.versions)
    remote_dir = Path(args.remote)
    retry = args.retry
    label = _label()

    # State management (cleanse / restore from state branch) is handled by the
    # accumulate job before this script runs. This script always starts with
    # versions/ pre-populated (empty on retry=0, restored from state branch on
    # retry>0) and merges any freshly-fetched TSVs into it.
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
    expected_backends = args.expected.split() if args.expected else None
    missing_names, expected = _missing(versions_dir, expected_backends)
    done = (not missing_names) and now >= expected

    if done:
        print(f"=== ALL {now}/{expected} BACKENDS COLLECTED ===", file=sys.stderr)
    else:
        print(f"=== INCOMPLETE: {now}/{expected} after retry {retry} ===", file=sys.stderr)
        print(f"Missing: {' '.join(missing_names)}", file=sys.stderr)

    # Output JSON for GHA step outputs.  Use "true"/"false" strings rather than
    # Python bool so that downstream `--done` parsing in finalize_descriptions.py
    # matches the argparse choices (lowercase).
    #
    # Also include a verify summary: counts of success/failure/skipped from the
    # metadata headers in each collected TSV.
    verify_counts = {"success": 0, "failure": 0, "skipped": 0}
    for tsv in versions_dir.glob("*.tsv"):
        head = tsv.read_text()[:256]
        m = re.search(r"^# verify: (success|failure|skipped)", head, re.MULTILINE)
        if m:
            verify_counts[m.group(1)] += 1

    result = {
        "done": "true" if done else "false",
        "count": now,
        "label": label,
        "missing": " ".join(missing_names),
        "verify_ok": verify_counts["success"],
        "verify_fail": verify_counts["failure"],
        "verify_skip": verify_counts["skipped"],
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
