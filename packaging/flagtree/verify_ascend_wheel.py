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

"""Build gates for the ascend FlagTree wheels (packaging/flagtree/ascend3.5 and
ascend3.2). Fails the build on a wheel the ascend backends cannot use.

Shared by both targets — they gate the same things. It is a file rather than a
Dockerfile heredoc because the CANN build nodes still run Docker's legacy
builder, which has no heredoc support (heredocs work on the h20 runner, which
has BuildKit, so the non-ascend builders can keep inlining theirs).

Requires the environment to carry CANN's variables (the images' BASH_ENV does),
and CANN_VERSION, the toolkit the wheel must pair with: FlagTree's ascend build
derives the AscendNPU-IR pin from the CANN found on the build machine, so a
mismatch here means the wheel was built against the wrong bishengir.
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
# libtriton and the ascend plugin share pybind11 type registries; the runtime
# venv ships pybind11 3.0.3, whose internals version is this. A drift is the
# metax/sunrise failure mode: the wheel imports fine on a GPU-less box and only
# breaks at kernel-compile time on real hardware.
PYBIND11_INTERNALS = b"11"


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def cann_version():
    """Mirror of FlagTree's python/setup_tools/utils/ascend.py:get_cann_version,
    which is what selects the AscendNPU-IR pin."""
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
             "(wrong BASE_IMAGE: the wheel is built against the CANN it finds there)")
    print(f"OK: build machine CANN {found} matches CANN_VERSION")

    d = tempfile.mkdtemp()
    zipfile.ZipFile(whl).extractall(d)
    missing = [p for p in EXTRA_TREES if not os.path.exists(os.path.join(d, p))]
    if missing:
        fail(f"wheel missing {missing}")
    print("OK: wheel ships the ascend extra trees " + " / ".join(EXTRA_TREES))

    so = next(iter(glob.glob(d + "/**/libtriton.so", recursive=True)), None)
    if so is None:
        fail("no libtriton.so in the wheel")
    got = internals(so)
    if got != [PYBIND11_INTERNALS]:
        fail(f"libtriton.so pybind11 internals {got} (expected "
             f"[{PYBIND11_INTERNALS!r}]; adjust PYBIND11_VERSION)")
    others = {tuple(v) for p in glob.glob(d + "/**/*.so", recursive=True)
              if p != so and (v := internals(p))}
    if others - {(PYBIND11_INTERNALS,)}:
        fail(f"shipped .so files expose other pybind11 internals {others}")
    print(f"OK: libtriton.so pybind11 internals v{PYBIND11_INTERNALS.decode()}")


if __name__ == "__main__":
    main()
