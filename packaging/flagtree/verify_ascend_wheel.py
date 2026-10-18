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

"""Build gates for the ascend FlagTree wheels (ascend-cann9.0.0, ascend-cann8.5.0):
fail the build on a wheel the ascend backends cannot use.

A file rather than a Dockerfile heredoc: the CANN build nodes still run Docker's
legacy builder, which has no heredoc support.

Requires the environment to carry CANN's variables (the images' BASH_ENV does) and
CANN_VERSION — the toolkit this wheel must be built against: the 3.5 line derives
its AscendNPU-IR pin from the CANN on the build machine, and both lines link that
CANN's BiShengIR dialects.
"""

import glob
import os
import platform
import re
import sys
import tempfile
import zipfile
from pathlib import Path

WHEELS = "/wheels"
# Trees the ascend install hooks ship (get_extra_install_packages); a missing one
# means the hook did not run.
EXTRA_TREES = (
    "triton/language/extra/cann",
    "triton/language/extra/kernels",
    "triton/extension",
    "triton/experimental/tle/language/dsa/ascend",
)
# The runtime images run cp311 on aarch64. A wheel tagged otherwise means the
# build ran with the wrong interpreter or on the wrong runner.
ARCH_TAG = "-cp311-cp311-linux_aarch64"
# The install-info file names CANN ships, in preference order.
INSTALL_INFO_FILES = ("ascend_toolkit_install.info", "ascend_all_cann_install.info")


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def installed_internals():
    """The PYBIND11_INTERNALS_VERSION of the pybind11 this build installed.

    Read out of pybind11's own header, the way FlagTree's own
    _installed_pybind11_internals() does, rather than pinned as a literal here:
    the pin is PYBIND11_VERSION, and this is what proves the build used it.
    """
    import pybind11
    hdr = Path(pybind11.get_include()) / "pybind11" / "detail" / "internals.h"
    try:
        m = re.search(r"#\s*define\s+PYBIND11_INTERNALS_VERSION\s+(\d+)", hdr.read_text())
    except OSError:
        return None, getattr(pybind11, "__version__", None)
    return (m.group(1).encode() if m else None), getattr(pybind11, "__version__", None)


def cann_version():
    """The CANN version this image provides — flagtree's ascend.py:get_cann_version
    probes the same two roots for the same version= line.

    Both names: flagtree reads ascend_toolkit_install.info, which a CANN 9.0.0
    install does not ship (it ships ascend_all_cann_install.info, and flagtree
    therefore falls back to its default pin), while 8.5.0 ships the toolkit file.
    The version is the contract here, not the file name.
    """
    arch = platform.machine()
    roots = []
    if os.environ.get("ASCEND_HOME_PATH"):
        roots.append(Path(os.environ["ASCEND_HOME_PATH"]))
    roots.append(Path("/usr/local/Ascend/ascend-toolkit/latest"))
    for root in roots:
        for name in INSTALL_INFO_FILES:
            try:
                text = (root / f"{arch}-linux" / name).read_text()
            except OSError:
                continue
            for line in text.splitlines():
                if line.startswith("version="):
                    return line.split("=", 1)[1].strip()
    return ""


def internals(path):
    with open(path, "rb") as f:
        return sorted(set(re.findall(rb"__pybind11_internals_v(\d+)", f.read())))


def main():
    whl = glob.glob(f"{WHEELS}/*.whl")
    if len(whl) != 1:
        fail(f"expected exactly one wheel in {WHEELS}, found {whl}")
    whl = whl[0]
    base = os.path.basename(whl)
    ver = base.split("-")[1]

    # Version gate: a clean version. FlagTree's setup.py stamps "<ver>.git<sha>"
    # unless the build dropped .git first — a dirty version means it was not.
    if "git" in ver:
        fail(f"dirty wheel version '{ver}' (expected clean, no git<sha> suffix)")
    if ARCH_TAG not in base:
        fail(f"wheel '{base}' not tagged {ARCH_TAG}")
    print(f"OK: clean wheel version '{ver}', cp311/aarch64")

    expected = os.environ.get("CANN_VERSION", "")
    found = cann_version()
    if not expected:
        fail("CANN_VERSION is not set (it is the pairing gate, not decoration)")
    if found != expected:
        fail(f"build machine CANN '{found or '<not found>'}' != expected '{expected}' "
             "(wrong BUILDER_IMAGE: the wheel is built against the CANN it finds there)")
    print(f"OK: build machine CANN {found} matches CANN_VERSION")

    d = tempfile.mkdtemp()
    zipfile.ZipFile(whl).extractall(d)
    missing = [p for p in EXTRA_TREES if not os.path.exists(os.path.join(d, p))]
    if missing:
        fail(f"wheel missing {missing}")
    print("OK: wheel ships the ascend extra trees " + " / ".join(EXTRA_TREES))

    # The carrier the build writes: .git is dropped for the clean version, so the
    # commit only survives if setuptools merged the setup.cfg the build left in
    # the clone. Asserted here rather than assumed, because it is the only record
    # of what the wheel was built from.
    with zipfile.ZipFile(whl) as zf:
        meta = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
        lines = zf.read(meta).decode().splitlines()
    source_commits = [l for l in lines if l.startswith("Project-URL: Source-Commit, ")]
    if len(source_commits) != 1 or not source_commits[0].startswith(
            "Project-URL: Source-Commit, https://github.com/flagos-ai/flagtree/commit/"):
        fail(f"wheel METADATA carries {source_commits} (expected one Source-Commit "
             "Project-URL; the build's setup.cfg carrier did not survive)")
    print(f"OK: {source_commits[0]}")

    so = next(iter(glob.glob(d + "/**/libtriton.so", recursive=True)), None)
    if so is None:
        fail("no libtriton.so in the wheel")
    # The comparison, not a literal: libtriton and the ascend plugin it links
    # share pybind11 type registries only when their internals versions match, and
    # a mismatch is the metax/sunrise failure mode -- the wheel imports fine on a
    # GPU-less box and only breaks at kernel-compile time on real hardware. What
    # the build installed is read from pybind11 itself, so the pin and this gate
    # cannot drift apart.
    want, pybind11_version = installed_internals()
    if want is None:
        fail("could not read PYBIND11_INTERNALS_VERSION from the installed pybind11 "
             f"({pybind11_version!r})")
    got = internals(so)
    if got != [want]:
        fail(f"libtriton.so pybind11 internals {got}, the build's pybind11 "
             f"{pybind11_version} provides [{want!r}]")
    others = {tuple(v) for p in glob.glob(d + "/**/*.so", recursive=True)
              if p != so and (v := internals(p))}
    if others - {(want,)}:
        fail(f"shipped .so files expose other pybind11 internals {others}")
    print(f"OK: libtriton.so and the wheel's other .so files carry pybind11 internals "
          f"v{want.decode()}, the build's pybind11 {pybind11_version}")


if __name__ == "__main__":
    main()
