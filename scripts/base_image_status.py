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

"""Report which base images are outdated relative to what is pushed to Harbor.

During a release cycle every backend shares one flat Harbor tag,
``flagos-base-{name}:{version}`` — rebuilt images overwrite the same tag.
Attaching a ``-N`` affix to the tag was dropped because it is confusing
to users; instead this script answers the "is the pushed image behind
HEAD's config?" question *without building anything*, by reading the OCI
labels that ``scripts/build_base.py`` stamps onto every image:

    org.opencontainers.image.revision   git commit the image was built from
    org.opencontainers.image.version    image version tag at build time

A backend is OUTDATED when the files that configure its base image
(base/<name> and configs.yaml) changed since that commit. Run this before
a manual, selective rebuild to see which backends actually need one.

Status values:
    UP_TO_DATE  pushed :{version} reflects HEAD's config — no rebuild needed
    OUTDATED    config changed since the pushed image was built — rebuild
    NOT_BUILT   no :{version} tag in Harbor yet — must build
    UNKNOWN     could not determine (see detail column)

Usage:
    HARBOR_USER=... HARBOR_PW=... python scripts/base_image_status.py
    python scripts/base_image_status.py --json
    python scripts/base_image_status.py nvidia-cuda12.8 cambricon-neuware4.7.2
    python scripts/base_image_status.py --tag 2.1.2

Exit code is always 0 — this is an informational overview.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files whose changes require a base image rebuild. Strictly the image
# content comes from base/<name>; configs.yaml is included because it is
# the stack-level single source of truth the release process revolves
# around. Extend this list (e.g. build-config.yml) if other files should
# count.
CONFIG_PATHS = ["configs.yaml"]


def load_context() -> tuple[str, str, str, str, list[str]]:
    """Return (host, project, version, tag-default) + backend names."""
    configs = yaml.safe_load((REPO_ROOT / "configs.yaml").read_text()) or {}
    build = yaml.safe_load((REPO_ROOT / ".github" / "build-config.yml").read_text()) or {}
    registry = build.get("registry") or {}
    host = registry.get("host", "")
    project = (registry.get("prefixes") or {}).get("base", "flagos-base")
    version = str(configs.get("version", "") or "")

    vendors = configs.get("vendors") or {}
    names = sorted(f"{v}-{b}" for v, backends in vendors.items() for b in backends)
    return host, project, version, names


def auth_header() -> str:
    user = os.environ.get("HARBOR_USER", "")
    pw = os.environ.get("HARBOR_PW", "")
    if not user or not pw:
        sys.exit("HARBOR_USER and HARBOR_PW are required (same as docs/upload_descriptions.py)")
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


def image_labels(host: str, repo: str, tag: str, auth: str) -> dict | None:
    """Return the OCI labels of the pushed image, or None if the tag is absent."""
    manifest_url = f"https://{host}/v2/{repo}/manifests/{tag}"
    headers = {
        "Authorization": auth,
        "Accept": (
            "application/vnd.oci.image.manifest.v1+json, "
            "application/vnd.docker.distribution.manifest.v2+json, "
            "application/vnd.oci.image.index.v1+json, "
            "application/vnd.docker.distribution.manifest.list.v2+json"
        ),
    }
    try:
        with urllib.request.urlopen(urllib.request.Request(manifest_url, headers=headers), timeout=30) as r:
            manifest = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

    # Single-arch builds (plain docker build) produce a manifest with a
    # config digest. A manifest list would appear here too; follow the
    # first entry in that case.
    if "config" not in manifest and "manifests" in manifest:
        first = manifest["manifests"][0]["digest"]
        with urllib.request.urlopen(
            urllib.request.Request(f"https://{host}/v2/{repo}/manifests/{first}", headers=headers),
            timeout=30,
        ) as r:
            manifest = json.load(r)

    config_digest = manifest.get("config", {}).get("digest")
    if not config_digest:
        return {}
    with urllib.request.urlopen(
        urllib.request.Request(f"https://{host}/v2/{repo}/blobs/{config_digest}", headers={"Authorization": auth}),
        timeout=30,
    ) as r:
        config = json.load(r)
    return (config.get("config") or {}).get("labels") or {}


def changed_since(revision: str, name: str) -> bool | None:
    """True if base/<name> or configs.yaml changed since `revision`; None if unknown."""
    r = subprocess.run(
        ["git", "diff", "--quiet", f"{revision}..HEAD", "--", f"base/{name}", *CONFIG_PATHS],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    if r.returncode == 128:  # revision not present in this clone
        return None
    return r.returncode == 1  # 0 = no diff, 1 = diff


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("backends", nargs="*", help="limit to these backends (default: all)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument("--tag", help="Harbor tag to inspect (default: configs.yaml version)")
    args = ap.parse_args()

    host, project, version, names = load_context()
    if not host:
        sys.exit("registry.host missing from .github/build-config.yml")
    if not version:
        sys.exit("configs.yaml has no version: field")
    tag = args.tag or version
    auth = auth_header()

    if args.backends:
        wanted = set(args.backends)
        missing = wanted - set(names)
        if missing:
            sys.exit(f"unknown backend(s): {', '.join(sorted(missing))}")
        names = [n for n in names if n in wanted]

    results = []
    for name in names:
        repo = f"{project}/flagos-base-{name}"
        entry = {"name": name, "tag": tag, "revision": "", "status": "", "detail": ""}
        try:
            labels = image_labels(host, repo, tag, auth)
        except urllib.error.URLError as e:
            entry.update(status="UNKNOWN", detail=f"registry unreachable: {e.reason}")
            results.append(entry)
            continue
        except Exception as e:  # noqa: BLE001
            entry.update(status="UNKNOWN", detail=str(e))
            results.append(entry)
            continue

        if labels is None:
            entry.update(status="NOT_BUILT")
            results.append(entry)
            continue

        revision = labels.get("org.opencontainers.image.revision", "")
        entry["revision"] = revision[:12]
        if not revision:
            entry.update(status="UNKNOWN", detail="image has no revision label")
            results.append(entry)
            continue

        changed = changed_since(revision, name)
        if changed is None:
            entry.update(
                status="UNKNOWN",
                detail=f"commit {revision[:12]} not in local clone (need fetch-depth: 0)",
            )
            results.append(entry)
            continue

        entry["status"] = "OUTDATED" if changed else "UP_TO_DATE"
        results.append(entry)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    header = f"{'backend':<28} {'tag':<10} {'built-from':<13} status"
    print(header)
    print("-" * len(header))
    for r in results:
        detail = f"  ({r['detail']})" if r.get("detail") else ""
        print(f"{r['name']:<28} {r['tag']:<10} {r['revision']:<13} {r['status']}{detail}")
    counts = Counter(r["status"] for r in results)
    summary = ", ".join(f"{n} {s}" for s, n in counts.most_common())
    print(f"\n{len(results)} backends: {summary}")


if __name__ == "__main__":
    main()
