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

"""Dispatch app-image build workflows for verify-passed cells.

Run by the verify-driver build job after the verify matrix uploaded its
results. Reads the merged ``result-*.json`` files and, for each passed cell,
dispatches the matching app-image workflow (``push=true``) via the REST API —
so the build + snapshot verify + tag record + PR chain reuses the existing
workflow instead of re-implementing it.

Mapping:
  vllm0.20.2        -> vllm-app-image.yml      (vllm_version=0.20.2)
  vllm0.24.0        -> vllm-app-image.yml      (vllm_version=0.24.0)
  megatron_training -> megatron-app-image.yml  (app=megatron_training)
  megatron_rl       -> megatron-app-image.yml  (app=megatron_rl)

Never dispatches a cell whose verify failed. Requires GITHUB_TOKEN/GITHUB_REPOSITORY.

Usage:
    python scripts/verify_dispatch_build.py --results-dir /tmp/results
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import urllib.request
from pathlib import Path

APP_WORKFLOW = {
    "vllm0.20.2": ("vllm-app-image.yml", {"vllm_version": "0.20.2"}),
    "vllm0.24.0": ("vllm-app-image.yml", {"vllm_version": "0.24.0"}),
    "megatron_training": ("megatron-app-image.yml", {"app": "megatron_training"}),
    "megatron_rl": ("megatron-app-image.yml", {"app": "megatron_rl"}),
}


def _gh_api(method: str, path: str, body: dict | None = None) -> dict:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Error: GH_TOKEN/GITHUB_TOKEN not set — cannot dispatch")
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        # Dispatch endpoints answer 204 No Content (empty body); json.loads on
        # b"" raises, so treat an empty body as an empty object instead.
        return json.loads(raw) if raw else {}


def dispatch(repo: str, workflow: str, backend: str, inputs: dict) -> None:
    _gh_api("POST", f"/repos/{repo}/actions/workflows/{workflow}/dispatches", {
        "ref": "main",
        "inputs": {"backend": backend, "push": "true", **inputs},
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, help="dir holding merged result-*.json")
    args = parser.parse_args()

    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        sys.exit("Error: GITHUB_REPOSITORY not set — cannot dispatch")

    dispatched = 0
    seen: set[tuple[str, str]] = set()
    for f in sorted(glob.glob(str(Path(args.results_dir) / "result-*.json"))):
        r = json.loads(open(f).read())
        if r.get("status") != "passed":
            continue
        # A backend whose F and T cells both pass dispatches only once — the
        # app image is compiler-agnostic, one build covers both columns.
        key = (r["app"], r["backend"])
        if key in seen:
            continue
        seen.add(key)
        workflow, extra = APP_WORKFLOW[r["app"]]
        dispatch(repo, workflow, r["backend"], extra)
        dispatched += 1
        print(f"dispatched {workflow} backend={r['backend']} {extra}")

    print(f"verify_dispatch_build: dispatched {dispatched} build(s)")


if __name__ == "__main__":
    main()
