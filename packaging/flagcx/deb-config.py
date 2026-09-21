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
  --check-version-label <key>
                          print the local version label the row publishes, and
                          name it when that differs from the matrix suffix
                          a PEP 440 round trip rewrote

--channel {deb,wheel,builder} (default deb) picks the product: which rows are
enabled (`deb.enabled` / `wheel.enabled` / `builder.enabled`) and which fields
the joined entry carries — the .deb channel derives deb_package and the control
relationships, the wheel channel the wheel_* identity fields, the builder
channel the image ref it publishes, built on the row's runtime image. The
joining and the drift alarm are the same in all three.
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
BUILD_CONFIG = REPO / ".github" / "build-config.yml"

# Fields that are lists in the registry and strings in the CI matrix — a build
# arg can only be a string, and the workflow passes every field through as one.
LIST_FIELDS = ("apt", "vendor_libs", "vendor_lib_dirs", "assert")
REQUIRED_ENABLED = ("vendor", "make_flag", "arch", "glibc_floor", "deb")
# The wheel channel's own list, deliberately smaller and deliberately separate.
# glibc_floor and deb are absent because a wheel embodies neither: its platform
# tag is linux_x86_64, which claims more than any floor states (an open item,
# see WHEEL-DESIGN.md), and it has no control stanza. `make_flag` stays because
# a row that names an adaptor has to name its USE_* flag too — the two are one
# choice spelled twice, and the deb channel is not the only reader of it.
REQUIRED_WHEEL_ENABLED = ("vendor", "make_flag", "arch")
# The builder channel needs even less: it installs a toolchain and builds no
# FlagCX source, so neither the adaptor flag nor the packaging decisions that
# only a .deb or a wheel embodies apply. `assert` is not listed because
# check() requires it of every enabled row on every channel — a builder whose
# SDK assertion list is empty would install a toolchain and prove nothing. The
# bitcode fields are required the same way and in the same place: of an enabled
# builder row, not of the eighteen rows that have no builder at all.
REQUIRED_BUILDER_ENABLED = ("vendor", "arch")
# _build_config.py rejects `flagos` for the du/metax adaptors outright, so a row
# carrying it can only ever build a wheel that fails on import. Widening this is
# a per-adaptor decision, not a default.
VALID_WHEEL_TORCH_BACKENDS = ("vendor",)
VALID_ARCH = ("amd64", "arm64")
# Debian's package-name grammar, which is stricter than anything the registry
# enforces: no uppercase, no underscore. dpkg-gencontrol applies it deep inside
# the build and names the field rather than the offending character, so a name
# this far from legal is worth catching at the gate.
DEB_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")

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

# The wheel channel's own set, not a superset: a wheel is built in the *runtime*
# image (image_tag) rather than the base one, has no control stanza, and stamps
# its identity from the wheel_* names instead of a package name. Emitting the
# relationship fields here would suggest they reach a package that does not
# exist on this channel.
WHEEL_BUILD_INPUT_FIELDS = (
    "name", "version", "image_tag", "arch", "python_version",
    "wheel_version_suffix", "wheel_local_version", "wheel_python_tag",
    "wheel_torch_backend", "wheel_adaptor", "wheel_make_env", "wheel_cuda_path",
    "wheel_index_url", "wheel_assert",
)

