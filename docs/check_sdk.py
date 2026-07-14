#!/usr/bin/env python3
"""Check docs/data/sdk.yaml against the SDK packages in the base images.

sdk.yaml is a one-time, hand-filled, frozen map of base-image SDK package
filenames to human-readable descriptions. This flags drift: packages present
in base/ containerfiles but missing from sdk.yaml (need a description), and
stale sdk.yaml entries no longer installed by any base image (warning only).

  python docs/check_sdk.py          # check; exit 1 on missing entries
  python docs/check_sdk.py --init   # print a fresh skeleton (all packages)
"""
import sys
from pathlib import Path

import yaml
import gen_data


def all_packages():
    root = gen_data.find_repo_root()
    pkgs = set()
    for f in sorted((root / "base").iterdir()):
        if f.is_file() and not f.name.endswith(".py"):
            pkgs |= set(gen_data.parse_containerfile(f)["sdk_packages"])
    return pkgs, root


def main():
    pkgs, root = all_packages()
    sdk_path = root / "docs" / "data" / "sdk.yaml"

    if "--init" in sys.argv:
        print("# SDK package descriptions for the base images.")
        print("# Hand-filled and frozen (not script-maintained). The SDK dict")
        print("# check CI job flags when a base Dockerfile change adds/removes a")
        print("# package. Fill each empty value with a short readable description.")
        print("packages:")
        for p in sorted(pkgs):
            print(f'  "{p}": ""')
        return

    have = {}
    if sdk_path.exists():
        have = (yaml.safe_load(sdk_path.read_text()) or {}).get("packages") or {}
    missing = sorted(pkgs - set(have))
    stale = sorted(set(have) - pkgs)
    for m in missing:
        print(f"MISSING (add to docs/data/sdk.yaml): {m}")
    for s in stale:
        print(f"stale (no longer installed): {s}")
    if missing:
        print(f"\n{len(missing)} package(s) missing from docs/data/sdk.yaml")
        sys.exit(1)
    print("OK: docs/data/sdk.yaml covers all base-image SDK packages")


if __name__ == "__main__":
    main()
