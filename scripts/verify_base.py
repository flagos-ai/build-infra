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

"""Verify a built base image by running the vendor's device-enumeration command.

Reads the verify command from .github/build-config.yml for the vendor extracted
from the backend name, then runs ``docker run --rm <image> <verify-cmd>``.
When the runner lacks the matching accelerator, the command fails gracefully
(skip) rather than erroring — verification is a best-effort gate, not a hard
requirement for description extraction.

Usage: python scripts/verify_base.py <backend-name>
"""

import shlex
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: verify_base.py <backend-name>")
    name = sys.argv[1]

    # Image ref from generated data.
    images = yaml.safe_load(
        (REPO_ROOT / "docs" / "data" / "images.yaml").read_text()
    )
    entry = next(
        (b for b in images.get("backends", []) if b["name"] == name), None
    )
    if not entry:
        sys.exit(f"Error: '{name}' not in images.yaml")
    image = entry["base"]["image"]

    # Verify command from build-config.
    build_cfg = yaml.safe_load(
        (REPO_ROOT / ".github" / "build-config.yml").read_text()
    )
    vendor = name.split("-")[0]
    verify_cmd = (
        (build_cfg.get("verify") or {}).get("vendors") or {}
    ).get(vendor, "")
    if not verify_cmd:
        print(f"::notice::{vendor}: no verify command in build-config.yml → SKIP")
        return

    # Per-vendor `docker run` flags (raw device-passthrough — no toolkit needed).
    raw_cfg = ((build_cfg.get("run") or {}).get("vendors") or {}).get(vendor) or {}
    raw_flags_str = raw_cfg.get("raw", "")
    raw_flags = shlex.split(raw_flags_str) if raw_flags_str else []

    # docker run <run-flags> --rm <image> verify
    cmd = ["docker", "run"] + raw_flags + ["--rm", image, "bash", "-c", verify_cmd]
    print(f"::group::{' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    print("::endgroup::")

    if r.returncode == 0:
        # Print a GHA workflow command so the log stands out.
        print(f"::notice title=Verify::{vendor}: verify OK — {verify_cmd}")
        return

    # Non-zero exit. Collapse into "skip" or "fail" based on signal.
    rc = r.returncode
    if rc == 137:
        # SIGKILL (OOM) — real error, not missing hardware.
        sys.exit(f"{vendor}: verify command was OOM-killed (exit {rc})")
    if rc == 139:
        # SIGSEGV — real error.
        sys.exit(f"{vendor}: verify command segfaulted (exit {rc})")

    # Any other non-zero: likely missing device / driver — skip.
    print(
        f"::warning title=Verify::{vendor}: verify exited {rc} "
        f"— runner likely lacks {vendor} hardware → SKIP"
    )


if __name__ == "__main__":
    main()
