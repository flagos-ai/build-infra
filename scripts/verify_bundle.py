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

from __future__ import annotations

"""Bundle verify helpers (FEP-0139 closure equality).

Called by scripts/verify_bundle.sh with --check-wheels: re-derives the
expected wheel set from configs.yaml + packaging/<app>/app-versions.yaml using
the SAME resolver build_bundle.py uses, then asserts the bundle's wheelhouse
covers it. Because the resolver is shared, the build cannot silently omit a
runtime or app pin.
"""

import argparse
import re
import sys
import tarfile
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_bundle import load_app_manifest, repo_root
from build_runtime import load_yaml, resolve_backend, resolve_build_args


def bundle_parts(bundle_name: str) -> tuple[str, str]:
    """Split flagos-<app>-<vendor>-<backend>-<version> into (app, backend-key).

    app is a single token (vllm); version is the last token; everything
    between is the {vendor}-{backend} key (which may itself carry hyphens,
    e.g. nvidia-cuda12.8 or ascend-cann8.5.0-910c).
    """
    parts = bundle_name.split("-")
    if len(parts) < 4 or parts[0] != "flagos":
        sys.exit(f"Error: unexpected bundle name {bundle_name!r}")
    app = parts[1]
    backend = "-".join(parts[2:-1])
    return app, backend


def expected_reqs(bundle_name: str) -> tuple[list[str], dict[str, list[str]]]:
    app, backend_key = bundle_parts(bundle_name)
    configs = load_yaml(repo_root() / "configs.yaml")
    backend_info, _vendor, _backend = resolve_backend(backend_key, configs)
    args = resolve_build_args(backend_info, _vendor, _backend, configs, repo_root())
    flaggems = configs.get("flaggems", "")

    runtime_top = args["DEPS"].split() + args["RUNTIME_PREREQS"].split() \
        + [f"flag_gems=={flaggems}"]
    deltas: dict[str, list[str]] = {}
    app_deps = backend_info.get("deps_app") or {}
    versions = load_app_manifest(app).get("versions") or {}
    for ver, pins in versions.items():
        key = f"{app}{ver}"
        if key not in app_deps:
            continue
        deltas[ver] = list(pins) + list(app_deps[key])
    return runtime_top, deltas


def norm_spec(spec: str) -> tuple[str, str | None]:
    """Return (distribution-name, exact-version-or-None) for a requirement spec."""
    name = re.split(r"[<>=!~ ]", spec)[0].strip().lower().replace("_", "-")
    if "==" in spec:
        ver = spec.split("==", 1)[1].strip()
        return name, ver
    return name, None


def wheel_name_and_version(fname: str) -> tuple[str, str]:
    """Return (canonical-dist-name, version) from a PEP 427 wheel filename.

    Local-version wheels (torch-2.10.0+cu128) URL-encode the '+' as %2B in the
    filename — as both the report URLs and the wheelhouse store them — so the
    raw split-by-'-' name/version would compare "2.10.0%2Bcu128" against the
    pin's "2.10.0+cu128" and report every vendor wheel missing. Unquote first,
    then match version on the decoded segment that carries the build tag.
    """
    stem = unquote(fname[:-len(".whl")])
    parts = stem.split("-")
    name = parts[0].lower().replace("_", "-")
    # version is the segment after the name, up to the next '-' (build/python).
    version = parts[1] if len(parts) > 1 else ""
    return name, version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tarball")
    parser.add_argument("--check-wheels", action="store_true",
                        help="Assert the wheelhouse covers the re-derived closure")
    args = parser.parse_args()

    tarball = Path(args.tarball)
    bundle_name = tarball.name[:-len(".tar.gz")]
    runtime_top, deltas = expected_reqs(bundle_name)

    if not args.check_wheels:
        print("runtime:", " ".join(runtime_top))
        for ver in sorted(deltas):
            print(f"  {ver}:", " ".join(deltas[ver]))
        return

    # Map wheel filenames → (distribution name, version) inside the archive.
    wheel_names: dict[str, str] = {}
    wheel_versions: dict[str, str] = {}
    with tarfile.open(tarball) as tf:
        for member in tf.getmembers():
            if not member.name.endswith(".whl"):
                continue
            fname = member.name.rsplit("/", 1)[-1]
            name, version = wheel_name_and_version(fname)
            wheel_names[fname] = name
            wheel_versions[fname] = version

    # A wheel matching spec s is present iff some wheel's dist name == s's dist
    # name AND (s has no exact pin, or any wheel of that name carries s's
    # version). Check by name first (cheap), then by version.
    by_name: dict[str, list[str]] = {}
    for fname, dist in wheel_names.items():
        by_name.setdefault(dist, []).append(fname)

    def has_version(filenames: list[str], want: str) -> bool:
        return any(wheel_versions[f] == want for f in filenames)

    missing: list[str] = []
    for spec in runtime_top:
        name, ver = norm_spec(spec)
        if name not in by_name:
            missing.append(f"{spec} (runtime)")
        elif ver is not None and not has_version(by_name[name], ver):
            missing.append(f"{spec} (runtime, version {ver})")
    for ver, reqs in deltas.items():
        for spec in reqs:
            name, v = norm_spec(spec)
            if name not in by_name:
                missing.append(f"{spec} ({ver})")
            elif v is not None and not has_version(by_name[name], v):
                missing.append(f"{spec} ({ver}, version {v})")

    if missing:
        print("ERROR: wheelhouse is missing wheels for:")
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)

    print(f"OK: wheelhouse covers {len(runtime_top)} runtime + "
          f"{sum(len(r) for r in deltas.values())} app pins across "
          f"{len(wheel_names)} wheel files")


if __name__ == "__main__":
    main()
