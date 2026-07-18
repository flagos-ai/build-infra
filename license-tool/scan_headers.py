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
"""Scan a git repository for copyright/license issues.

Produces structured audit data (YAML + JSON) WITHOUT modifying any files.
This is the read-only audit tool — it never touches source files on disk.

Usage:
    python3 scan_headers.py /path/to/repo --yaml audit.yaml
    python3 scan_headers.py /path/to/repo --json -          # stdout
    python3 scan_headers.py /path/to/repo --license mit
"""

import argparse
import json
import sys
import os

# Allow running from anywhere
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


def main():
    parser = argparse.ArgumentParser(
        description="Scan a repo for copyright/license issues (read-only)."
    )
    parser.add_argument("directory", help="Path to the git repository")
    lib.add_common_args(parser)
    parser.add_argument("--yaml", metavar="FILE",
                        help="Dump audit data to YAML (+ .json companion)")
    parser.add_argument("--json", dest="json_stdout", action="store_true",
                        help="Print audit data as JSON to stdout")

    args = parser.parse_args()

    data = lib.classify_files(args.directory, args.year, args.owner, args.license_id)

    if args.yaml:
        lib.dump_data(data, args.yaml)
        print(f"Audit data → {args.yaml} (+ .json)")

    if args.json_stdout:
        print(json.dumps(data, indent=2, ensure_ascii=False))

    # Console summary
    s = data["stats"]
    lic_display = data["scan"]["license_name"]
    print(f"\n=== {data['repo']['root']} ({lic_display}) ===\n")
    print("--- Scan Summary ---")
    print(f"  Needs header:   {s['added']}")
    print(f"  Skipped:        {s['skipped']}")
    print(f"  Already ours:   {s['already_ours']}")
    if s.get("other_owner"):
        print(f"  Wrong owner:    {s['other_owner']}")
    if s.get("other_license"):
        print(f"  Other license:  {s['other_license']}")
    if s.get("unlicensed"):
        print(f"  Unlicensed:     {s['unlicensed']}")
    if s.get("unknown_type"):
        print(f"  Unknown type:   {s['unknown_type']}")
    if s.get("error"):
        print(f"  Errors:         {s['error']}")

    if data["errors"]:
        print("\nErrors:")
        for e in data["errors"]:
            print(f"  {e['path']}: {e['error']}")


if __name__ == "__main__":
    main()
