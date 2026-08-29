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

"""Audit a built wheel's declared dependencies against the critical set.

The runtime image bakes a pinned matrix (torch / triton / flag_gems / …);
app images install wheels single-step, so a wheel that *declares* one of
these would give pip a reason to resolve/upgrade it and silently drift the
matrix (see docs/sglang-0.5.18/decisions.md §2). The sglang wheel builds
torch-free by construction; the sglang-plugin-FL wheel, like vllm-plugin-FL,
ships with an empty requirement set — torch comes from the image, never
from the wheel.

A watch entry ending in ``*`` is a prefix match (e.g. ``nvidia-*`` matches
``nvidia-cudnn-cu13``, ``flashinfer*`` matches ``flashinfer-python``).

Usage:
    python3 audit-deps.py [--watch pkg ...] wheel.whl [wheel.whl ...]

Exit status: 0 = clean, 1 = a watched package is declared.
"""

import argparse
import sys
import zipfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--watch",
        action="append",
        default=[
            "torch", "torchaudio", "torchvision", "torchcodec",
            "torch-c-dlpack-ext", "triton", "sglang-kernel",
            "cuda-python", "flashinfer*", "flash-attn-4",
            "sgl-deep-gemm", "sgl-deep-ep", "tilelang", "tokenspeed-mla",
            "quack-kernels", "nvidia-*", "numba", "kernels",
            "torch-memory-saver", "torchao", "nvidia-modelopt", "flag-gems",
        ],
        metavar="PKG",
        help="package names to fail on if declared (repeatable; "
             "trailing '*' = prefix match)",
    )
    parser.add_argument("wheels", nargs="+", metavar="wheel.whl")
    args = parser.parse_args()

    watch = {w.lower().replace("_", "-") for w in args.watch}
    prefixes = sorted(p[:-1] for p in watch if p.endswith("*"))
    exact = watch - {p + "*" for p in prefixes}
    failed = False

    for wheel in args.wheels:
        requires: list[str] = []
        with zipfile.ZipFile(wheel) as zf:
            for name in zf.namelist():
                if name.endswith(".dist-info/METADATA"):
                    requires = [
                        ln.split(";", 1)[0].split("[", 1)[0].strip()
                        for ln in zf.read(name).decode().splitlines()
                        if ln.startswith("Requires-Dist:")
                    ]
                    break

        declared = {r.lower().replace("_", "-") for r in requires}
        hits = sorted(
            (exact & declared)
            | {d for d in declared if any(d.startswith(p) for p in prefixes)}
        )
        print(f"{wheel}: requires {len(requires)} packages "
              f"(watchlist hits: {', '.join(hits) if hits else 'none'})")
        if hits:
            failed = True
            for pkg in hits:
                print(f"  FAIL: declares critical package {pkg} — "
                      f"an app-image single-step install would drift the "
                      f"runtime matrix. Drop it from the wheel's "
                      f"dependencies; the image provides it.",
                      file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
