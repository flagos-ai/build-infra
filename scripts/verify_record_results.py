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

"""Apply verify-job results to the status matrices + debug queue.

The verify-driver.yml record job aggregates the per-cell results the verify
matrix job uploaded, then hands them here. For each result this script:

  1. Surgically sets the cell symbol in the app's status_matrix YAML —
     ✅ for passed, ❌ for failed (line edit, same technique as
     record_app_image_tag.py, so the header comment survives).
  2. Appends a task card for each failed cell to .github/verify-queue.yaml
     (the driver → local debug-loop handoff; docs/verify-orchestrator.md
     §4.2.1). Idempotent: a cell already queued for the same verdict is not
     duplicated.

It never pushes or opens PRs — the record job wraps that around this script.

Usage:
    python scripts/verify_record_results.py --results /tmp/results.json
    python scripts/verify_record_results.py --results /tmp/results.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from verify_collect_cells import APP_VERIFY, MATRICES, PENDING, _default_compiler

REPO_ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = REPO_ROOT / ".github" / "verify-queue.yaml"

PASS = "✅"
FAIL = "❌"


def set_symbol(matrix_path: Path, scenario: str, backend: str, compiler: str, symbol: str) -> bool:
    """Set the T/F symbol for backend in the scenario's verification map; return changed.

    The verification lines are ``      {backend}: {T: "...", F: "..."}`` — a
    backend key at 6-space indent inside the ``{scenario}`` block (megatron has
    several scenarios; the record must only touch the cell's own). Locate the
    ``  {scenario}:`` header, then scan its block for the backend key and swap
    the compiler's symbol inside it.
    """
    lines = matrix_path.read_text().splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln == f"  {scenario}:":
            start = i
            break
    if start is None:
        sys.exit(f"Error: scenario '{scenario}' not found in {matrix_path}")
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        stripped = ln.lstrip(" ")
        if not stripped:
            continue
        indent = len(ln) - len(stripped)
        if indent <= 2:
            break  # left the scenario block (next scenario or top-level key)
        if indent == 6 and stripped.startswith(f"{backend}:"):
            old = f'{compiler}: "{PENDING}"'
            new = f'{compiler}: "{symbol}"'
            if old not in ln:
                return False  # already resolved (or absent compiler)
            lines[i] = ln.replace(old, new, 1)
            matrix_path.write_text("\n".join(lines) + "\n")
            return True
    sys.exit(f"Error: backend '{backend}' not found in scenario '{scenario}' of {matrix_path}")


def _cell_key(cell: dict) -> str:
    return f"{cell['app']} / {cell['backend']} / {cell['compiler']}"


def upsert_queue(cards: list[dict]) -> None:
    """Merge new task cards into .github/verify-queue.yaml, dedup by cell id."""
    existing: list[dict] = []
    if QUEUE_PATH.is_file():
        existing = yaml.safe_load(QUEUE_PATH.read_text()) or []
        if not isinstance(existing, list):
            existing = []
    seen = {_cell_key(c) for c in existing}
    for card in cards:
        if _cell_key(card) not in seen:
            existing.append(card)
            seen.add(_cell_key(card))
    QUEUE_PATH.write_text(yaml.safe_dump(existing, allow_unicode=True, sort_keys=False))


def remaining_pending() -> int:
    """Count default-compiler cells still ⬜ across all app matrices (for the
    terminate job). Mirrors collect(): only the default compiler column (F if
    present else T) counts — the other column stays ⬜ until the scripts grow
    --compiler, so it must not keep the driver running."""
    n = 0
    for app, rel in MATRICES.items():
        matrix = yaml.safe_load((REPO_ROOT / rel).read_text()) or {}
        verification = matrix.get("scenarios", {}).get(APP_VERIFY[app]["scenario"], {}).get("verification", {})
        for syms in verification.values():
            if _default_compiler(syms) is not None:
                n += 1
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, help="JSON list of verify results")
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = parser.parse_args()

    results = json.loads(Path(args.results).read_text())
    failed_cards = []
    changed_files: set[str] = set()
    for r in results:
        rel = MATRICES[r["app"]]
        matrix_path = REPO_ROOT / rel
        symbol = PASS if r["status"] == "passed" else FAIL
        if not args.dry_run and set_symbol(matrix_path, r["scenario"], r["backend"], r["compiler"], symbol):
            changed_files.add(rel)
        print(f"{r['app']:16} {r['backend']:26} {r['compiler']} -> {symbol}")

        if r["status"] != "passed":
            failed_cards.append({
                "app": r["app"],
                "backend": r["backend"],
                "compiler": r["compiler"],
                "scenario": r.get("scenario"),
                "image": r.get("image"),
                "verify_script": r.get("verify_script"),
                "verify_args": r.get("verify_args"),
                "failure": r.get("failure"),
            })

    if failed_cards and not args.dry_run:
        upsert_queue(failed_cards)

    pending = remaining_pending()
    print(f"remaining pending cells: {pending}")

    with open(REPO_ROOT / ".github" / "verify-remaining.json", "w") as fh:
        json.dump({"remaining": pending, "changed": list(changed_files)}, fh)


if __name__ == "__main__":
    main()
