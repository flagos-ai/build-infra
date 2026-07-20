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

"""Per-backend image version from configs.yaml + git.

configs.yaml declares the stack version::

    version: "2.1.1"

image_version() counts git commits to ``base/<name>`` since tag
``v2.1.1``, producing::

    2.1.1        (n=0, no changes since the tag)
    2.1.1-3      (3 commits to this Containerfile since v2.1.1)
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _load_version(repo_root: Path) -> str | None:
    """Read ``version:`` from configs.yaml."""
    import yaml

    cfg = repo_root / "configs.yaml"
    if not cfg.is_file():
        return None
    with open(cfg) as f:
        data = yaml.safe_load(f) or {}
    return data.get("version") or None


def image_version(repo_root: Path, name: str) -> str | None:
    """Compute the per-backend image version tag.

    ``name`` is the containerfile name (e.g. ``"nvidia-cuda12.8"``).

    Returns ``"X.Y.Z-n"`` when there are *n* commits to ``base/<name>``
    since tag ``vX.Y.Z``, or just ``"X.Y.Z"`` when n=0.  Returns None
    when configs.yaml has no version field.
    """
    label_ver = _load_version(repo_root)
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

    if r.returncode != 0:
        return label_ver

    n = int(r.stdout.strip())
    return f"{label_ver}-{n}" if n else label_ver
