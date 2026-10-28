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

"""Push each generated image description to Harbor as the repository
description. Harbor renders the description as markdown and shows the repository
name as the top heading, so the H2-based body reads correctly on its own.

Reads the plain-flavor markdown for every image in docs/data/images.yaml. The
base and runtime layers read <layer>/<name>.md, one per backend; the app layer
reads app/<component>/<image>.md, one per app image (109 of them, against 21
backends — which is why the app layer iterates the app images too). The
repository and the Harbor project are both taken from the image ref itself, so
one rule covers all three layers.

Env: HARBOR_HOST, HARBOR_USER, HARBOR_PW (basic auth).
Usage: python scripts/docs/upload_descriptions.py [--layer base|runtime|app] [--dry-run]
"""

import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml


def strip_front_matter(md: str) -> str:
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            md = md[end + 4:]
    return md.lstrip("\n")


def repo_of(image_ref: str) -> str:
    # harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda13.3:2.1.1 -> flagos-base-nvidia-cuda13.3
    # harbor.baai.ac.cn/flagos-app/vllm0.24.0-generic-12.8:TBD -> vllm0.24.0-generic-12.8
    return image_ref.split("/")[2].split(":")[0]


def project_of(image_ref: str) -> str:
    # harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda13.3:2.1.1 -> flagos-base
    path = image_ref.split("/", 1)[1] if "/" in image_ref else image_ref
    return path.split("/", 1)[0]


def targets(images: dict, layer: str, root: Path) -> list[tuple[Path, str]]:
    """(markdown path, image ref) for every image of one layer.

    The markdown path is derived from the ref's repository name — the app layer's
    component directory (megatron / vllm / sglang) is discovered from where the
    file lives rather than re-derived from the app key, so the two can never
    disagree about which component an image belongs to.
    """
    out: list[tuple[Path, str]] = []
    for entry in images.get("backends", []):
        if layer in ("base", "runtime"):
            md = root / layer / f"{entry['name']}.md"
            out.append((md, entry[layer]["image"]))
            continue
        for data in (entry.get("app") or {}).get("images", {}).values():
            repo = repo_of(data["image"])
            for md in sorted((root / "app").glob(f"*/{repo}.md")):
                out.append((md, data["image"]))
    return out


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    layer = "base"
    if "--layer" in args:
        layer = args[args.index("--layer") + 1]
    if layer not in ("base", "runtime", "app"):
        sys.exit(f"invalid --layer {layer!r}: expected 'base', 'runtime' or 'app'")

    host = os.environ["HARBOR_HOST"]
    user = os.environ.get("HARBOR_USER", "")
    pw = os.environ.get("HARBOR_PW", "")
    auth = "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()

    root = Path(__file__).resolve().parents[2]
    images = yaml.safe_load((root / "docs" / "data" / "images.yaml").read_text())

    failures = 0
    for md_path, ref in targets(images, layer, root):
        repo = repo_of(ref)
        if not md_path.is_file():
            print(f"skip {repo}: no description md")
            continue
        desc = strip_front_matter(md_path.read_text())
        project = project_of(ref)
        url = f"https://{host}/api/v2.0/projects/{project}/repositories/{repo}"
        if dry:
            print(f"[dry-run] PUT {url}  ({len(desc)} chars)")
            continue
        body = json.dumps({"description": desc}).encode()
        req = urllib.request.Request(url, data=body, method="PUT")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", auth)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"OK {repo}: http={r.status}")
        except urllib.error.HTTPError as e:
            print(f"FAIL {repo}: http={e.code} {e.read().decode()[:200]}")
            failures += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {repo}: {e}")
            failures += 1

    if failures:
        sys.exit(f"{failures} description upload(s) failed")


if __name__ == "__main__":
    main()
