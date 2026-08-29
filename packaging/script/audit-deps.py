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

"""Audit built wheels' declared dependencies against a critical package list.

The runtime image bakes a pinned matrix (torch / triton / flag_gems / …) and
app images install wheels single-step, so a wheel that *declares* one of
those packages gives pip a reason to resolve/upgrade it and silently drift
the matrix. This gate reads each wheel's METADATA ``Requires-Dist`` and fails
the build when a watched package is declared.

The watched set is product-line specific (vllm's critical list and sglang's
differ, e.g. numpy is critical for vllm but a legal sglang dependency), so
the script ships no default list — callers pass theirs with ``--watch``.
A watch entry ending in ``*`` is a prefix match (e.g. ``nvidia-*`` matches
``nvidia-cudnn-cu13``, ``flashinfer*`` matches ``flashinfer-python``).

Usage:
    python3 audit-deps.py --watch pkg [--watch pkg ...] wheel.whl [...]
    python3 audit-deps.py --watch pkg [--watch pkg ...] --pkginfo PKG-INFO

Exit status: 0 = clean, 1 = a watched package is declared.
"""

import argparse
import re
import sys
import zipfile

# PEP 508 distribution name: [A-Za-z0-9._-]+ — the name stops at the first
# '[', '<', '>', '=', '!', '~', '(', or space (extras / version / marker).
_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")


def _requires_dist(lines: list[str]) -> list[str]:
    """Extract bare package names from METADATA / PKG-INFO Requires-Dist lines.

    A line is ``Requires-Dist: name[extras]>=spec; marker`` — drop the label,
    extras, version specifier, and environment marker, leaving just the name.
    """
    names = []
    for ln in lines:
        if ln.startswith("Requires-Dist:"):
            m = _NAME_RE.match(ln.split(":", 1)[1].lstrip())
            if m:
                names.append(m.group(0))
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--watch",
        action="append",
        metavar="PKG",
        help="package name to fail on if declared (repeatable; trailing "
             "'*' = prefix match) — required, no product default",
    )
    parser.add_argument(
        "--pkginfo",
        metavar="FILE",
        help="audit a PEP 566 metadata text file (an sdist's PKG-INFO) "
             "instead of wheels — the same Requires-Dist gate for source "
             "tarballs (build-sdist.sh)",
    )
    parser.add_argument("wheels", nargs="*", metavar="wheel.whl")
    args = parser.parse_args()

    if not args.watch:
        parser.error("at least one --watch is required — the script ships "
                     "no product-specific default list")
    if args.pkginfo and args.wheels:
        parser.error("give either --pkginfo or wheel paths, not both")
    if not args.pkginfo and not args.wheels:
        parser.error("no input: pass at least one wheel.whl, or --pkginfo FILE")

    watch = {w.lower().replace("_", "-") for w in args.watch}
    prefixes = sorted(p[:-1] for p in watch if p.endswith("*"))
    exact = watch - {p + "*" for p in prefixes}
    failed = False

    artifacts = [args.pkginfo] if args.pkginfo else args.wheels
    for artifact in artifacts:
        requires: list[str] = []
        if args.pkginfo:
            requires = _requires_dist(open(artifact))
        else:
            with zipfile.ZipFile(artifact) as zf:
                for name in zf.namelist():
                    if name.endswith(".dist-info/METADATA"):
                        requires = _requires_dist(
                            zf.read(name).decode().splitlines()
                        )
                        break

        declared = {r.lower().replace("_", "-") for r in requires}
        hits = sorted(
            (exact & declared)
            | {d for d in declared if any(d.startswith(p) for p in prefixes)}
        )
        print(f"{artifact}: requires {len(requires)} packages "
              f"(watchlist hits: {', '.join(hits) if hits else 'none'})")
        if hits:
            failed = True
            for pkg in hits:
                print(f"  FAIL: declares critical package {pkg} — "
                      f"an app-image single-step install would drift the "
                      f"runtime matrix. Drop it from the wheel's "
                      f"dependencies; the image provides it.",
                      file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
