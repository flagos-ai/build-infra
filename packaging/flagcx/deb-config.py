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

"""Join backends.yaml with `generate_matrix.py --runtime`.

The matrix owns what build-infra already knows (base_image, runson, version,
image_tag); backends.yaml owns the FlagCX packaging facts. This is the join and
the drift alarm between the two — no version logic, no build logic.

  --merge <matrix.json>   joined CI matrix (one entry per enabled backend)
  --check                 drift + consistency gate; non-zero exit on failure
  --build-inputs <key>    KEY=value lines the build script sources
  --render-control <out>  render debian/control from control.in (values from DEB_*)
  --list                  one line per backend, ready or probe-pending
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REGISTRY = HERE / "backends.yaml"
MATRIX_SCRIPT = REPO / "scripts" / "generate_matrix.py"

# Fields that are lists in the registry and strings in the CI matrix — a build
# arg can only be a string, and the workflow passes every field through as one.
LIST_FIELDS = ("apt", "vendor_libs", "vendor_lib_dirs", "assert")
REQUIRED_ENABLED = ("vendor", "make_flag", "arch", "glibc_floor", "deb")
VALID_ARCH = ("amd64", "arm64")

# What `--build-inputs` hands the build script. Everything else in a matrix row
# describes the runtime image (deps, pypi indexes, compilers) and a deb build
# never links against it, so emitting those would only suggest they matter.
# Every name is emitted DEB_-prefixed so the container's build args cannot
# collide with anything the base image already exports.
BUILD_INPUT_FIELDS = (
    "name", "version", "base_image", "arch", "glibc_floor", "vendor", "codename",
    "make_flag", "make_env", "apt", "vendor_libs", "vendor_lib_dirs", "assert",
    "build_infra_version", "deb_package", "deb_provides", "deb_conflicts",
    "deb_replaces", "deb_conflicts_dev", "deb_replaces_dev",
)

# control.in placeholder -> the DEB_* variable that fills it verbatim.
CONTROL_VALUES = {
    "BACKEND": "DEB_NAME",
    "VENDOR": "DEB_VENDOR",
    "ARCH": "DEB_ARCH",
    "GLIBC_FLOOR": "DEB_GLIBC_FLOOR",
    "VENDOR_LIBS": "DEB_VENDOR_LIBS",
    "BUILD_IMAGE": "DEB_BASE_IMAGE",
    "BUILD_INFRA_VERSION": "DEB_BUILD_INFRA_VERSION",
}
# The relationship fields are the ones a backend may legitimately not have, so
# they carry the field name too. --build-inputs already emits them in control
# syntax (comma-separated names, `pkg (<< version)`), and the renderer only
# collapses whitespace: splitting them into tokens would turn
# `libflagcx-nvidia (<< ${binary:Version})` into three bogus packages. An absent
# one drops its whole line — these placeholders sit alone on their line, and a
# blank line inside a stanza would end it, sending Description: into a package
# of its own.
CONTROL_LINES = {
    "PROVIDES": ("Provides", "deb_provides"),
    "CONFLICTS": ("Conflicts", "deb_conflicts"),
    "REPLACES": ("Replaces", "deb_replaces"),
    "CONFLICTS_DEV": ("Conflicts", "deb_conflicts_dev"),
    "REPLACES_DEV": ("Replaces", "deb_replaces_dev"),
}
# Not optional: an empty one of these produces a control dpkg-buildpackage
# rejects, and the message it gives names the field, not the missing input.
CONTROL_REQUIRED = (
    "BACKEND", "VENDOR", "ARCH", "GLIBC_FLOOR", "VENDOR_LIBS",
    "BUILD_IMAGE", "BUILD_INFRA_VERSION",
)
PLACEHOLDER_RE = re.compile(r"@([A-Z0-9_]+)@")

# Ubuntu release -> the oldest glibc a binary built on it may assume. The floor
# itself is a packaging decision and lives in backends.yaml; this table only
# cross-checks it against the base image's own release, which is the failure
# that would otherwise ship a package that cannot install on its own runtime.
GLIBC_BY_UBUNTU = {"22.04": "2.35", "24.04": "2.39"}
UBUNTU_RE = re.compile(r"ubuntu[-:]?(\d{2}\.\d{2})", re.I)

# Ubuntu release -> the apt suite its repository is served under. Derived from the
# same release that names the repo, so the two cannot disagree. Lowercase because
# apt resolves the suite as a literal path, with no case folding.
CODENAME_BY_UBUNTU = {"22.04": "jammy", "24.04": "noble"}


def load_registry() -> dict:
    with REGISTRY.open() as fh:
        return yaml.safe_load(fh)


def load_matrix(path: Path | None) -> list[dict]:
    if path is None:
        proc = subprocess.run(
            [sys.executable, str(MATRIX_SCRIPT), "--runtime"],
            cwd=REPO, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            sys.exit(f"generate_matrix.py --runtime failed:\n{proc.stderr}")
        # A note about enabled-but-unbuildable backends goes to stderr; surface
        # it, because that is exactly the set --check must not call drift.
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        doc = json.loads(proc.stdout)
    else:
        with path.open() as fh:
            doc = json.load(fh)
    return doc["include"]


def base_image_ubuntu(key: str) -> str | None:
    """Ubuntu release base/<key> is built on, or None if it names != one.

    Only FROM lines count: a base Containerfile's comments name other Ubuntu
    releases on purpose (hygon's DTK is an Ubuntu-22.04 tarball unpacked into a
    24.04 base), and the release that sets the floor is the one being built on.
    """
    containerfile = REPO / "base" / key
    if not containerfile.is_file():
        return None
    releases = {
        release
        for line in containerfile.read_text().splitlines()
        if line.upper().startswith("FROM")
        for release in UBUNTU_RE.findall(line)
    }
    if len(releases) != 1:
        return None
    return releases.pop()


def base_image_glibc(key: str) -> str | None:
    release = base_image_ubuntu(key)
    return GLIBC_BY_UBUNTU.get(release) if release else None


def base_image_codename(key: str) -> str | None:
    release = base_image_ubuntu(key)
    return CODENAME_BY_UBUNTU.get(release) if release else None


def deb_name(key: str) -> str:
    return f"libflagcx-{key}"


def build_input_var(field: str) -> str:
    """Registry field name -> the variable `--build-inputs` emits.

    One DEB_ namespace for everything, and a leading `deb_` is absorbed rather
    than doubled (`deb_package` -> DEB_PACKAGE). debian/rules reads
    DEB_MAKE_FLAG/DEB_MAKE_ENV out of the environment and control.in is rendered
    from the same set, so there is exactly one naming rule to remember and no
    way for a matrix row to shadow a variable the base image already exports.
    """
    return "DEB_" + field.removeprefix("deb_").upper()


def merge(registry: dict, matrix: list[dict]) -> list[dict]:
    joined = []
    # Iterate the matrix, not the registry: the matrix carries the fields CI
    # needs to schedule a runner, and an enabled backend absent from it has no
    # base image to build in. Emitting such a row would reach the build job as
    # an empty `runs-on` instead; --check is what names the drift.
    for row in matrix:
        key = row["name"]
        spec = registry.get(key)
        if not spec or not (spec.get("deb") or {}).get("enabled"):
            continue
        entry = dict(row)
        for field in LIST_FIELDS:
            entry[field] = " ".join(spec.get(field) or [])
        entry["make_env"] = " ".join(
            f"{k}={v}" for k, v in sorted((spec.get("make_env") or {}).items())
        )
        entry["make_flag"] = spec["make_flag"]
        entry["vendor"] = spec["vendor"]
        entry["arch"] = spec["arch"]
        entry["glibc_floor"] = str(spec["glibc_floor"])
        # Not a deb_ field: it is the base image's release, carried so the verify
        # job can name the plain ubuntu:<release> the floor asserts against
        # without keeping a second copy of the floor table.
        entry["ubuntu"] = base_image_ubuntu(key) or ""
        # The suite the repository for that release is read back under.
        entry["codename"] = base_image_codename(key) or ""
        # The packaging is part of the stack release, so it carries the stack
        # release version. Reading it off the matrix rather than a field here is
        # the point: a version written into backends.yaml goes stale silently,
        # and the label exists to say which stack a .deb came out of.
        entry["build_infra_version"] = entry.get("version", "")
        entry["deb_package"] = deb_name(key)
        # Not every variant of a vendor is the vendor's package. Only the one
        # marked default_for_vendor answers to the unqualified name, and only it
        # may absorb the legacy package of that name — which is why Provides and
        # Replaces are gated on the same flag.
        default = bool((spec.get("deb") or {}).get("default_for_vendor"))
        legacy = f"libflagcx-{spec['vendor']}"
        entry["deb_provides"] = legacy if default else ""
        entry["deb_replaces"] = f"{legacy} (<< ${{binary:Version}})" if default else ""
        entry["deb_replaces_dev"] = (
            f"{legacy}-dev (<< ${{binary:Version}})" if default else ""
        )
        siblings = [
            other
            for other, other_spec in registry.items()
            if other != key
            and (other_spec.get("deb") or {}).get("enabled")
            and other_spec["arch"] == spec["arch"]
        ]
        entry["deb_conflicts"] = ", ".join(deb_name(other) for other in siblings)
        entry["deb_conflicts_dev"] = ", ".join(
            f"{deb_name(other)}-dev" for other in siblings
        )
        joined.append(entry)
    return joined


def check(registry: dict, matrix: list[dict]) -> list[str]:
    problems: list[str] = []
    matrix_keys = {entry["name"] for entry in matrix}

    for key in sorted(matrix_keys - set(registry)):
        problems.append(
            f"{key}: in the runtime matrix but not in backends.yaml — it is "
            f"buildable but has no packaging entry"
        )
    for key in sorted(set(registry) - matrix_keys):
        # generate_matrix.py prints its own note for these (no base/ file);
        # only an *enabled* one is drift, since it could never be built.
        if (registry[key].get("deb") or {}).get("enabled"):
            problems.append(
                f"{key}: enabled in backends.yaml but not in the runtime matrix "
                f"— no base image to build in"
            )

    # A placeholder with no value survives rendering and lands in debian/control
    # verbatim, where dpkg-buildpackage reports it as a malformed field — far
    # from the template edit that caused it. Catch it here instead.
    for placeholder in sorted(
        template_placeholders() - set(CONTROL_VALUES) - set(CONTROL_LINES)
    ):
        problems.append(
            f"control.in has @{placeholder}@ but no value is defined for it"
        )

    defaults: dict[str, list[str]] = {}
    flags: dict[str, dict[str, str]] = {}
    for key, spec in registry.items():
        deb = spec.get("deb") or {}
        enabled = bool(deb.get("enabled"))
        where = f"{key}: "

        missing = [f for f in REQUIRED_ENABLED if f not in spec]
        if missing:
            problems.append(where + f"missing field(s) {', '.join(missing)}")
            continue
        if not isinstance(deb.get("default_for_vendor"), bool):
            problems.append(where + "deb.default_for_vendor must be a boolean")
        if spec["arch"] not in VALID_ARCH:
            problems.append(where + f"arch {spec['arch']!r} not in {VALID_ARCH}")

        implied = base_image_glibc(key)
        if implied is None:
            problems.append(
                where + "could not read a single Ubuntu release from base/" + key
                + " — glibc_floor cannot be cross-checked"
            )
        elif str(spec["glibc_floor"]) != implied:
            problems.append(
                where + f"glibc_floor {spec['glibc_floor']} disagrees with the "
                f"base image's Ubuntu release (implies {implied})"
            )

        if enabled:
            if not spec.get("assert"):
                problems.append(
                    where + "assert is empty — the build would fail silently "
                    "rather than at the assert gate"
                )
            if deb.get("default_for_vendor"):
                defaults.setdefault(spec["vendor"], []).append(key)
            flags.setdefault(spec["vendor"], {})[key] = spec["make_flag"]

    for vendor, keys in sorted(defaults.items()):
        if len(keys) > 1:
            problems.append(
                f"vendor {vendor}: {len(keys)} variants claim "
                f"default_for_vendor ({', '.join(keys)}) — Provides: "
                f"libflagcx-{vendor} would have two providers"
            )
    enabled_vendors = {
        spec["vendor"]
        for spec in registry.values()
        if (spec.get("deb") or {}).get("enabled")
    }
    for vendor in sorted(enabled_vendors - set(defaults)):
        print(
            f"note: vendor {vendor} has no default_for_vendor variant, so no "
            f"package Provides: libflagcx-{vendor}",
            file=sys.stderr,
        )
    for vendor, per_key in sorted(flags.items()):
        if len(set(per_key.values())) > 1:
            problems.append(
                f"vendor {vendor}: make_flag differs across its backends "
                f"({per_key}) — one adaptor, one flag"
            )
    return problems


def template_placeholders() -> set[str]:
    return set(PLACEHOLDER_RE.findall((HERE / "debian" / "control.in").read_text()))


def render_control(out: Path) -> int:
    """Fill debian/control from control.in, values taken from the environment.

    Deliberately reads the environment instead of recomputing anything: the
    build script sources `--build-inputs` and calls this, so what the container
    builds is exactly what `--build-inputs` printed, with no second code path
    that could disagree.
    """
    template = (HERE / "debian" / "control.in").read_text()
    problems: list[str] = []

    def value_for(key: str) -> str:
        if key in CONTROL_LINES:
            field, source = CONTROL_LINES[key]
            raw = os.environ.get(build_input_var(source), "").strip()
            return f"{field}: {' '.join(raw.split())}" if raw else ""
        if key not in CONTROL_VALUES:
            problems.append(
                f"control.in has @{key}@ but no value is defined for it"
            )
            return ""
        raw = os.environ.get(CONTROL_VALUES[key], "").strip()
        if not raw:
            if key in CONTROL_REQUIRED:
                problems.append(
                    f"@{key}@ is empty — {CONTROL_VALUES[key]} is unset or blank"
                )
            return ""
        return raw

    rendered: list[str] = []
    for line in template.splitlines():
        stripped = line.strip()
        # A placeholder alone on its line is an optional field: absent, the whole
        # line goes, because a blank line inside a stanza terminates it and the
        # fields after it would become a package of their own.
        if stripped and PLACEHOLDER_RE.fullmatch(stripped):
            filled = value_for(stripped[1:-1])
            if filled:
                rendered.append(filled)
            continue
        rendered.append(PLACEHOLDER_RE.sub(lambda m: value_for(m.group(1)), line))

    text = "\n".join(rendered) + "\n"
    left = sorted(set(PLACEHOLDER_RE.findall(text)))
    if left:
        problems.append("unsubstituted placeholder(s): " + ", ".join(left))

    for problem in dict.fromkeys(problems):
        print(f"error: {problem}", file=sys.stderr)
    if problems:
        return 1
    out.write_text(text)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--merge", metavar="MATRIX_JSON", type=Path)
    g.add_argument("--check", action="store_true")
    g.add_argument("--build-inputs", metavar="KEY")
    g.add_argument("--render-control", metavar="OUT", type=Path)
    g.add_argument("--list", action="store_true")
    args = ap.parse_args()

    registry = load_registry()

    if args.render_control:
        return render_control(args.render_control)

    if args.list:
        for key, spec in registry.items():
            deb = spec.get("deb") or {}
            state = "ready" if deb.get("enabled") else "probe"
            default = " (default)" if deb.get("default_for_vendor") else ""
            print(f"{state:5}  {key}{default}")
        return 0

    if args.check:
        problems = check(registry, load_matrix(None))
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        if problems:
            return 1
        enabled = sum(
            1 for s in registry.values() if (s.get("deb") or {}).get("enabled")
        )
        print(f"ok: {enabled} enabled, {len(registry) - enabled} probe-pending")
        return 0

    if args.build_inputs:
        entries = {e["name"]: e for e in merge(registry, load_matrix(None))}
        if args.build_inputs not in entries:
            sys.exit(
                f"{args.build_inputs}: not an enabled backend "
                f"(see --list)"
            )
        entry = entries[args.build_inputs]
        # Quoted: several values carry spaces, so an unquoted KEY=a b line would
        # assign `a` and then try to *run* `b` when the script sources it.
        for name in BUILD_INPUT_FIELDS:
            print(
                f"{build_input_var(name)}={shlex.quote(str(entry.get(name, '')))}"
            )
        return 0

    print(json.dumps({"include": merge(registry, load_matrix(args.merge))}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
