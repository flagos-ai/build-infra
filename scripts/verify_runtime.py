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

"""Verify a runtime v2 image: import torch, triton, flag_gems, and run
flag_gems.use_gems() with a simple add operator.

Pulls the image from Harbor and runs the verification command inside it
with the appropriate per-vendor docker run flags.  Designed primarily
for interactive use on self-hosted runner nodes.

Usage: python scripts/verify_runtime.py <backend-name>
       python scripts/verify_runtime.py nvidia-cuda12.8
       python scripts/verify_runtime.py all         # every backend listed in images.yaml
"""

import shlex
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

# Verification script run inside the container via bash heredoc.
# Checks: import torch, import triton, import flag_gems, use_gems + add op.
# Each step is independently try/except'd; failures are collected.
VERIFY_SCRIPT = r'''import sys
tests = []
# 1. import torch
try:
    import torch
    tests.append('torch OK ' + torch.__version__)
except Exception as e:
    tests.append('torch FAIL: ' + str(e))

# 2. import triton
try:
    import triton
    tests.append('triton OK ' + str(getattr(triton, '__version__', '?')))
except Exception as e:
    tests.append('triton FAIL: ' + str(e))

# 3. import flag_gems
try:
    import flag_gems
    tests.append('flag_gems OK ' + flag_gems.__version__)
except Exception as e:
    tests.append('flag_gems FAIL: ' + str(e))

# 4. use_gems + add op
try:
    flag_gems.use_gems()
    a = torch.randn(2, 3)
    b = a + a
    tests.append('use_gems+add OK shape=' + str(list(b.shape)))
except Exception as e:
    tests.append('use_gems+add FAIL: ' + str(e))

for t in tests:
    print(t)
if any('FAIL' in t for t in tests):
    sys.exit(1)
'''


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: verify_runtime.py <backend-name> | all")

    images = yaml.safe_load(
        (REPO_ROOT / "docs" / "data" / "images.yaml").read_text()
    )
    build_cfg = yaml.safe_load(
        (REPO_ROOT / ".github" / "build-config.yml").read_text()
    )

    # Resolve backend names.
    target = sys.argv[1]
    all_names = [b["name"] for b in images.get("backends", [])]
    if target == "all":
        names = all_names
        print(f"Verifying all {len(names)} runtime v2 backends...")
    else:
        names = [target] if target in all_names else []
        if not names:
            sys.exit(f"'{target}' not in images.yaml")

    failed = []
    for name in names:
        entry = next(b for b in images.get("backends", []) if b["name"] == name)
        image = entry["runtime"]["image"]
        vendor = name.split("-")[0]

        # Per-vendor docker run flags.
        run_cfg = (
            (build_cfg.get("run") or {}).get("vendors") or {}
        ).get(vendor) or {}
        flags_str = run_cfg.get("toolkit", "") or run_cfg.get("raw", "")
        flags = shlex.split(flags_str) if flags_str else []

        # Pull + verify.  Stream output directly to the terminal so
        # self-hosted runners capture it in the job log — capture_output
        # can drop it when GitHub API connectivity is unreliable.
        print(f"::group::{name} — verify runtime v2 ({image})")
        print(f"  Pulling {image}...")
        pr = subprocess.run(["docker", "pull", image])
        if pr.returncode != 0:
            print(f"  ❌ docker pull failed (exit {pr.returncode})")
            print("::endgroup::")
            failed.append(name)
            continue

        # Pipe the verification script via bash heredoc so multi-line
        # try/except blocks work (python3 -c can't do that on one line).
        cmd = ["docker", "run"] + flags + ["--rm", image,
               "bash", "-c", f"python3 << 'PYEOF'\n{VERIFY_SCRIPT}\nPYEOF"]
        print(f"  Verifying...")
        r = subprocess.run(cmd)
        print("::endgroup::")

        if r.returncode != 0:
            print(f"  ❌ {name}: verification FAILED (exit {r.returncode})")
            failed.append(name)
        else:
            print(f"  ✅ {name}: ALL 4 checks passed")

    if failed:
        print(f"\n{len(failed)} FAILED: {' '.join(failed)}")
        sys.exit(1)
    print(f"\nAll {len(names)} backends passed.")


if __name__ == "__main__":
    main()
