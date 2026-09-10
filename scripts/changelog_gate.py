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
# Gate: refuse to push an app image unless the changelog authorizes it.
#
# The changelog flow: a human writes an entry (reason, date left empty)
# BEFORE triggering a push. The empty date marks it as pending — after the
# push succeeds the app-image workflow backfills the date with the registry
# push_time, so a filled date means "already delivered". Therefore this check
# reduces to one question: does the changelog carry a pending (empty-date)
# entry for the tag being pushed?
#
#   - a brand-new tag needs a new tag block with a pending entry;
#   - a re-push of an existing tag needs a new pending entry under it.
#
# Both cases are the same test, so no registry query / clock comparison is
# needed here (the "since the last push_time" rule is subsumed: the previous
# build's entry was already backfilled, so it can no longer be pending).
#
# Usage:
#   python3 changelog_gate.py <changelog.yaml> <tag>
#
# Exit 0 = authorized; non-zero with an explanatory message otherwise.

import sys

import yaml


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: changelog_gate.py <changelog.yaml> <tag>")
    path, tag = sys.argv[1], sys.argv[2]

    try:
        data = yaml.safe_load(open(path))
    except FileNotFoundError:
        sys.exit(
            f"gate: {path} does not exist — a new app image needs a changelog "
            f"file with a pending entry for tag {tag} before it can be pushed."
        )

    for block in data.get("tags") or []:
        if str(block.get("tag")) != tag:
            continue
        for entry in block.get("entries") or []:
            if not (entry.get("date") or ""):
                print(f"gate: ok — pending changelog entry found for tag {tag}")
                return
        sys.exit(
            f"gate: tag {tag} is already delivered (all its entries are dated). "
            f"Add a new entry describing why this rebuild is needed — an image "
            f"must not be rebuilt without a documented reason."
        )
    sys.exit(
        f"gate: tag {tag} has no changelog record. Add a tag block with a "
        f"pending entry (reason, empty date) before pushing."
    )


if __name__ == "__main__":
    main()
