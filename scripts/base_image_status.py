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
An earlier ``-N`` affix design was dropped as confusing to users. Instead
this script answers "is the pushed image behind HEAD?" *without building
anything*, by reading the OCI labels that ``scripts/build_base.py`` stamps
onto every image:

    org.opencontainers.image.revision   git commit the image was built from
    org.opencontainers.image.version    image version tag at build time

A backend is OUTDATED when either:

  - the ``base/<name>`` Containerfile changed since that commit, or
  - the image's ``version`` label differs from the tag being inspected
    (normally configs.yaml ``version:`` — the tag changed, so the image
    must be rebuilt to carry the new tag).

Run this before a manual, selective base rebuild to see which backends
actually need one.

Status values:
    UP_TO_DATE  pushed :{tag} reflects HEAD's containerfile and tag
    OUTDATED    containerfile and/or tag changed since the pushed image
    NOT_BUILT   no :{tag} tag in Harbor yet — must build
    UNKNOWN     could not determine (see detail column)

Usage:
    python scripts/base_image_status.py                          # anonymous (public projects)
    HARBOR_USER=... HARBOR_PW=... python scripts/base_image_status.py  # private registry
    python scripts/base_image_status.py --json
    python scripts/base_image_status.py nvidia-cuda12.8 cambricon-neuware4.7.2
    python scripts/base_image_status.py --tag 2.1.2

Requires a checkout with the full history (fetch-depth: 0) so the
revision stamped on a pushed image is resolvable locally.

Exit code is always 0 — this is an informational overview.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_context() -> tuple[str, str, str, list[str]]:
    """Return (host, base-project, version, backend names)."""
    configs = yaml.safe_load((REPO_ROOT / "configs.yaml").read_text()) or {}
    build = yaml.safe_load((REPO_ROOT / ".github" / "build-config.yml").read_text()) or {}
    registry = build.get("registry") or {}
    host = registry.get("host", "")
    project = (registry.get("prefixes") or {}).get("base", "flagos-base")
    version = str(configs.get("version", "") or "")

    vendors = configs.get("vendors") or {}
    names = sorted(f"{v}-{b}" for v, backends in vendors.items() for b in backends)
    return host, project, version, names


def credentials() -> str | None:
    """Basic auth header if HARBOR_USER/HARBOR_PW are set, else None (anonymous).

    Credentials are optional: the base-image project is public, so the
    bearer-token grant works anonymously. Set them only when inspecting a
    private registry.
    """
    user = os.environ.get("HARBOR_USER", "")
    pw = os.environ.get("HARBOR_PW", "")
    if not user or not pw:
        return None
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


def _parse_www_authenticate(header: str) -> dict:
    """Parse a challenge like ``Bearer realm="...",service="...",scope="..."``."""
    return {m.group(1): m.group(2) for m in re.finditer(r'(\w+)="([^"]*)"', header or "")}


class HarborAuth:
    """Registry client that follows the bearer-token challenge on 401.

    With credentials set, the token grant is made with Basic auth; without
    them the grant is anonymous, which works for public projects like
    ``flagos-base``. A 404 is raised as ``HTTPError`` and left to callers.
    """

    def __init__(self, host: str, basic: str | None):
        self.host = host
        self.basic = basic

    def request(self, path: str, headers: dict | None = None):
        """Open ``/v2/{path}``, following the bearer challenge once on 401."""
        url = f"https://{self.host}/v2/{path}"
        h = dict(headers or {})
        if self.basic:
            h["Authorization"] = self.basic
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30)
        except urllib.error.HTTPError as e:
            if e.code != 401:
                raise
            token = self._bearer_token(e.headers.get("WWW-Authenticate", ""))
            if not token:
                raise
            h["Authorization"] = f"Bearer {token}"
            return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30)

    def _bearer_token(self, challenge: str) -> str | None:
        params = _parse_www_authenticate(challenge)
        realm = params.get("realm")
        if not realm:
            return None
        qs = "&".join(
            f"{k}={v}" for k, v in (("service", params.get("service")), ("scope", params.get("scope"))) if v
        )
        h = {"Authorization": self.basic} if self.basic else {}
        try:
            with urllib.request.urlopen(
                urllib.request.Request(realm + (f"?{qs}" if qs else ""), headers=h),
                timeout=30,
            ) as r:
                return json.load(r).get("token")
        except Exception:  # noqa: BLE001 — a failed token grant just means no retry
            return None


