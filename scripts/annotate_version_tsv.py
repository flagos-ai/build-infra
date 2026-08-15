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

"""Annotate an extracted version TSV with metadata headers before upload.

The extract job runs this after ``docs/extract_versions.py`` and the verify
step, then uploads the annotated ``<backend>.tsv`` as a GitHub artifact
(``versions-<backend>``). The accumulate job's ``collect_version_tsvs.py``
reads the ``# verify:`` header for its verify summary, and
``docs/gen_descriptions.py`` reads ``# last_updated:`` / ``# revision:`` for
the "Last updated" line — so the headers must travel inside the TSV.

Preconditions: ``GITHUB_RUN_ID`` is set; ``<tsv-dir>/<backend>.verify_outcome``
exists (written by the workflow's "Record verify status" step); the optional
``<tsv-dir>/<backend>.labels`` was written by ``docs/extract_versions.py``.

Usage: python scripts/annotate_version_tsv.py <backend> <tsv-dir>
"""

import os
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: annotate_version_tsv.py <backend> <tsv-dir>")

    backend = sys.argv[1]
    tsv_dir = Path(sys.argv[2])
    tsv_file = tsv_dir / f"{backend}.tsv"
    verify_file = tsv_dir / f"{backend}.verify_outcome"

    if not tsv_file.is_file():
        sys.exit(f"Error: {tsv_file} not found")

    headers = [f"# run: {os.environ.get('GITHUB_RUN_ID', 'unknown')}"]
    verify = verify_file.read_text().strip() if verify_file.is_file() else "unknown"
    headers.append(f"# verify: {verify}")

    labels_file = tsv_dir / f"{backend}.labels"
    if labels_file.is_file():
        for line in labels_file.read_text().splitlines():
            key, _, val = line.partition("=")
            if val:
                headers.append(f"# {key}: {val}")

    # Prepend the headers to the TSV content in place.
    tsv_file.write_text("\n".join(headers) + "\n" + tsv_file.read_text())
    print(f"Annotated {backend}.tsv with {len(headers)} metadata headers")


if __name__ == "__main__":
    main()
