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

"""Make ``flagtree.__version__`` report the distribution version.

Upstream ships ``python/flagtree/__init__.py`` as::

    from triton import __version__

so ``print(flagtree.__version__)`` always prints the Triton line the build is
forked from (e.g. ``3.6.0``) — never the wheel's own version. A FlagTree wheel
built by this repo carries that version (``0.7.1.dev20261015``), so the answer
to "which FlagTree is this?" is already in the dist-info; this patch just points
the module at it.

The commit a build came from is a separate fact and lives in the same dist-info
as a ``Project-URL: Source-Commit`` line (``pip show -v``); this patch does not
read it, so there is one place to look for it rather than two.

Applied to the clone inside the build, before ``pip wheel`` — the fork is not
modified. Reading dist-info at import (rather than stamping a version file at
build time) keeps FlagTree's version rule in exactly one place, its ``setup.py``.

Reads FLAGTREE_WHEEL_NAME (default ``flagtree``) and bakes it in as a literal:
the module is always imported as ``flagtree``, but the daily line publishes the
distribution under a per-backend name (``flagtree-nvidia``).

Usage: ``patch-flagtree-version.py <flagtree-source-dir>``
"""

import os
import re
import sys
from pathlib import Path

ANCHOR = "from triton import __version__"
MARKER = "# build-infra: report the distribution version"

TEMPLATE = '''{marker}
try:
    from importlib import metadata as _metadata

    __version__ = _metadata.version("{dist}")
except Exception:  # source tree, or an interpreter without dist metadata
{anchor}
'''


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch-flagtree-version.py <flagtree-source-dir>", file=sys.stderr)
        return 2

    module = Path(sys.argv[1]) / "python" / "flagtree" / "__init__.py"
    if not module.is_file():
        print(f"ERROR: {module} not found", file=sys.stderr)
        return 1

    source = module.read_text()
    if MARKER in source:
        # Idempotent: a rebuild over an already-patched tree is a no-op.
        print(f">>> {module} is already patched")
        return 0
    if source.count(ANCHOR) != 1:
        # Upstream moved on. Fail loudly rather than publish a wheel whose
        # __version__ silently stays at the Triton line.
        print(f"ERROR: {module} does not hold exactly one {ANCHOR!r} line", file=sys.stderr)
        return 1

    dist = os.environ.get("FLAGTREE_WHEEL_NAME") or "flagtree"
    patched = source.replace(
        ANCHOR,
        TEMPLATE.format(marker=MARKER, dist=dist, anchor="    " + ANCHOR),
    )
    if not re.search(r'__version__ = _metadata\.version\("' + re.escape(dist) + r'"\)', patched):
        print("ERROR: patch did not land", file=sys.stderr)
        return 1

    module.write_text(patched)
    print(f">>> {module}: __version__ -> {dist} distribution version")
    return 0


if __name__ == "__main__":
    sys.exit(main())
