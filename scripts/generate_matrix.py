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

"""Generate a GitHub Actions build matrix for the FlagOS base images.

Reads configs.yaml (the source of truth for vendors/backends) and the runner
mapping in .github/build-config.yml, then emits a matrix of the base images
that are actually buildable — i.e. each vendor/backend that has a
base/{vendor}-{backend} containerfile.

Output (compact JSON on stdout):
    {"include": [{"name": "nvidia-cuda12.8", "runson": "..."}, ...]}

Usage:
    python scripts/generate_matrix.py                       # all buildable backends
    python scripts/generate_matrix.py nvidia-cuda12.8 metax-maca3.7.2.1  # subset

Backends without a base/ file (e.g. thead-ppu2.0.0, spacemit-spacemit) are
skipped with a note on stderr.
"""

import json
import sys
from pathlib import Path

import yaml


def find_repo_root() -> Path:
    d = Path(__file__).resolve().parent.parent
    if (d / "base").is_dir():
        return d
    sys.exit("Error: cannot locate repository root (base/ not found)")


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def buildable_backends(repo_root: Path, configs: dict):
    """Yield (name, has_base_file) for every configs.yaml backend.

    name is "{vendor}-{backend}", matching the base/ containerfile name.
    """
    for vendor, backends in configs.get("vendors", {}).items():
        for backend in backends:
            name = f"{vendor}-{backend}"
            yield name, (repo_root / "base" / name).is_file()


def runson_for(name: str, runners: dict) -> str:
    """Return the runner as a JSON-encoded array string.

    A reusable workflow's `runs-on` must come from a string input, so we pass
    the labels JSON-encoded and `fromJSON` them in imagebuild.yml. A bare label
    is normalised to a single-element array (e.g. "ubuntu-latest" -> ["ubuntu-latest"]).
    """
    overrides = runners.get("overrides") or {}
    val = overrides.get(name, runners.get("default", "ubuntu-latest"))
    if isinstance(val, str):
        val = [val]
    return json.dumps(val)


def main():
    requested = sys.argv[1:]  # optional subset of names

    repo_root = find_repo_root()
    configs = load_yaml(repo_root / "configs.yaml")

    config_path = repo_root / ".github" / "build-config.yml"
    config = load_yaml(config_path) if config_path.exists() else {}
    runners = config.get("runners") or {}

    all_backends = list(buildable_backends(repo_root, configs))
    buildable = {name for name, has_file in all_backends if has_file}
    skipped = [name for name, has_file in all_backends if not has_file]

    if skipped:
        print(
            f"note: skipping backends with no base/ file: {', '.join(sorted(skipped))}",
            file=sys.stderr,
        )

    if requested:
        unknown = [n for n in requested if n not in buildable]
        for n in unknown:
            print(f"warning: '{n}' is not a buildable base backend, ignoring",
                  file=sys.stderr)
        selected = [n for n in requested if n in buildable]
    else:
        selected = [name for name, has_file in all_backends if has_file]

    include = [{"name": name, "runson": runson_for(name, runners)} for name in selected]
    print(json.dumps({"include": include}))


if __name__ == "__main__":
    main()
