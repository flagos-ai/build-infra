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
#
# Backfill the push_time into an image changelog after a push.
#
# The changelog flow is: a human writes a changelog entry (reason, date left
# empty) BEFORE triggering a push — the entry is the authorization for the
# rebuild. After the push succeeds, this script fills the empty date with the
# registry's authoritative push_time, so the entry's date is never
# hand-typed. Uses ruamel.yaml round-trip so comments and the block style of
# the file survive untouched.
#
# WHICH ENTRY GETS THE DATE. Not "the first entry with an empty date": a human
# adds the new entry above the still-undated one, so picking by position dates
# the wrong entry (2026-11-25, hygon: the apex push dated the 11-24 rebuild
# below it). The gate already decides which entry is pending and prints its
# index; this reads that, so the two cannot disagree.
#
# Usage:
#   python3 backfill_changelog_date.py <changelog.yaml> <tag> <push_time>
#
# push_time format: 2026-09-08T12:22:01Z (RFC3339, from the Harbor API).

import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

GATE = Path(__file__).resolve().parent / "changelog_gate.py"
PENDING_MARK = "gate: pending entry "
# The gate's refusal for a tag whose every entry is dated: an idempotent re-run.
DELIVERED_MARK = "is already delivered"


def pending_index(path: str, tag: str) -> int | None:
    result = subprocess.run(
        [sys.executable, str(GATE), path, tag], capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if line.startswith(PENDING_MARK):
            return int(line[len(PENDING_MARK):].split()[0])
    if DELIVERED_MARK in result.stdout + result.stderr:
        return None
    sys.exit(f"error: the gate refused this changelog:\n{result.stdout}{result.stderr}")


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit("usage: backfill_changelog_date.py <changelog.yaml> <tag> <push_time>")
    path, tag, push_time = sys.argv[1], sys.argv[2], sys.argv[3]

    index = pending_index(path, tag)

    y = YAML()
    y.preserve_quotes = True
    with open(path) as f:
        data = y.load(f)

    for block in data.get("tags") or []:
        if str(block.get("tag")) != tag:
            continue
        if index is None:
            # Already backfilled (idempotent re-run) — not an error, so the
            # record step can call this unconditionally.
            print(f"{path}: tag {tag} has no pending entry — nothing to backfill")
            return
        block["entries"][index]["date"] = push_time
        with open(path, "w") as f:
            y.dump(data, f)
        print(f"backfilled {path}: tag {tag} date -> {push_time}")
        return
    sys.exit(f"error: tag {tag} not found in {path}")


if __name__ == "__main__":
    main()
