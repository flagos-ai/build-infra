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

"""Image version tag from configs.yaml.

configs.yaml declares the stack version::

    version: "2.1.2"

image_version() returns that value verbatim::

    2.1.2

During a release cycle every backend shares the same flat tag
(``flagos-base-{name}:{version}``) and rebuilt images overwrite it. An
earlier design appended a per-backend ``-N`` affix (commits to
``base/<name>`` since the release tag) so a stale image was visible from
its tag alone; that proved confusing to users and was dropped. Whether a
pushed image reflects HEAD is answered instead by
``scripts/base_image_status.py``, which reads the OCI labels stamped on
the image (see build_base.py) and diffs the corresponding containerfile.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def _load_version(repo_root: Path) -> str | None:
    """Read ``version:`` from configs.yaml."""
    cfg = repo_root / "configs.yaml"
    if not cfg.is_file():
        return None
    with open(cfg) as f:
        data = yaml.safe_load(f) or {}
    return data.get("version") or None


def image_version(repo_root: Path) -> str | None:
    """Return the stack version tag for images, e.g. ``"2.1.2"``.

    Returns None when configs.yaml has no version field.
    """
    return _load_version(repo_root)
