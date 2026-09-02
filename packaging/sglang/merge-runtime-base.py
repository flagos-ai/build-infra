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

"""Merge sglang's runtime_base + runtime_common into `dependencies`.

Shared by build-sdist.sh and build-and-repack.sh so the two cannot drift.
The wheel builds from srt_empty (= runtime_base) yet must install in one
step, so it also carries runtime_common, sglang's must-install group.
Those packages only set torch lower bounds satisfied by the pre-baked
vendor runtime, so pip never moves torch (decisions.md §2).

Usage:
    merge-runtime-base.py pyproject.toml

Exit status: 0 = merged, 1 = a section is missing or the rewrite failed.
"""

import re
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: merge-runtime-base.py pyproject.toml", file=sys.stderr)
        return 1
    path = sys.argv[1]
    text = open(path).read()

    def section_items(section):
        # Scan to the array's *matching* close bracket, not the first `]`:
        # entries may embed one inside quotes (runtime_common's first entry is
        # "sglang[runtime_base]").
        m = re.search(rf'^{section}\s*=\s*\[', text, re.M)
        if not m:
            raise SystemExit(f"merge-runtime-base: no `{section}` array in {path}")
        i = m.end()
        depth = 1
        in_string = False
        while depth:
            ch = text[i]
            if ch == '"' and text[i - 1] != "\\":
                in_string = not in_string
            elif not in_string:
                depth += ch == "["
                depth -= ch == "]"
            i += 1
        return re.findall(r'"([^"]+)"', text[m.end():i - 1])

    deps = section_items("dependencies")
    base = section_items("runtime_base")
    common = section_items("runtime_common")

    # runtime_base re-declares all six base deps — dedupe, then sort by
    # package name (before any version specifier), the order upstream asks for.
    merged = list(dict.fromkeys(deps + base))

    # runtime_common is sglang's must-install group — take it whole so
    # completeness follows upstream's declaration, not our count. Skip the
    # sglang[...] self-refs (runtime_base, merged above) and compressed-tensors
    # (app images install the pinned +flagos repack instead).
    for entry in common:
        name = re.split(r'[<=>!~\[\s]', entry)[0]
        if entry.startswith("sglang[") or name.lower() == "compressed-tensors":
            continue
        if not any(re.split(r'[<=>!~\[\s]', have)[0].lower() == name.lower()
                   for have in merged):
            merged.append(entry)

    merged.sort(key=lambda s: re.sub(r'[<=>!~\[\s].*$', '', s).lower())

    rendered = 'dependencies = ["' + '", "'.join(merged) + '"]'
    text, n = re.subn(r'^dependencies\s*=\s*\[.*?\]', rendered, text,
                      count=1, flags=re.M | re.S)
    if n != 1:
        raise SystemExit(f"merge-runtime-base: failed to rewrite `dependencies` in {path}")
    open(path, "w").write(text)

    print(f"  dependencies: {len(deps)} -> {len(merged)} after merging runtime_base + runtime_common")
    return 0


if __name__ == "__main__":
    sys.exit(main())
