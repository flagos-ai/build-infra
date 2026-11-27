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

"""Stamp release versions into Debian changelogs and RPM spec files."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

TAG_VERSION_RE = re.compile(
    r"^v?\d+(?:\.\d+)*(?:-?rc\d+(?:\.\d+)?)?(?:\.post\d+)?$"
)
UPSTREAM_RELEASE_RE = re.compile(
    r"^v?(\d+(?:\.\d+)*)(?:[-.~]?(rc\d+(?:\.\d+)?))?(?:[-.]?(post\d+))?$"
)
PEP440_RELEASE_RE = re.compile(
    r"^v?\d+(?:\.\d+)*(?:[-~]?(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?$"
)
DISTRO_SUFFIX_RE = re.compile(r"\+[a-z][a-z0-9.]*$")
RPM_BASE_REL_RE = re.compile(r"^([1-9]\d*)(?:\.post\d+)?(?:%\{\?dist\})?$")


def _validate_release(value: str, label: str, strict_pep440: bool) -> str:
    """Validate an explicit or tag-derived upstream release string."""
    pattern = PEP440_RELEASE_RE if strict_pep440 else UPSTREAM_RELEASE_RE
    if not pattern.match(value):
        if strict_pep440:
            raise ValueError(
                f"{label} '{value}' is not PEP 440 compatible for wheel metadata "
                "(use rc<N>.post<M> and omit Debian revisions)"
            )
        raise ValueError(
            f"cannot parse an upstream release version out of {label} '{value}' "
            "(omit package revisions such as '-2')"
        )
    return value


def select_release_version(
    ref: str,
    ref_is_tag: bool,
    requested: str = "",
    pinned: str = "",
    strict_pep440: bool = False,
) -> tuple[str, str] | None:
    """Resolve the target upstream release string and audit reason, or None."""
    req = requested.strip()
    pin = pinned.strip()
    if req:
        return _validate_release(req, "requested version", strict_pep440), "requested by this dispatch"
    if pin:
        return _validate_release(pin, "pinned version", strict_pep440), "pinned for this target"
    if ref_is_tag:
        if strict_pep440 and re.match(r"^v?\d+\.", ref):
            return _validate_release(ref, "tag", True), f"derived from tag {ref}"
        if not strict_pep440 and TAG_VERSION_RE.match(ref):
            return _validate_release(ref, "tag", False), f"derived from tag {ref}"
    return None


def compute_deb_version(
    current: str,
    release: str,
    strict_pep440: bool = False,
) -> str:
    """Compute the new Debian changelog version while preserving matching revisions."""
    clean_rel = release.lstrip("v")
    if strict_pep440:
        upstream = re.sub(r"(?<!~)-?(a|b|rc)", r"~\1", clean_rel)
    else:
        upstream = re.sub(r"(?<!~)-?rc", "~rc", clean_rel)

    cur_base = DISTRO_SUFFIX_RE.sub("", current)
    cur_up, cur_rev = cur_base.rsplit("-", 1) if "-" in cur_base else (cur_base, "1")
    rev = cur_rev if cur_up == upstream else "1"
    return f"{upstream}-{rev}"


def compute_rpm_version_release(
    cur_ver: str,
    cur_rel: str,
    release: str,
) -> tuple[str, str]:
    """Compute RPM Version and Release fields while preserving integer base releases."""
    m = UPSTREAM_RELEASE_RE.match(release)
    if not m:
        raise ValueError(f"cannot parse a release version out of '{release}'")
    upstream, rc, post = m.group(1), m.group(2), m.group(3)

    m_rel = RPM_BASE_REL_RE.match(cur_rel)
    base_rel = m_rel.group(1) if (cur_ver == upstream and m_rel) else "1"
    qualifier = ".".join(x for x in (rc, post) if x)
    if rc:
        relval = f"0.{qualifier}%{{?dist}}"
    elif post:
        relval = f"{base_rel}.{post}%{{?dist}}"
    else:
        relval = f"{base_rel}%{{?dist}}"
    return upstream, relval


def stamp_deb_changelog(
    path: Path,
    ref: str,
    ref_is_tag: bool,
    requested: str = "",
    pinned: str = "",
    strict_pep440: bool = False,
) -> None:
    """Rewrite the top entry of a Debian changelog when a release version applies."""
    body = path.read_text(encoding="utf-8")
    head = body.splitlines()[0] if body else ""
    m = re.match(r"^(\S+) \(([^)]+)\)(.*)$", head)
    if not m:
        raise ValueError(f"cannot parse changelog first line: {head}")
    source, current, _ = m.groups()

    selected = select_release_version(ref, ref_is_tag, requested, pinned, strict_pep440)
    if selected is None:
        print(
            f"Keeping the changelog version {current}: {ref} is not a version tag."
            " Pass `version` to stamp a release version explicitly."
        )
        return

    release, why = selected
    new = compute_deb_version(current, release, strict_pep440)
    if new == current:
        print(f"Changelog already at {current}; nothing to stamp")
        return

    print(f"::notice::stamping {source} {current} -> {new} ({why})")
    path.write_text(body.replace(f"{source} ({current})", f"{source} ({new})", 1), encoding="utf-8")


def stamp_rpm_spec(
    path: Path,
    ref: str,
    ref_is_tag: bool,
    requested: str = "",
    pinned: str = "",
) -> None:
    """Rewrite Version and Release in an RPM spec file when a release version applies."""
    body = path.read_text(encoding="utf-8")
    mv = re.search(r"^Version:(\s+)(\S+)\s*$", body, re.M)
    mr = re.search(r"^Release:(\s+)(\S+)\s*$", body, re.M)
    if not mv or not mr:
        raise ValueError(f"{path} needs both a Version: and a Release: line")

    selected = select_release_version(ref, ref_is_tag, requested, pinned, strict_pep440=False)
    if selected is None:
        print(
            f"Keeping the spec at {mv.group(2)}-{mr.group(2)}: {ref} is not a version tag."
            " Pass `version` to stamp a release version explicitly."
        )
        return

    release, why = selected
    version, relval = compute_rpm_version_release(mv.group(2), mr.group(2), release)
    if (version, relval) == (mv.group(2), mr.group(2)):
        print(f"Spec already at {version}-{relval}; nothing to stamp")
        return

    print(f"::notice::stamping {path} {mv.group(2)}-{mr.group(2)} -> {version}-{relval} ({why})")
    body = body[:mr.start(2)] + relval + body[mr.end(2):]
    body = body[:mv.start(2)] + version + body[mv.end(2):]
    path.write_text(body, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for workflow steps."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("format", choices=("deb", "rpm"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--is-tag", default="false")
    parser.add_argument("--requested", default="")
    parser.add_argument("--pinned", default="")
    parser.add_argument("--pep440", action="store_true")
    args = parser.parse_args(argv)

    is_tag = args.is_tag.strip().lower() == "true"
    try:
        if args.format == "deb":
            stamp_deb_changelog(
                args.path,
                ref=args.ref,
                ref_is_tag=is_tag,
                requested=args.requested,
                pinned=args.pinned,
                strict_pep440=args.pep440,
            )
        else:
            stamp_rpm_spec(
                args.path,
                ref=args.ref,
                ref_is_tag=is_tag,
                requested=args.requested,
                pinned=args.pinned,
            )
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
