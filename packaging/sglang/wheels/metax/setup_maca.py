# Copyright 2025 SGLang Team. All Rights Reserved.
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
# ==============================================================================
#
# metax (MACA) variant of setup_musa.py. Differences vs upstream:
#   - distribution name `sgl_kernel`, version = sgl-kernel version + "+flagos"
#     (pyproject.toml is moved away during the build so its [project] name
#     `sglang-kernel` does not override this)
#   - custom build_ext shells out to mxcc/g++ directly (verified recipe) instead
#     of torch CUDAExtension: torch would inject `-gencode` nvcc flags that mxcc
#     rejects, and metax torch is a CUDA-alias build (no torch.musa).
#   - registration file is csrc/common_extension_maca.cc (kCUDA), not
#     common_extension_musa.cc (kMUSA).
#   - libraries include c10_cuda/torch_cuda (flashinfer csrc references
#     c10::cuda::CUDACachingAllocator::allocator, exported by libtorch_cuda).
#   - .cu TUs are force-include'd with cu-bridge cuda_runtime.h; the .cc
#     registration TU is NOT (its __noinline__ macro clashes with libstdc++).
#   - FLASHINFER_ENABLE_F16/BF16 + ENABLE_BF16 so Half/BFloat16 dispatch cases
#     (sglang sampling runs bf16 logits).

import os
import platform
import re
import subprocess
import sysconfig
from pathlib import Path

import torch
from setuptools import Extension, find_packages, setup
from setuptools.command.build_ext import build_ext as _build_ext
from torch.utils.cpp_extension import include_paths

root = Path(__file__).parent.resolve()
arch = platform.machine().lower()

# flashinfer source tree lives at build/_deps/flashinfer (copied in by the
# build wrapper; mirrors upstream third_party layout)
FLASHINFER_DIR = root / "build" / "_deps" / "flashinfer"


def _get_version():
    m = re.search(r'__version__\s*=\s*"([^"]+)"', (root / "python" / "sgl_kernel" / "version.py").read_text())
    return m.group(1)


operator_namespace = "sgl_kernel"

MACA_PATH = os.environ.get("MACA_PATH", "/opt/maca")
MXCC = os.path.join(MACA_PATH, "mxgpu_llvm", "bin", "mxcc")
CUBR = os.path.join(MACA_PATH, "tools", "cu-bridge", "include")

include_dirs = [
    str(root / "include"),
    str(root / "include" / "impl"),
    str(root / "csrc"),
    str(FLASHINFER_DIR / "include"),
    str(FLASHINFER_DIR / "csrc"),
    str(FLASHINFER_DIR / "3rdparty"),
    CUBR,
] + include_paths() + [
    os.path.join(MACA_PATH, "include"),
    os.path.join(MACA_PATH, "include", "common"),
    os.path.join(MACA_PATH, "include", "mcrand"),
    os.path.join(MACA_PATH, "include", "mcr"),
] + [sysconfig.get_paths()["include"]]

# relative to setup dir (setuptools rejects absolute sources)
sources = [
    "csrc/common_extension_maca.cc",
    "csrc/elementwise/activation.cu",
    "build/_deps/flashinfer/csrc/norm.cu",
    "build/_deps/flashinfer/csrc/renorm.cu",
    "build/_deps/flashinfer/csrc/sampling.cu",
]

common_flags = [
    "-offload-arch=xcore1000",
    "-std=c++17",
    "-O2",
    "-fPIC",
    "-DUSE_MACA",
    "-D__CUDACC__",
    f"-DOPERATOR_NAMESPACE={operator_namespace}",
]

cu_only_flags = [
    "-DFLASHINFER_ENABLE_F16",
    "-DFLASHINFER_ENABLE_BF16",
    "-DENABLE_BF16",
    "-include",
    f"{CUBR}/cuda_runtime.h",
]

libraries = ["c10", "c10_cuda", "torch", "torch_cuda", "torch_python"]
extra_link_args = [
    "-Wl,-rpath,$ORIGIN/../../torch/lib",
]


class _BuildExt(_build_ext):
    """Compile the 5 TUs with mxcc, link with g++ (metax MACA)."""

    def build_extension(self, ext):
        out_path = Path(self.get_ext_fullpath(ext.name))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.build_temp = os.path.abspath(self.build_temp)
        os.makedirs(self.build_temp, exist_ok=True)

        objs = []
        for src in ext.sources:
            src_path = root / src if not os.path.isabs(src) else Path(src)
            obj = os.path.join(self.build_temp, Path(src).name + ".o")
            cmd = [MXCC] + common_flags
            if src.endswith(".cu"):
                cmd += cu_only_flags
            cmd += ["-c", str(src_path), "-o", obj]
            for d in include_dirs:
                cmd += ["-I", d]
            self._run(cmd)
            objs.append(obj)

        torch_lib = os.path.join(os.path.dirname(os.path.abspath(torch.__file__)), "lib")
        link_cmd = ["g++", "-shared", "-o", str(out_path)] + objs
        for l in libraries:
            link_cmd += ["-l" + l]
        link_cmd += ["-L" + torch_lib] + extra_link_args
        self._run(link_cmd)

    @staticmethod
    def _run(cmd):
        print("  " + " ".join(cmd))
        subprocess.check_call(cmd)


setup(
    name="sgl_kernel",
    version=_get_version() + "+flagos",
    packages=find_packages(where="python"),
    package_dir={"": "python"},
    ext_modules=[
        Extension(name="sgl_kernel.common_ops", sources=sources),
    ],
    cmdclass={"build_ext": _BuildExt},
)
