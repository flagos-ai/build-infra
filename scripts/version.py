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

"""Base image version computation.

Each base/<vendor>-<backend> Containerfile declares a base repo version label::

    LABEL org.opencontainers.image.version="2.1.1"

image_version() reads that label and counts git commits to the Containerfile
since the corresponding tag (v2.1.1), producing::

    2.1.1        (n=0, no changes since the tag)
    2.1.1-3      (3 commits to this Containerfile since v2.1.1)
"""

import re
import subprocess
from pathlib import Path


_VERSION_LABEL_RE = re.compile(
    r'LABEL\s+org\.opencontainers\.image\.version\s*=\s*"([^"]+)"'
)


def read_version_label(repo_root: Path, name: str) -> str | None:
    """Read the base version label from ``base/<name>`` Containerfile.

    Returns the version string (e.g. ``"2.1.1"``) or None when the
    file is missing or has no version label.
    """
    cf = repo_root / "base" / name
    if not cf.is_file():
        return None
    m = _VERSION_LABEL_RE.search(cf.read_text())
    return m.group(1) if m else None


def image_version(repo_root: Path, name: str) -> str | None:
    """Compute the per-backend image version tag.

    ``name`` is the containerfile name (e.g. ``"nvidia-cuda12.8"``).

    Returns ``"X.Y.Z-n"`` when there are *n* commits to ``base/<name>``
    since tag ``vX.Y.Z``, or just ``"X.Y.Z"`` when n=0.  Returns None
    when the Containerfile has no version label — callers should fall
    back to the old ``git describe`` scheme.
    """
    label_ver = read_version_label(repo_root, name)
    if not label_ver:
        return None

    tag = f"v{label_ver}"
    try:
        r = subprocess.run(
            ["git", "rev-list", "--count", f"{tag}..HEAD", "--", f"base/{name}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return label_ver

    # Tag not reachable (e.g. it still points to an old commit, or doesn't
    # exist yet) — treat as n=0, which is the right answer once the tag is
    # moved to HEAD.
    if r.returncode != 0:
        return label_ver

    n = int(r.stdout.strip())
    return f"{label_ver}-{n}" if n else label_ver
