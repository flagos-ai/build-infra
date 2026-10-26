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

"""Native-wheel identity of a vllm-plugin-FL backend.

A backend installs `vllm-plugin-fl==<public>` (the pure-python wheel) or
`<public>+<label>` (the native `vllm_fl._C` wheel that its own runtime image
built). The default fan-out publishes several builds under ONE public version
on one index — nvidia carries cuda12.8 and cuda13.3, metax carries maca3.7.2.1
and maca3.8.1.3, and every native index also carries the pure wheel — so a bare
`==<public>` pin silently resolves to whichever local label is newest, i.e. to
another backend's `.so`. The label is what keeps the install honest; membership
in packaging/vllm/plugin-build.yaml is what says which backends need one.

One resolver, shared by the wheel build (which labels the wheel), the app build
(which pins it) and the docs + verify side (which read the pin back), so the
four can never disagree about what a backend installs. `pin` is idempotent, so
a pin can be passed straight back in — the verify driver forwards a cell's own
pin to the build workflow unchanged.

Two forms of the same backend, and the difference is deliberate:

  pin()     what the image INSTALLS — carries the label, so pip picks this
            backend's build.
  public()  what the image TAG carries — the public version only. A tag states
            which plugin release shipped, not which native build of it was
            packaged; the backend is already named by the repository segment,
            and a label in the tag breaks two consumers that parse the tag's
            suffix (the verify driver's pin recovery and the record step's
            PR-head drift gate).

The fold is hand-rolled rather than imported from `packaging`: this runs in the
docs pipeline, which installs pyyaml and nothing else. It reproduces PEP 440
local normalization for the label shapes backend keys produce (lowercase,
`-`/`_` to `.`, all-numeric segments lose leading zeros: dtk26.04 -> dtk26.4)
and refuses any input it cannot fold into a valid label instead of guessing.

Usage:
    python scripts/vllm_plugin.py label  nvidia-cuda12.8
    python scripts/vllm_plugin.py pin    nvidia-cuda12.8 0.3.0
    python scripts/vllm_plugin.py public nvidia-cuda12.8 0.3.0+cuda12.8
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_BUILD = Path("packaging") / "vllm" / "plugin-build.yaml"

# PEP 440 local label: alphanumeric segments separated by dots. Anything that
# does not fold into this shape is a backend key this module does not
# understand — fail loudly rather than emit a pin that cannot install.
_LABEL_RE = re.compile(r"^[a-z0-9]+(?:\.[a-z0-9]+)*$")

_backends_cache: dict[Path, set[str]] = {}


def _backends(repo_root: Path = REPO_ROOT) -> set[str]:
    """Backend keys that build the native wheel — presence IS the selector."""
    if repo_root not in _backends_cache:
        with (repo_root / PLUGIN_BUILD).open() as f:
            cfg = yaml.safe_load(f) or {}
        _backends_cache[repo_root] = set((cfg.get("backends") or {}).keys())
    return _backends_cache[repo_root]


def _fold_segment(text: str) -> str:
    segs = [s for s in re.split(r"[.\-_]", text.lower()) if s]
    return ".".join(str(int(s)) if s.isdigit() else s for s in segs)


def label(backend: str, repo_root: Path = REPO_ROOT) -> str:
    """The backend's native wheel label, or "" for a pure-python backend.

    The vendor prefix is dropped — the wheel already lands on a per-vendor
    index, so `+metax.maca3.7.2.1` would carry the vendor twice.
    """
    if backend not in _backends(repo_root):
        return ""
    bare = backend.split("-", 1)[1] if "-" in backend else backend
    folded = _fold_segment(bare)
    if not _LABEL_RE.match(folded):
        raise ValueError(
            f"native backend {backend!r} folds to {folded!r}, which is not a "
            f"PEP 440 local label — add an explicit label or fix the backend key"
        )
    return folded


def _has_label(version: str, lab: str) -> bool:
    return version.endswith(f"+{lab}") or version.endswith(f".{lab}")


def pin(backend: str, version: str, repo_root: Path = REPO_ROOT) -> str:
    """The exact vllm-plugin-fl version this backend installs (idempotent).

    The temp version form already carries a `+g<sha>.d<date>` local label and a
    second `+` is invalid, so the label extends it with a `.`; the released tag
    form has no local label, so the label is added as one with `+`.
    """
    lab = label(backend, repo_root)
    if not lab or _has_label(version, lab):
        return version
    return f"{version}{'.' if '+' in version else '+'}{lab}"


def public(backend: str, version: str, repo_root: Path = REPO_ROOT) -> str:
    """The tag-side form: the version with this backend's label stripped."""
    lab = label(backend, repo_root)
    if not lab:
        return version
    for sep in ("+", "."):
        if version.endswith(f"{sep}{lab}"):
            return version[: -len(lab) - len(sep)]
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("form", choices=["pin", "public", "label"])
    parser.add_argument("backend", help="backend key, e.g. nvidia-cuda12.8")
    parser.add_argument("version", nargs="?",
                        help="plugin version (omit for the `label` form)")
    args = parser.parse_args()

    if args.form == "label":
        print(label(args.backend))
        return
    if args.version is None:
        sys.exit(f"Error: the {args.form} form needs a version")
    print(pin(args.backend, args.version) if args.form == "pin"
          else public(args.backend, args.version))


if __name__ == "__main__":
    main()
