#!/usr/bin/env python3
"""Push each generated base-image description to Harbor as the repository
description. Strips the Hugo front matter — Harbor renders the description as
markdown and shows the repository name as the top heading, so the H2-based body
reads correctly on its own.

Reads the generated markdown from docs/content/en/base/<name>.md for every
backend in docs/data/images.yaml. The repository is flagos-base-<name> under the
project taken from the image ref.

Env: HARBOR_HOST, HARBOR_USER, HARBOR_PW (basic auth).
Usage: python docs/upload_descriptions.py [--dry-run]
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


def project_of(image_ref: str) -> str:
    # harbor.baai.ac.cn/flagos-base/flagos-base-nvidia-cuda13.3:2.1.1 -> flagos-base
    path = image_ref.split("/", 1)[1] if "/" in image_ref else image_ref
    return path.split("/", 1)[0]


def main():
    dry = "--dry-run" in sys.argv[1:]
    host = os.environ["HARBOR_HOST"]
    user = os.environ.get("HARBOR_USER", "")
    pw = os.environ.get("HARBOR_PW", "")
    auth = "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()

    root = Path(__file__).resolve().parent.parent
    images = yaml.safe_load((root / "docs" / "data" / "images.yaml").read_text())
    base_dir = root / "docs" / "content" / "en" / "base"

    failures = 0
    for entry in images.get("backends", []):
        name = entry["name"]
        md_path = base_dir / f"{name}.md"
        if not md_path.is_file():
            print(f"skip {name}: no description md")
            continue
        desc = strip_front_matter(md_path.read_text())
        project = project_of(entry["base"]["image"])
        repo = f"flagos-base-{name}"
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
