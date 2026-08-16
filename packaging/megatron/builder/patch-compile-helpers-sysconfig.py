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

"""On-the-fly patch: compile_helpers() extension suffix via sysconfig.

Megatron-LM-FL's compile_helpers() (megatron/core/datasets/utils.py, a
FlagOS fork addition) shells out to `python3-config --extension-suffix` to
locate the prebuilt helpers_cpp .so. python3-config is a CPython build
artifact, not a pip package — uv-created venvs (as in the runtime images)
do not carry it, so the dataset import path dies with FileNotFoundError.

The proper fix is upstream: Megatron-LM-FL PR #112 switches to
sysconfig.get_config_var("EXT_SUFFIX") (stdlib, present in every Python).
This script is the build-infra fallback that applies the same change on the
fly during wheel builds while that PR is unmerged. It is idempotent and
fails loudly if the source moved on (exit 1 when neither form is found),
so a silently-skipped patch can never ship a wheel that still needs
python3-config.

Usage: python patch-compile-helpers-sysconfig.py <megatron/core/datasets/utils.py>
"""

import pathlib
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch-compile-helpers-sysconfig.py <utils.py>", file=sys.stderr)
        return 2
    p = pathlib.Path(sys.argv[1])
    src = p.read_text()
    marker = 'sysconfig.get_config_var("EXT_SUFFIX")'
    old_import = "    import subprocess\n"
    old_body = (
        "    ext_suffix = subprocess.check_output(\n"
        '        ["python3-config", "--extension-suffix"], text=True\n'
        "    ).strip()\n"
    )
    if marker in src:
        print(">>> compile_helpers: sysconfig form already present (no-op)")
    elif old_body in src:
        assert old_import in src, "compile_helpers imports changed unexpectedly"
        src = src.replace(old_import, old_import + "    import sysconfig\n", 1)
        src = src.replace(
            old_body,
            '    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")\n',
            1,
        )
        p.write_text(src)
        print(">>> compile_helpers: patched python3-config -> sysconfig")
    else:
        print(
            "ERROR: compile_helpers source moved on — neither python3-config "
            "nor sysconfig form found; rework the builder patch",
            file=sys.stderr,
        )
        return 1
    assert marker in p.read_text(), "compile_helpers sysconfig patch did not land"
    print("gate OK: compile_helpers uses sysconfig")
    return 0


if __name__ == "__main__":
    sys.exit(main())
