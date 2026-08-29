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

"""Merge sglang's `runtime_base` extra into `dependencies`.

Single source of truth for the pyproject rewrite, shared by build-sdist.sh
and build-and-repack.sh so the two paths cannot drift. The wheel must carry
the full runtime set in Requires-Dist for a one-step
`pip install sglang==<version>+flagos`. Additive merge: the torch-pinning
extras (srt_mps / srt_musa) stay out of the default set, so the wheel stays
torch-free by construction (docs/sglang-0.5.18/decisions.md §2).

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
        m = re.search(rf'^{section}\s*=\s*\[(.*?)\]', text, re.M | re.S)
        if not m:
            raise SystemExit(f"merge-runtime-base: no `{section}` array in {path}")
        return re.findall(r'"([^"]+)"', m.group(1))

    deps = section_items("dependencies")
    base = section_items("runtime_base")

    # runtime_base re-declares all six base deps — dedupe, then sort by
    # package name (before any version specifier), the order upstream asks for.
    merged = list(dict.fromkeys(deps + base))

    # Upstream gap: the 0.5.18 import chain pulls `xgrammar` unconditionally
    # yet pyproject_other.toml declares it only under runtime_common — a
    # srt_empty-based wheel could not `import sglang.srt.entrypoints.engine`
    # without it. Pin to the same ==0.2.1 upstream declares.
    if not any(re.split(r'[<=>!~\[\s]', s)[0].lower() == 'xgrammar'
               for s in merged):
        merged.append('xgrammar==0.2.1')

    merged.sort(key=lambda s: re.sub(r'[<=>!~\[\s].*$', '', s).lower())

    rendered = 'dependencies = ["' + '", "'.join(merged) + '"]'
    text, n = re.subn(r'^dependencies\s*=\s*\[.*?\]', rendered, text,
                      count=1, flags=re.M | re.S)
    if n != 1:
        raise SystemExit(f"merge-runtime-base: failed to rewrite `dependencies` in {path}")
    open(path, "w").write(text)

    print(f"  dependencies: {len(deps)} -> {len(merged)} after merging runtime_base")
    return 0


if __name__ == "__main__":
    sys.exit(main())
