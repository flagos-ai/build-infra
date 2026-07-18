#!/usr/bin/env python3
"""Apply copyright headers to source files in a git repository.

Can work in two modes:
  1. Direct mode    — scan repo + apply headers in one pass
  2. YAML-driven    — read prior audit data, apply only to files that need it

Usage:
    python3 add_headers.py /path/to/repo --dry-run
    python3 add_headers.py /path/to/repo
    python3 add_headers.py --from-yaml audit.yaml --dry-run
    python3 add_headers.py --from-yaml audit.yaml
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


def add_header_to_file(filepath, year, owner, license_id, dry_run=False):
    """Insert the copyright header into *filepath*. Returns (status, lines_written)."""
    header_lines = lib.build_header_lines(year, owner, license_id)
    header, insert_line = lib.get_header(filepath, header_lines)

    if header is None:
        return "unknown_type", 0

    try:
        with open(filepath, "r") as f:
            original = f.read()
    except (IOError, OSError) as e:
        return f"error: {e}", 0

    hdr_lines = header.count("\n")

    if insert_line == 0:
        new_content = header + "\n" + original
    else:
        lines = original.splitlines(keepends=True)
        new_content = "".join(
            lines[:insert_line] + ["\n", header, "\n"] + lines[insert_line:]
        )

    new_content = new_content.rstrip("\n") + "\n"

    if new_content == original:
        return "unchanged", 0

    if dry_run:
        return "would_add", hdr_lines

    with open(filepath, "w") as f:
        f.write(new_content)
    return "added", hdr_lines


def main():
    parser = argparse.ArgumentParser(
        description="Apply copyright headers to source files."
    )
    parser.add_argument("directory", nargs="?", default=None,
                        help="Path to the git repository (direct mode)")
    lib.add_common_args(parser)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without modifying files")
    parser.add_argument("--from-yaml", metavar="FILE",
                        help="Load prior audit data; apply headers to files that need it")

    args = parser.parse_args()

    dry_run = args.dry_run

    # --- resolve repo root, license, and target files --------------------
    if args.from_yaml:
        data = lib.load_data(args.from_yaml)
        repo_root = data["repo"]["root"]
        lic_id = data["scan"]["license"]
        year = args.year if args.year != "2026" else data["scan"]["year"]
        owner = args.owner if args.owner != "FlagOS Contributors" else data["scan"]["owner"]
        target_files = data.get("needs_header", [])
        if not target_files:
            print("No files need headers — nothing to do.")
            return
    elif args.directory:
        repo_root = os.path.abspath(args.directory)
        lic_id, _ = lib.resolve_license(repo_root, args.license_id)
        year, owner = args.year, args.owner
        # Classify to find files that need headers
        data = lib.classify_files(repo_root, year, owner, lic_id)
        target_files = data.get("needs_header", [])
    else:
        parser.error("specify a directory, or --from-yaml to load audit data")

    if not target_files:
        print("No files need headers — nothing to do.")
        return

    lic_display = lib.license_name(lic_id)
    print(f"=== {repo_root} ({lic_display}) ===\n")

    applied = 0
    skipped = 0

    for relpath in target_files:
        fullpath = os.path.join(repo_root, relpath)
        if not os.path.isfile(fullpath):
            print(f"  ✗ {relpath}: file not found (skipped)")
            skipped += 1
            continue

        status, lines = add_header_to_file(fullpath, year, owner, lic_id, dry_run=dry_run)
        if status in ("added", "would_add"):
            applied += 1
            print(f"  {'[DRY RUN] ' if dry_run else ''}+ {relpath}")
        else:
            skipped += 1
            print(f"  ? {relpath}: {status}")

    print(f"\n--- Summary {'(DRY RUN)' if dry_run else ''} ---")
    print(f"  Applied:  {applied}")
    print(f"  Skipped:  {skipped}")


if __name__ == "__main__":
    main()
