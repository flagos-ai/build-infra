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
# Backfill the push_time into an app-image changelog after a push.
#
# The changelog flow is: a human writes a changelog entry (reason, date left
# empty) BEFORE triggering a push — the entry is the authorization for the
# rebuild. After the push succeeds, this script fills the empty date with the
# registry's authoritative push_time, so the entry's date is never
# hand-typed. Uses ruamel.yaml round-trip so comments and the block style of
# the file survive untouched.
#
# Usage:
#   python3 backfill_changelog_date.py <changelog.yaml> <tag> <push_time>
#
# push_time format: 2026-09-08T12:22:01Z (RFC3339, from the Harbor API).

import sys
from ruamel.yaml import YAML


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit("usage: backfill_changelog_date.py <changelog.yaml> <tag> <push_time>")
    path, tag, push_time = sys.argv[1], sys.argv[2], sys.argv[3]

    y = YAML()
    y.preserve_quotes = True
    data = y.load(open(path))

    for block in data.get("tags") or []:
        if str(block.get("tag")) != tag:
            continue
        entries = block.get("entries") or []
        # Newest first; fill the most recent entry whose date is still empty.
        for entry in entries:
            if not (entry.get("date") or ""):
                entry["date"] = push_time
                with open(path, "w") as f:
                    y.dump(data, f)
                print(f"backfilled {path}: tag {tag} date -> {push_time}")
                return
        sys.exit(f"error: tag {tag} exists but no entry has an empty date to backfill")
    sys.exit(f"error: tag {tag} not found in {path}")


if __name__ == "__main__":
    main()