# The builder channel's own set. It builds an image rather than an artifact, so
# it reads the row's runtime image (`image_tag`, the same one the wheel builds
# in) and the two lists the image has to install. `arch`, `vendor` and `version`
# are carried for the image tag and the labels; `make_env` and the bitcode pair
# are not inputs to the image at all — they are what the verification rebuilds
# the device bitcode with, which is the row's acceptance test. The wheel_*
# identity fields are absent because nothing here is published to an index.
BUILDER_BUILD_INPUT_FIELDS = (
    "name", "version", "image_tag", "builder_image", "arch", "vendor",
    "apt", "builder_apt", "assert", "make_env",
    "bitcode_arch", "bitcode_adaptor_flag",
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


def registry_prefix(name: str) -> str | None:
    """One of build-config.yml's image prefixes, or None if it is not there.

    Only the prefix is read: every matrix row already carries the registry host
    in `image_tag` — the same host every other layer is pushed to — so taking it
    from the row is one source for it rather than two.
    """
    if not BUILD_CONFIG.is_file():
        return None
    with BUILD_CONFIG.open() as fh:
        cfg = yaml.safe_load(fh) or {}
    prefixes = (cfg.get("registry") or {}).get("prefixes") or {}
    return prefixes.get(name) or None


def builder_image(key: str, entry: dict) -> str:
    """The builder image ref this row publishes, or "" if it cannot be named.

    Derived here rather than in the build script for the same reason deb_name()
    is: it is this channel's artifact identity, and the build and the verify
    scripts both have to arrive at it without either owning a second spelling
    of it.
    """
    image_tag = entry.get("image_tag", "")
    host = image_tag.split("/", 1)[0] if "/" in image_tag else ""
    prefix = registry_prefix("builder")
    if not host or not prefix:
        return ""
    return f"{host}/{prefix}/flagcx-builder-{key}:{entry.get('version', '')}"


def version_label(key: str) -> str:
    """The local version label a backend's wheel carries.

    Derived from the backend key and not from a field, because the whole point
    of the label is that it is the matrix name's second segment: two rows of one
    commit get two versions only if the label is a property of the row. `vendor`
    cannot stand in for it — that is the FlagCX adaptor family, and hygon's
    adaptor is `du`, which names no vendor at all.
    """
    return key.split("-", 1)[1] if "-" in key else key


def label_problem(key: str) -> str | None:
    """Why a backend's local label cannot be published at all, or None if it can.

    The check is a parse through `packaging` rather than a hand-written grammar
    because normalisation is its rule, not a syntax question: a `-` inside a
    local segment is a segment separator, and uppercase is lowercased. A label
    that parses but reads back spelled differently is not a problem — it is
    published under the spelling `wheel_label()` returns, and nothing downstream
    ever sees the raw one. Only a label `packaging` refuses outright is fatal,
    because setuptools would refuse the version and there would be no artifact
    to pin.

    The string checked is the published one and not the suffix, because the
    published one is what setuptools is handed; a row published under a
    spelled-out label has to clear the gate in that spelling.
    """
    published = wheel_label(key)
    try:
        label_round_trip(published)
    except ImportError:
        # Only the wheel channel has a set-matrix step that installs `packaging`;
        # the deb channel has never needed it and does not get it here.
        return "python3-packaging is not installed, so the label cannot be checked"
    except ValueError as exc:
        return f"label {published!r} is not a legal version local part: {exc}"
    return None


def label_round_trip(label: str) -> str:
    """The label as PEP 440 reads it back (`dtk26.04` -> `dtk26.4`).

    A numeric local segment loses its leading zero. That is a write-through, not
    a display quirk: a wheel asked for `+dtk26.04` is written as `+dtk26.4`.
    No enabled row asks for that spelling — wheel_label() answers the one row it
    would apply to first — so today this rule is what the labels are checked
    against, not what produces them.
    """
    from packaging.version import Version

    return str(Version("0+" + label))[2:]


# The one row whose published label is not what PEP 440 makes of its suffix.
# DTK's release is spelled `26.04` — the runtime image is
# `flagos-runtime-hygon-dtk26.04:2.1.2` — and PEP 440 cannot carry that spelling:
# a numeric local segment loses its leading zero, so `+dtk26.04` is written as
# `+dtk26.4`. Publishing the normalised form would rename the vendor SDK in the
# one place a reader goes to read its name. Spelled out here rather than derived
# by a rule: no other row has a vendor version whose leading zero is part of its
# name, and a general rewriting rule would respell a suffix nobody has seen yet.
DTK_KEY = "hygon-dtk26.04"
DTK_PUBLISHED_LABEL = "dtk2604"


def wheel_label(key: str) -> str:
    """The label as it is actually published: the matrix suffix, normalised.

    setuptools writes the version it is given through `packaging`, so a suffix
    lands spelled as that reading of it. `maca3.7.2.1` survives untouched;
    `dtk26.04` does not, and a real `pip wheel` asked for it comes back
    `flagcx-0.14.0.dev14+dtk26.4.20260915.g08ab373-py3-none-any.whl`. Both the
    exported FLAGCX_VERSION_SUFFIX and the asserted local label have to be the
    spelling the artifact carries: a row asserting a suffix no artifact has would
    name a version that does not exist, and the host-side filename assertion in
    build-flagcx-wheel.sh — deliberately plain string work, because the hygon
    runner's python has no pip and no `packaging` — could not match the file
    without reimplementing PEP 440's rules.

    The DTK row is answered before `packaging` is consulted (see DTK_KEY): its
    label is decided here and not read off the suffix, so a runner that cannot
    normalise still exports the spelling the index will carry.

    Falls back to the raw suffix when `packaging` is missing: that is
    `--check --channel wheel`'s failure to report, not a merge's to abort on.
    """
    if key == DTK_KEY:
        return DTK_PUBLISHED_LABEL
    label = version_label(key)
    try:
        return label_round_trip(label)
    except (ImportError, ValueError):
        return label


def legacy_name(vendor: str) -> str:
    """The pre-rename package name for a vendor's adaptor family.

    The adaptor family name is FlagCX's, so it is not bound by Debian's
    package-name grammar — iluvatar_corex carries an underscore, which
    dpkg-gencontrol rejects outright in Provides/Replaces. Sanitized here rather
    than in backends.yaml, because `vendor` has to stay the string the makefiles
    and _build_config.py use.
    """
    return "libflagcx-" + vendor.replace("_", "-")


def relationship_fields(key: str, spec: dict, registry: dict) -> dict[str, str]:
    """The control relationship fields derived for one backend.

    Shared by --merge and --check so the gate validates exactly the strings the
    build would emit: a second derivation for the gate is the drift the gate
    exists to catch.
    """
    # Not every variant of a vendor is the vendor's package. Only the one marked
    # default_for_vendor answers to the unqualified name, and only it may absorb
    # the legacy package of that name — which is why Provides and Replaces are
    # gated on the same flag.
    legacy = legacy_name(spec["vendor"])
    if (spec.get("deb") or {}).get("default_for_vendor"):
        provides = legacy
        replaces = f"{legacy} (<< ${{binary:Version}})"
        replaces_dev = f"{legacy}-dev (<< ${{binary:Version}})"
    else:
        provides = replaces = replaces_dev = ""
    # Every enabled backend of an architecture installs the same soname and the
    # same headers, so dpkg has to be told they cannot coexist rather than left
    # to fail on "trying to overwrite" at install time.
    siblings = [
        other
        for other, other_spec in registry.items()
        if other != key
        and (other_spec.get("deb") or {}).get("enabled")
        and other_spec["arch"] == spec["arch"]
    ]
    return {
        "deb_provides": provides,
        "deb_replaces": replaces,
        "deb_replaces_dev": replaces_dev,
        "deb_conflicts": ", ".join(deb_name(other) for other in siblings),
        "deb_conflicts_dev": ", ".join(
            f"{deb_name(other)}-dev" for other in siblings
        ),
    }


def build_input_var(field: str) -> str:
    """Registry field name -> the variable `--build-inputs` emits.

    One DEB_ namespace for everything, and a leading `deb_` is absorbed rather
    than doubled (`deb_package` -> DEB_PACKAGE). debian/rules reads
    DEB_MAKE_FLAG/DEB_MAKE_ENV out of the environment and control.in is rendered
    from the same set, so there is exactly one naming rule to remember and no
    way for a matrix row to shadow a variable the base image already exports.
    """
    return "DEB_" + field.removeprefix("deb_").upper()


def merge(registry: dict, matrix: list[dict], channel: str = "deb") -> list[dict]:
    deb = channel == "deb"
    wheel = channel == "wheel"
    builder = channel == "builder"
    joined = []
    # Iterate the matrix, not the registry: the matrix carries the fields CI
    # needs to schedule a runner, and an enabled backend absent from it has no
    # base image to build in. Emitting such a row would reach the build job as
    # an empty `runs-on` instead; --check is what names the drift.
    for row in matrix:
        key = row["name"]
        spec = registry.get(key)
        if not spec or not (spec.get(channel) or {}).get("enabled"):
            continue
        entry = dict(row)
        for field in LIST_FIELDS:
            entry[field] = " ".join(spec.get(field) or [])
        entry["make_env"] = " ".join(
            f"{k}={v}" for k, v in sorted((spec.get("make_env") or {}).items())
        )
        # The adaptor flag is the deb and wheel builds' input; a builder rows it
        # too (the image is the wheel's environment), but nothing on this
        # channel reads it, so it is not required of a builder row.
        entry["make_flag"] = spec.get("make_flag", "")
        entry["vendor"] = spec["vendor"]
        entry["arch"] = spec["arch"]
        entry["glibc_floor"] = str(spec.get("glibc_floor", ""))
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
        if wheel:
            # FLAGCX_VERSION_SUFFIX and the asserted local label are the same
            # string on purpose: what the build is told to stamp and what is
            # checked to have been stamped must not be two derivations. Both are
            # the published spelling rather than the matrix suffix — FlagCX
            # appends the suffix verbatim into a local part, and setuptools then
            # normalises what it writes (see wheel_label).
            label = wheel_label(key)
            entry["wheel_version_suffix"] = label
            entry["wheel_local_version"] = label
            entry["wheel_python_tag"] = "cp3" + entry["python_version"].split(".", 1)[1]
            entry["wheel_torch_backend"] = (spec.get("wheel") or {}).get(
                "torch_backend", "vendor"
            )
            # The adaptor family, not the index vendor — _build_config.py keys
            # off this name to pick the make flag and the adaptor sources.
            entry["wheel_adaptor"] = spec["vendor"]
            entry["wheel_make_env"] = entry["make_env"]
            # The build reads CUDA_PATH/CUDA_HOME, never DEVICE_HOME, so the value
            # is surfaced under the name it actually reads. Same root as the make
            # env on most rows; MACA overrides it because pointing DEVICE_HOME at
            # its cu-bridge would move metax.mk's compiler and include path too.
            entry["wheel_cuda_path"] = (spec.get("wheel") or {}).get(
                "cuda_path"
            ) or (spec.get("make_env") or {}).get("DEVICE_HOME", "")
            entry["wheel_index_url"] = entry.get("flagos_pypi", "")
            entry["wheel_assert"] = " ".join(spec.get("assert") or [])
        elif deb:
            entry["deb_package"] = deb_name(key)
            entry.update(relationship_fields(key, spec, registry))
        else:
            # The builder's own increment, kept apart from `apt` above rather
            # than merged into it: the two are installed by one step but they
            # answer different questions. `apt` is the row's SDK — the same list
            # the .deb line states, installed here because this build needs it
            # too — while this one is build-time-only and no other channel has
            # it.
            entry["builder_apt"] = " ".join(
                (spec.get("builder") or {}).get("apt") or []
            )
            # Not under `builder:` in the registry: nothing in the image depends
            # on either, so a block that also holds what the image installs would
            # read as if they were installed too. They are the row's device
            # bitcode — the arch it is compiled for and the comm-traits branch it
            # takes — which the verification rebuilds and the wheel build will
            # consume.
            entry["bitcode_arch"] = spec.get("bitcode_arch", "")
            entry["bitcode_adaptor_flag"] = spec.get("bitcode_adaptor_flag", "")
            entry["builder_image"] = builder_image(key, entry)
        joined.append(entry)
    return joined


def check(registry: dict, matrix: list[dict], channel: str = "deb") -> list[str]:
    deb = channel == "deb"
    wheel = channel == "wheel"
    builder = channel == "builder"
    required = {
        "deb": REQUIRED_ENABLED,
        "wheel": REQUIRED_WHEEL_ENABLED,
        "builder": REQUIRED_BUILDER_ENABLED,
    }[channel]
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
        if (registry[key].get(channel) or {}).get("enabled"):
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
        chan = spec.get(channel) or {}
        enabled = bool(chan.get("enabled"))
        where = f"{key}: "

        missing = [f for f in required if f not in spec]
        if missing:
            problems.append(where + f"missing field(s) {', '.join(missing)}")
            continue
        if wheel:
            # pip resolves a pin by name and has no Provides:, so deb's
            # one-default-per-vendor idea has nothing to say on this channel —
            # a row carrying it reads as if it did something.
            if "default_for_vendor" in chan:
                problems.append(
                    where + "wheel.default_for_vendor has no meaning (pip has "
                    "no Provides:) — it belongs to the deb block"
                )
        elif deb:
            if not isinstance(chan.get("default_for_vendor"), bool):
                problems.append(where + "deb.default_for_vendor must be a boolean")
        elif "default_for_vendor" in chan:
            # Same reasoning as the wheel channel's: a builder publishes an
            # image, which answers to no apt name.
            problems.append(
                where + "builder.default_for_vendor has no meaning (an image is "
                "not installed by name) — it belongs to the deb block"
            )
        if spec["arch"] not in VALID_ARCH:
            problems.append(where + f"arch {spec['arch']!r} not in {VALID_ARCH}")

        # glibc_floor is a deb requirement (see REQUIRED_ENABLED) and a wheel
        # makes no such claim — its platform tag is linux_x86_64, which says
        # both more and less. A wheel row that states one anyway is
        # cross-checked here like any other.
        if "glibc_floor" in spec:
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

        if not enabled:
            continue
        if not spec.get("assert"):
            problems.append(
                where + "assert is empty — the build would fail silently "
                "rather than at the assert gate"
            )
        # A builder that cannot be shown to compile the row's device bitcode is
        # a large base image and nothing more: the verification is what the row
        # is published on, and without these two it would rebuild at the
        # Makefile's own defaults and answer a question about some other row.
        if builder and not (
            spec.get("bitcode_arch") and spec.get("bitcode_adaptor_flag")
        ):
            problems.append(
                where + "no bitcode_arch/bitcode_adaptor_flag — nothing would "
                "state which device bitcode this row is verified on"
            )
        # Only the deb channel derives package relationships, so only it has
        # anything to collect below.
        if not deb:
            continue
        if chan.get("default_for_vendor"):
            defaults.setdefault(spec["vendor"], []).append(key)
        flags.setdefault(spec["vendor"], {})[key] = spec["make_flag"]

    # The package name and the relationship fields are derived, not read, so no
    # check above has seen them as strings. Debian's name grammar is stricter
    # than anything the registry enforces, dpkg-gencontrol applies it deep inside
    # the build, and it names the field rather than the character that broke it —
    # which is how an adaptor family name carrying an underscore
    # (iluvatar_corex) reached the link and only died there.
    if deb:
        for entry in merge(registry, matrix, channel):
            key = entry["name"]
            for field in ("deb_package", "deb_provides", "deb_replaces",
                          "deb_replaces_dev", "deb_conflicts", "deb_conflicts_dev"):
                for clause in (entry.get(field) or "").split(","):
                    # `pkg (<< ${binary:Version})` is one relationship, not three
                    # tokens, and no legal package name contains a parenthesis.
                    name = clause.split("(")[0].strip()
                    if name and not DEB_NAME_RE.match(name):
                        problems.append(
                            f"{key}: {field} carries {name!r}, which is not a legal "
                            f"Debian package name"
                        )

    if wheel:
        # One identity per row, or one pin for two artifacts. pip's `==` ignores
        # the local part, so two rows sharing (label, python tag, torch backend)
        # are two different builds answering to one pin — and the second upload
        # would report success while replacing the first. The deb channel's
        # counterpart rule is the one-default-per-vendor check below.
        identities: dict[tuple[str, str, str], list[str]] = {}
        for entry in merge(registry, matrix, channel):
            key = entry["name"]
            problem = label_problem(key)
            if problem:
                problems.append(f"{key}: {problem}")
            identities.setdefault(
                (
                    entry["wheel_local_version"],
                    entry["wheel_python_tag"],
                    entry["wheel_torch_backend"],
                ),
                [],
            ).append(entry["name"])
        for identity, keys in sorted(identities.items()):
            if len(keys) > 1:
                problems.append(
                    f"wheel {identity[0]} ({identity[1]}, {identity[2]}): "
                    f"{len(keys)} backends share it ({', '.join(keys)}) — "
                    f"one pin, two artifacts"
                )

    if builder:
        # The ref is derived, so no check above has seen it as a string: it needs
        # the row's matrix entry for the registry host and build-config.yml for
        # the prefix, and a row missing either would push to a name that is not
        # the one its consumers look for.
        for entry in merge(registry, matrix, channel):
            if not entry.get("builder_image"):
                problems.append(
                    f"{entry['name']}: the builder image has no ref — the matrix "
                    f"entry carries no registry host in image_tag, or "
                    f"build-config.yml states no registry.prefixes.builder"
                )

    for vendor, keys in sorted(defaults.items()):
        if len(keys) > 1:
            problems.append(
                f"vendor {vendor}: {len(keys)} variants claim "
                f"default_for_vendor ({', '.join(keys)}) — Provides: "
                f"libflagcx-{vendor} would have two providers"
            )
    # Nothing to note on the wheel or builder channels: neither has a Provides:
    # to be missing, and the note would name every row on them.
    if deb:
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
    g.add_argument("--check-version-label", metavar="KEY")
    g.add_argument("--render-control", metavar="OUT", type=Path)
    g.add_argument("--list", action="store_true")
    ap.add_argument(
        "--channel",
        choices=("deb", "wheel", "builder"),
        default="deb",
        help="which product to describe; the row set and the derived fields "
             "differ, the join and the drift alarm do not (default: deb)",
    )
    args = ap.parse_args()

    registry = load_registry()

    if args.render_control:
        return render_control(args.render_control)

    if args.list:
        for key, spec in registry.items():
            chan = spec.get(args.channel) or {}
            state = "ready" if chan.get("enabled") else "probe"
            default = " (default)" if chan.get("default_for_vendor") else ""
            print(f"{state:5}  {key}{default}")
        return 0

    if args.check:
        problems = check(registry, load_matrix(None), args.channel)
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        if problems:
            return 1
        enabled = sum(
            1
            for s in registry.values()
            if (s.get(args.channel) or {}).get("enabled")
        )
        pending = len(registry) - enabled
        if args.channel == "deb":
            # "probe-pending" is the deb channel's word for a row whose in-
            # container probe has not run yet. Most rows are simply not on the
            # other two channels, and saying otherwise would read as owed work.
            print(f"ok: {enabled} enabled, {pending} probe-pending")
        else:
            print(f"ok: {enabled} {args.channel}-enabled, {pending} off this channel")
        return 0

    if args.check_version_label:
        key = args.check_version_label
        if key not in registry:
            print(f"error: {key}: not in backends.yaml", file=sys.stderr)
            return 2
        problem = label_problem(key)
        if problem:
            print(f"error: {key}: {problem}", file=sys.stderr)
            return 1
        suffix = version_label(key)
        published = wheel_label(key)
        # A rewrite is not a failure: the published spelling is derived by
        # wheel_label() and every consumer gets the derived one, so nothing in
        # the pipeline can be holding the suffix. It is worth naming anyway —
        # it is the spelling a pin must carry, and the suffix is what a reader
        # finds in backends.yaml. Two different things cause it, and saying
        # which one is the difference between a reader trusting the note and
        # going to look for a normalisation bug that is not there.
        if published != suffix:
            cause = (
                "the published label is spelled out on purpose (see DTK_KEY)"
                if key == DTK_KEY
                else "PEP 440 normalises the local part"
            )
            print(
                f"note: {key}: suffix {suffix} is published as {published} — "
                f"{cause}, so pins must say {published}"
            )
        print(f"ok: {key}: label {published}")
        return 0

    if args.build_inputs:
        entries = {
            e["name"]: e
            for e in merge(registry, load_matrix(None), args.channel)
        }
        if args.build_inputs not in entries:
            sys.exit(
                f"{args.build_inputs}: not an enabled backend "
                f"(see --list)"
            )
        entry = entries[args.build_inputs]
        fields = {
            "deb": BUILD_INPUT_FIELDS,
            "wheel": WHEEL_BUILD_INPUT_FIELDS,
            "builder": BUILDER_BUILD_INPUT_FIELDS,
        }[args.channel]
        # Quoted: several values carry spaces, so an unquoted KEY=a b line would
        # assign `a` and then try to *run* `b` when the script sources it.
        for name in fields:
            print(
                f"{build_input_var(name)}={shlex.quote(str(entry.get(name, '')))}"
            )
        return 0

    print(
        json.dumps(
            {
                "include": merge(
                    registry, load_matrix(args.merge), args.channel
                )
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