def image_labels(client: HarborAuth, repo: str, tag: str) -> dict | None:
    """Return the OCI labels of the pushed image, or None if the tag is absent."""
    accept = (
        "application/vnd.oci.image.manifest.v1+json, "
        "application/vnd.docker.distribution.manifest.v2+json, "
        "application/vnd.oci.image.index.v1+json, "
        "application/vnd.docker.distribution.manifest.list.v2+json"
    )
    try:
        with client.request(f"{repo}/manifests/{tag}", {"Accept": accept}) as r:
            manifest = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

    # Plain docker build produces a single-arch manifest with a config digest.
    # A multi-arch index has no "config"; follow the first entry.
    if "config" not in manifest and "manifests" in manifest:
        first = manifest["manifests"][0]["digest"]
        with client.request(f"{repo}/manifests/{first}", {"Accept": accept}) as r:
            manifest = json.load(r)

    config_digest = manifest.get("config", {}).get("digest")
    if not config_digest:
        return {}
    with client.request(f"{repo}/blobs/{config_digest}") as r:
        config = json.load(r)
    # The OCI image-config JSON key is "Labels" (capital L, as Docker and
    # podman write it). A lowercase key never matches, so every pushed image
    # was reported UNKNOWN ("no revision label") despite carrying labels.
    return (config.get("config") or {}).get("Labels") or {}


def containerfile_changed(revision: str, name: str) -> bool | None:
    """True if base/<name> changed since `revision`; None if the commit is unknown."""
    r = subprocess.run(
        ["git", "diff", "--quiet", f"{revision}..HEAD", "--", f"base/{name}"],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    if r.returncode == 128:  # revision not present in this clone
        return None
    return r.returncode == 1  # 0 = no diff, 1 = diff


def containerfile_commits(revision: str, name: str) -> int | None:
    """Number of commits touching base/<name> since `revision`; None if unknown."""
    r = subprocess.run(
        ["git", "rev-list", "--count", f"{revision}..HEAD", "--", f"base/{name}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    return int(r.stdout.strip())


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
    client = HarborAuth(host, credentials())

    if args.backends:
        wanted = set(args.backends)
        missing = wanted - set(names)
        if missing:
            sys.exit(f"unknown backend(s): {', '.join(sorted(missing))}")
        names = [n for n in names if n in wanted]

    results = []
    for name in names:
        repo = f"{project}/flagos-base-{name}"
        entry = {"name": name, "tag": tag, "built": "", "status": "", "detail": ""}
        try:
            labels = image_labels(client, repo, tag)
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
        built_version = labels.get("org.opencontainers.image.version", "")
        entry["built"] = revision[:12]
        if not revision:
            entry.update(status="UNKNOWN", detail="image has no revision label")
            results.append(entry)
            continue

        changed = containerfile_changed(revision, name)
        if changed is None:
            entry.update(
                status="UNKNOWN",
                detail=f"commit {revision[:12]} not in local clone (need fetch-depth: 0)",
            )
            results.append(entry)
            continue

        reasons = []
        if built_version and built_version != tag:
            reasons.append(f"tag: built as {built_version}, expected {tag}")
        if changed:
            n = containerfile_commits(revision, name)
            count = f" ({n} commit(s))" if n is not None else ""
            reasons.append(f"containerfile: changed since {revision[:12]}{count}")
        if not reasons and not built_version:
            # Image is current tag-wise but carries no version label to verify.
            reasons.append("no version label on image")

        entry["status"] = "OUTDATED" if reasons else "UP_TO_DATE"
        entry["detail"] = "; ".join(reasons)
        results.append(entry)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    header = f"{'backend':<28} {'tag':<8} {'built':<13} status"
    print(header)
    print("-" * len(header))
    for r in results:
        detail = f"  ({r['detail']})" if r.get("detail") else ""
        print(f"{r['name']:<28} {r['tag']:<8} {r['built']:<13} {r['status']}{detail}")
    counts = Counter(r["status"] for r in results)
    summary = ", ".join(f"{n} {s}" for s, n in counts.most_common())
    print(f"\n{len(results)} backends: {summary}")


if __name__ == "__main__":
    main()
