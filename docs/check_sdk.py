#!/usr/bin/env python3
"""Check each backend's `sdk:` map in configs.yaml against the SDK packages
its base containerfile installs.

The per-backend `sdk:` map (package filename -> human description) is
hand-filled and frozen. This flags drift when a base Dockerfile changes:
packages installed but missing from the backend's `sdk:` map (need a
description), and stale `sdk:` entries no longer installed (warning only).

  python docs/check_sdk.py    # exit 1 if any package is missing a description
"""
import sys
from pathlib import Path

import gen_data


def main():
    root = gen_data.find_repo_root()
    configs = gen_data.load_yaml(root / "configs.yaml")

    missing_total = 0
    for vendor, backends in configs.get("vendors", {}).items():
        for backend, spec in backends.items():
            name = f"{vendor}-{backend}"
            cf = root / "base" / name
            if not cf.is_file():
                continue
            installed = set(gen_data.parse_containerfile(cf)["sdk_packages"])
            declared = set((spec.get("sdk") or {}))
            for m in sorted(installed - declared):
                print(f"MISSING  {name}: {m}  (add to its sdk: map in configs.yaml)")
                missing_total += 1
            for s in sorted(declared - installed):
                print(f"stale    {name}: {s}  (no longer installed)")

    if missing_total:
        print(f"\n{missing_total} package(s) missing an sdk: entry in configs.yaml")
        sys.exit(1)
    print("OK: every base-image SDK package has an sdk: entry in configs.yaml")


if __name__ == "__main__":
    main()
