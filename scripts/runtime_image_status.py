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

"""Report which runtime images are outdated relative to what is pushed to Harbor.

The runtime twin of ``scripts/base_image_status.py``. Runtime images are
built on demand (manual CI trigger or ``scripts/build_runtime.py``) and share
one flat Harbor tag per release cycle, ``flagos-runtime-{name}:{version}`` —
rebuilt images overwrite the same tag. This script answers "is the pushed
image behind HEAD?" *without building anything*, by reading the OCI labels
stamped by the runtime build paths:

    org.opencontainers.image.revision   git commit the image was built from
    org.opencontainers.image.version    image version tag at build time
    flagos.flaggems                     FlagGems wheel version installed
    flagos.base                         base image ref it was built from

Each backend is reported as TWO rows: the normal runtime image (``{name}``)
and the ``-build`` build-platform variant (``{name}-build``, produced with
NO_FLAGGEMS for cpp wheel compilation). Both live in the same
``flagos-runtime-{name}`` repo, the latter under a ``-build`` tag suffix.
``-build`` images carry the same provenance labels except ``flagos.flaggems``
(no flag_gems is installed by design), so that check is skipped for them.

A backend is OUTDATED when any of:

  - the image's ``version`` label differs from the tag being inspected
    (normally configs.yaml ``version:`` — the tag changed, so the image
    must be rebuilt to carry the new tag),
  - the image's ``flagos.flaggems`` differs from configs.yaml ``flaggems:``
    (normal rows only — ``-build`` images install no flag_gems),
  - runtime build inputs changed since that commit (``runtime/Containerfile``,
    ``scripts/build_runtime.py``), or
  - runtime-relevant configs.yaml fields changed since that commit. The
    comparison is per backend: global fields (``runtime_prereqs``/``pypi_base``/
    ``pypi_daily``/``mirror``/``base_image_prefix``) affect every build, but
    each backend's own fields (``deps``/``python``/``cmake_backend``/
    ``flagtree``/``triton``/``triton_post_install``/``env.runtime``) only flag
    that backend — a change to cambricon's deps flags only cambricon. Top-level
    ``version``/``flaggems`` are excluded: the tag and flaggems label checks
    cover those. The detail names exactly which fields changed.

Note that override builds (``--flaggems``, ``--base-image``, ``--tag``, CI
``inputs.flaggems``) legitimately read OUTDATED — they deviate from
configs.yaml, which is the source of truth. Script-only changes to
``scripts/generate_matrix.py`` (the CI twin of build_runtime.py's arg
resolution) are deliberately not a signal: a base-matrix-only change there
would flag every backend, and its config-driven output is already covered by
the per-backend config check.

Status values:
    UP_TO_DATE  pushed :{tag} reflects HEAD's build inputs and config
    OUTDATED    build inputs and/or config changed since the pushed image
    NOT_BUILT   no :{tag} tag in Harbor yet — must build
    UNKNOWN     could not determine (see detail column)

Usage:
    HARBOR_USER=... HARBOR_PW=... python scripts/runtime_image_status.py
    python scripts/runtime_image_status.py --json
    python scripts/runtime_image_status.py nvidia-cuda12.8 cambricon-neuware4.7.2
    python scripts/runtime_image_status.py --tag 2.1.2

Requires a checkout with the full history (fetch-depth: 0) so the
revision stamped on a pushed image is resolvable locally.

Exit code is always 0 — this is an informational overview.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
from collections import Counter
from pathlib import Path

import yaml

from base_image_status import auth_header, image_labels

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that determine runtime image content (Containerfile + arg resolution).
# scripts/generate_matrix.py — the CI twin of build_runtime.py's arg
# resolution — is deliberately excluded: a base-matrix-only change there would
# flag every backend, and its config-driven output is already covered per
# backend by runtime_config_snapshot. scripts/version.py only reads configs.yaml
# version:, which the tag/version-label check covers.
RUNTIME_BUILD_INPUTS = [
    "runtime/Containerfile",
    "scripts/build_runtime.py",
]

# Global configs.yaml fields consumed by the runtime build paths.
RUNTIME_CONFIG_GLOBALS = (
    "runtime_prereqs",
    "pypi_base",
    "pypi_daily",
    "mirror",
    "base_image_prefix",
)

# Per-backend fields consumed by the runtime build paths.
RUNTIME_BACKEND_KEYS = (
    "deps",
    "python",
    "cmake_backend",
    "flagtree",
    "triton",
    "triton_post_install",
)


def load_context() -> tuple[str, str, str, list[str], str]:
    """Return (host, runtime-project, version, names, flaggems)."""
    configs = yaml.safe_load((REPO_ROOT / "configs.yaml").read_text()) or {}
    build = yaml.safe_load((REPO_ROOT / ".github" / "build-config.yml").read_text()) or {}
    registry = build.get("registry") or {}
    host = registry.get("host", "")
    project = (registry.get("prefixes") or {}).get("runtime", "flagos-runtime")
    version = str(configs.get("version", "") or "")
    flaggems = str(configs.get("flaggems", "") or "")

    vendors = configs.get("vendors") or {}
    names = sorted(f"{v}-{b}" for v, backends in vendors.items() for b in backends)
    return host, project, version, names, flaggems


def build_inputs_changed(revision: str) -> bool | None:
    """True if any runtime build input changed since `revision`; None if unknown."""
    r = subprocess.run(
        ["git", "diff", "--quiet", f"{revision}..HEAD", "--", *RUNTIME_BUILD_INPUTS],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    if r.returncode == 128:  # revision not present in this clone
        return None
    return r.returncode == 1  # 0 = no diff, 1 = diff


def build_inputs_commits(revision: str) -> int | None:
    """Number of commits touching runtime build inputs since `revision`; None if unknown."""
    r = subprocess.run(
        ["git", "rev-list", "--count", f"{revision}..HEAD", "--", *RUNTIME_BUILD_INPUTS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    return int(r.stdout.strip())


def configs_at(revision: str) -> dict | None:
    """configs.yaml at `revision` as a parsed dict; None if the commit is unknown."""
    r = subprocess.run(
        ["git", "show", f"{revision}:configs.yaml"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    return yaml.safe_load(r.stdout) or {}


def runtime_config_snapshot(configs: dict, vendor: str, backend: str) -> dict:
    """Runtime-relevant configs.yaml fields for a backend.

    Global fields plus the backend subtree restricted to the keys the runtime
    build paths consume. ``env`` is restricted to ``env.runtime`` (compared as
    a parsed dict, not the serialized KEY=value form). Top-level
    ``version``/``flaggems`` are excluded — the tag and flagos.flaggems label
    checks cover those.
    """
    snap = {k: configs.get(k) for k in RUNTIME_CONFIG_GLOBALS}
    bi = ((configs.get("vendors") or {}).get(vendor) or {}).get(backend) or {}
    snap["backend"] = {k: bi.get(k) for k in RUNTIME_BACKEND_KEYS}
    snap["backend"]["env_runtime"] = (bi.get("env") or {}).get("runtime")
    return snap


def config_drift_reasons(old: dict, new: dict) -> list[str]:
    """Snapshot fields that differ between ``old`` and ``new``, human-readable.

    Field names come from RUNTIME_CONFIG_GLOBALS / RUNTIME_BACKEND_KEYS (the
    keys the runtime build paths actually consume), so a change to, say, only
    cambricon's ``deps`` yields ``["deps"]`` for that backend and nothing for
    any other.
    """
    reasons = []
    for key in RUNTIME_CONFIG_GLOBALS:
        if old.get(key) != new.get(key):
            reasons.append(key)
    old_backend = old.get("backend") or {}
    new_backend = new.get("backend") or {}
    for key in RUNTIME_BACKEND_KEYS:
        if old_backend.get(key) != new_backend.get(key):
            reasons.append(key)
    if old_backend.get("env_runtime") != new_backend.get("env_runtime"):
        reasons.append("env.runtime")
    return reasons


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("backends", nargs="*", help="limit to these backends (default: all)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument("--tag", help="Harbor tag to inspect (default: configs.yaml version)")
    args = ap.parse_args()

    host, project, version, names, flaggems = load_context()
    if not host:
        sys.exit("registry.host missing from .github/build-config.yml")
    if not version:
        sys.exit("configs.yaml has no version: field")
    tag = args.tag or version
    auth = auth_header()
    current_configs = yaml.safe_load((REPO_ROOT / "configs.yaml").read_text()) or {}

    if args.backends:
        wanted = set(args.backends)
        missing = wanted - set(names)
        if missing:
            sys.exit(f"unknown backend(s): {', '.join(sorted(missing))}")
        names = [n for n in names if n in wanted]

    def inspect_row(
        display_name: str,
        repo: str,
        query_tag: str,
        expected_version: str,
        is_build: bool,
        vendor: str,
        backend: str,
    ) -> dict:
        """Check one (backend, variant) row against Harbor + git history.

        ``is_build`` selects the ``-build`` (NO_FLAGGEMS) variant: it carries
        no ``flagos.flaggems`` label by design, so that check is skipped, and
        its ``version`` label is the plain stack version (the ``-build`` is a
        tag suffix, not a version).
        """
        entry = {"name": display_name, "tag": query_tag, "built": "", "status": "", "detail": ""}
        try:
            labels = image_labels(host, repo, query_tag, auth)
        except urllib.error.URLError as e:
            entry.update(status="UNKNOWN", detail=f"registry unreachable: {e.reason}")
            return entry
        except Exception as e:  # noqa: BLE001
            entry.update(status="UNKNOWN", detail=str(e))
            return entry

        if labels is None:
            entry.update(status="NOT_BUILT")
            return entry

        # Legacy images (built before label stamping) carry no flagos.* labels —
        # only labels inherited from the base image. The discriminator: normal
        # rows must have flagos.flaggems; -build rows have no flaggems by design
        # but do carry flagos.base (stamped since the same change), so flagos.base
        # is their marker. Checked before the revision check so legacy images get
        # the authoritative message.
        marker = "flagos.base" if is_build else "flagos.flaggems"
        if not labels.get(marker, ""):
            entry.update(
                status="UNKNOWN",
                detail="built before label stamping — rebuild to track status",
            )
            return entry

        revision = labels.get("org.opencontainers.image.revision", "")
        built_version = labels.get("org.opencontainers.image.version", "")
        entry["built"] = revision[:12]
        if not revision:
            entry.update(status="UNKNOWN", detail="image has no revision label")
            return entry

        changed = build_inputs_changed(revision)
        if changed is None:
            entry.update(
                status="UNKNOWN",
                detail=f"commit {revision[:12]} not in local clone (need fetch-depth: 0)",
            )
            return entry

        old_configs = configs_at(revision)
        if old_configs is None:
            entry.update(
                status="UNKNOWN",
                detail=f"commit {revision[:12]} not in local clone (need fetch-depth: 0)",
            )
            return entry

        reasons = []
        if built_version and built_version != expected_version:
            reasons.append(f"tag: built as {built_version}, expected {expected_version}")
        if not is_build:
            built_flaggems = labels.get("flagos.flaggems", "")
            if flaggems and built_flaggems != flaggems:
                reasons.append(f"flaggems: built {built_flaggems}, expected {flaggems}")
        if changed:
            n = build_inputs_commits(revision)
            count = f" ({n} commit(s))" if n is not None else ""
            reasons.append(f"build inputs: changed since {revision[:12]}{count}")
        drift = config_drift_reasons(
            runtime_config_snapshot(old_configs, vendor, backend),
            runtime_config_snapshot(current_configs, vendor, backend),
        )
        if drift:
            reasons.append(
                f"configs.yaml: {', '.join(drift)} changed since {revision[:12]}"
            )
        if not reasons and not built_version:
            # Stamped image but no version label to verify against the tag.
            reasons.append("no version label on image")

        entry["status"] = "OUTDATED" if reasons else "UP_TO_DATE"
        entry["detail"] = "; ".join(reasons)
        return entry

    results = []
    for name in names:
        vendor, backend = name.split("-", 1)
        repo = f"{project}/flagos-runtime-{name}"
        results.append(inspect_row(name, repo, tag, tag, False, vendor, backend))
        results.append(inspect_row(f"{name}-build", repo, f"{tag}-build", tag, True, vendor, backend))

    if args.json:
        print(json.dumps(results, indent=2))
        return

    header = f"{'backend':<28} {'tag':<13} {'built':<13} status"
    print(header)
    print("-" * len(header))
    for r in results:
        detail = f"  ({r['detail']})" if r.get("detail") else ""
        print(f"{r['name']:<28} {r['tag']:<13} {r['built']:<13} {r['status']}{detail}")
    counts = Counter(r["status"] for r in results)
    summary = ", ".join(f"{n} {s}" for s, n in counts.most_common())
    print(f"\n{len(results)} rows: {summary}")


if __name__ == "__main__":
    main()
