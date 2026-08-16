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

"""Replace python3-config with sysconfig in compile_helpers() (no-op if done)."""

import pathlib
import sys

OLD = (
    "    ext_suffix = subprocess.check_output(\n"
    '        ["python3-config", "--extension-suffix"], text=True\n'
    "    ).strip()\n"
)
NEW = '    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")\n'


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <utils.py>", file=sys.stderr)
        return 2
    p = pathlib.Path(sys.argv[1])
    src = p.read_text()
    if NEW in src:
        return 0  # already patched (upstream PR merged)
    if OLD not in src:
        print("ERROR: source moved on; rework the patch", file=sys.stderr)
        return 1
    src = src.replace("    import subprocess\n", "    import subprocess\n    import sysconfig\n", 1)
    src = src.replace(OLD, NEW, 1)
    p.write_text(src)
    assert "    import sysconfig\n" in src and NEW in src, "patch did not land"
    return 0


if __name__ == "__main__":
    sys.exit(main())
