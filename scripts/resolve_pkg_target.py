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

"""Resolve declarative system-package target metadata for GitHub Actions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "packaging" / "syspkg-targets.yaml"


def load_catalog(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Load and return the system-package target catalog."""
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{config_path} must contain a top-level mapping")
    return data


def _resolve_ref_and_version(
    target: str,
    entry: dict[str, Any],
    fmt_cfg: dict[str, Any],
    requested_ref: str,
) -> tuple[str, str, str]:
    """Resolve effective ref, default_ref, and default_version for a target."""
    default_ref = str(fmt_cfg.get("default_ref", entry.get("default_ref", "")) or "")
    default_ver = str(fmt_cfg.get("default_version", entry.get("default_version", "")) or "")
    eff_ref = requested_ref.strip() or default_ref
    if not eff_ref:
        raise ValueError(
            f"target '{target}' has no pinned release tag in packaging/syspkg-targets.yaml; "
            "pass `ref` explicitly to build a branch or candidate commit"
        )
    return eff_ref, default_ref, default_ver


def resolve_noarch(
    catalog: dict[str, Any],
    fmt: str,
    component: str,
    requested_ref: str = "",
) -> dict[str, str]:
    """Resolve outputs for noarch-deb or noarch-rpm workflows."""
    group = catalog.get("noarch", {})
    entry = group.get(component)
    if not entry or fmt not in entry:
        raise ValueError(f"unknown {fmt} noarch component '{component}'")

    fmt_cfg = entry[fmt]
    eff_ref, default_ref, default_ver = _resolve_ref_and_version(
        component, entry, fmt_cfg, requested_ref
    )
    repo = entry["repo"]
    out = {
        "repo_url": f"https://github.com/flagos-ai/{repo}.git",
        "effective_ref": eff_ref,
        "default_ref": default_ref,
        "default_version": default_ver,
    }
    if fmt == "deb":
        out["script"] = fmt_cfg["script"]
    else:
        out["dockerfile"] = fmt_cfg["dockerfile"]
        out["spec"] = fmt_cfg["spec"]
    return out


def resolve_native(
    catalog: dict[str, Any],
    fmt: str,
    target: str,
    suite: str,
    arch: str,
    requested_suites: str = "",
    requested_arches: str = "",
    requested_ref: str = "",
) -> dict[str, str]:
    """Resolve outputs for native-deb or native-rpm matrix rows."""
    group = catalog.get("native", {})
    entry = group.get(target)
    if not entry or fmt not in entry:
        raise ValueError(f"unknown {fmt} native target '{target}'")

    fmt_cfg = entry[fmt]
    eff_ref, default_ref, default_ver = _resolve_ref_and_version(
        target, entry, fmt_cfg, requested_ref
    )

    images: dict[str, str] = fmt_cfg.get("images", {})
    valid_suites = [s for s, img in images.items() if img]
    req_suites = requested_suites.split()
    for s in req_suites:
        if s not in valid_suites:
            raise ValueError(f"'{s}' is not a suite {target} is valid for ({' '.join(valid_suites)})")

    valid_arches: list[str] = list(fmt_cfg.get("arches", []))
    req_arches = requested_arches.split()
    for a in req_arches:
        if a not in valid_arches:
            raise ValueError(
                f"'{a}' is not an architecture {target} is valid for ({' '.join(valid_arches)})"
            )

    active_suites = req_suites if req_suites else valid_suites
    active_arches = req_arches if req_arches else valid_arches
    selected_image = images.get(suite, "") if suite in active_suites else ""
    build_arch = "true" if arch in active_arches else "false"

    publish_runs_on = json.dumps(entry.get("publish_runs_on", ["ubuntu-latest"]))
    require_tag = "true" if entry.get("require_tag_publish", False) else "false"
    repo = entry["repo"]

    out = {
        "repo_url": f"https://github.com/flagos-ai/{repo}.git",
        "effective_ref": eff_ref,
        "default_ref": default_ref,
        "default_version": default_ver,
        "require_tag_publish": require_tag,
        "script": fmt_cfg["script"],
        "base_arg": fmt_cfg["base_arg"],
        "script_arg": str(fmt_cfg.get("script_arg", "")),
        "outdir": fmt_cfg["outdir"],
        "deps": " ".join(fmt_cfg.get("deps", [])),
        "publish_runs_on": publish_runs_on,
        "arches": " ".join(valid_arches),
        "valid_suites": " ".join(valid_suites),
        "build_arch": build_arch,
        "base_image": selected_image,
    }
    if fmt == "deb":
        suite_meta = catalog.get("apt_suites", {}).get(suite, {})
        out["codename"] = str(suite_meta.get("codename", ""))
    else:
        out["spec"] = fmt_cfg["spec"]
        out["base_pkgs"] = " ".join(fmt_cfg.get("base_pkgs", []))
    return out


def _write_outputs(outputs: dict[str, str], output_path: str | None) -> None:
    """Emit key=value pairs to GITHUB_OUTPUT or stdout."""
    lines = "".join(f"{k}={v}\n" for k, v in outputs.items())
    if output_path:
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write(lines)
    else:
        sys.stdout.write(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("noarch", "native"))
    parser.add_argument("format", choices=("deb", "rpm"))
    parser.add_argument("--target", required=True)
    parser.add_argument("--suite", default="")
    parser.add_argument("--arch", default="")
    parser.add_argument("--suites-req", default="")
    parser.add_argument("--arches-req", default="")
    parser.add_argument("--ref", default="")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)

    try:
        catalog = load_catalog(args.config)
        if args.kind == "noarch":
            outputs = resolve_noarch(catalog, args.format, args.target, args.ref)
        else:
            outputs = resolve_native(
                catalog,
                args.format,
                args.target,
                suite=args.suite,
                arch=args.arch,
                requested_suites=args.suites_req,
                requested_arches=args.arches_req,
                requested_ref=args.ref,
            )
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    _write_outputs(outputs, os.environ.get("GITHUB_OUTPUT"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
