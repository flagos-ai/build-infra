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

A backend listed in packaging/vllm/plugin-build.yaml installs the native wheel
its own runtime image built (`0.3.0+cuda12.8`); every other backend installs
the pure-python one (`0.3.0`). The label is what keeps the install honest: on
one index a bare `==0.3.0` resolves to whichever local build is newest, which
may be another backend's `.so`.

The pin and the image tag are deliberately different: the pin carries the
label, the tag carries the public version only — the repository segment already
names the backend, and a label in the suffix breaks the two consumers that
parse it (the verify driver's pin recovery, the record step's plugin-commit
drift gate). Shared by the wheel build, the app build, the docs pages and the
verify driver, so the two forms cannot drift.

    python scripts/vllm_plugin.py label  nvidia-cuda12.8
    python scripts/vllm_plugin.py pin    nvidia-cuda12.8 0.3.0
    python scripts/vllm_plugin.py public nvidia-cuda12.8 0.3.0+cuda12.8
"""

import sys
from pathlib import Path

import yaml

PLUGIN_BUILD = (Path(__file__).resolve().parent.parent
                / "packaging" / "vllm" / "plugin-build.yaml")


def label(backend: str) -> str:
    """The backend's native label, or "" if it builds the pure-python wheel.

    The vendor prefix is dropped — the wheel already lands on a per-vendor
    index — and the rest folds to a PEP 440 local label (dtk26.04 -> dtk26.4).
    The fold is hand-rolled because the docs pipeline installs pyyaml and
    nothing else.
    """
    with PLUGIN_BUILD.open() as f:
        if backend not in (yaml.safe_load(f) or {}).get("backends", {}):
            return ""
    segs = backend.split("-", 1)[-1].lower().replace("-", ".").split(".")
    return ".".join(str(int(s)) if s.isdigit() else s for s in segs if s)


def pin(backend: str, version: str) -> str:
    """The version this backend installs. Idempotent: a pin may be passed back
    in, which the verify driver does with the cell's own pin."""
    lab = label(backend)
    if not lab or version.endswith((f"+{lab}", f".{lab}")):
        return version
    # A temp version already carries a `+g<sha>.d<date>` label (a second `+` is
    # invalid), so the label extends it with a `.`; the tag form gets a `+`.
    return f"{version}{'.' if '+' in version else '+'}{lab}"


def public(backend: str, version: str) -> str:
    """The tag-side form: the same version with this backend's label removed."""
    lab = label(backend)
    for sep in ("+", "."):
        if lab and version.endswith(f"{sep}{lab}"):
            return version[: -len(lab) - 1]
    return version


def main() -> None:
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in ("label", "pin", "public"):
        sys.exit(__doc__)
    form, backend = sys.argv[1], sys.argv[2]
    if form == "label":
        print(label(backend))
    elif form == "pin":
        print(pin(backend, sys.argv[3]))
    else:
        print(public(backend, sys.argv[3]))


if __name__ == "__main__":
    main()
