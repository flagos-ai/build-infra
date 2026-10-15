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

"""Bundle verify smoke probe (level 1): import the stack and prove the active
compiler JITs and runs a kernel on the device.

Runs inside the `--network none` container after install.sh, with the
profile.d env sourced (PYTHONPATH carries the active compiler side dir,
LD_LIBRARY_PATH the vendor runtime). This is the deep half of bundle verify:
the import-only smoke (SMOKE_IMPORTS in install.sh) already ran at install
time, but it never touches the device or the compiler. Here we fail the step
on:

  - torch / vllm / flag_gems import failure
  - no device visible (preinstalled SDK/driver missing or mismatched)
  - flag_gems.use_gems() + a device op failing
  - torch.compile failing to run a kernel through the active compiler

`torch.compile` deliberately uses the default inductor backend: inductor
codegens triton by name, so whichever `triton` the active PYTHONPATH resolves
— flagtree's side dir or the vendor triton — is the compiler that actually
JITs and executes. That is the production path vLLM takes, so a pass here
means more than a `compiler <name>` toggle printing "(active)".
"""

import os
import sys

failures: list[str] = []


def check(name: str, fn) -> None:
    try:
        detail = fn()
        print(f"OK   {name}" + (f" — {detail}" if detail else ""))
    except Exception as e:  # noqa: BLE001 — report every failure, keep going
        failures.append(name)
        print(f"FAIL {name}: {e!r}")


def _version(mod: str):
    m = __import__(mod)
    return getattr(m, "__version__", "?")


# ── Imports ────────────────────────────────────────────────────────────────
check("import torch", lambda: _version("torch"))
check("import vllm", lambda: _version("vllm"))
check("import flag_gems", lambda: _version("flag_gems"))

# flagcx is a runtime-layer dep only where the backend's index carries one
# (nvidia); warn, never fail, so a backend without it still verifies.
try:
    import flagcx
    print(f"OK   import flagcx — {getattr(flagcx, '__version__', '?')}")
except Exception as e:  # noqa: BLE001
    print(f"note import flagcx skipped ({e!r})")

import torch


def _device():
    # Vendor torch trees expose the device as torch.cuda / torch.npu /
    # torch.musa / torch.mlu / ...; pick whichever the installed torch has
    # and can report on, rather than hardcoding the vendor.
    for name in ("cuda", "npu", "musa", "mlu", "xpu", "maca", "gcu", "hpu"):
        mod = getattr(torch, name, None)
        if mod is not None and callable(getattr(mod, "is_available", None)):
            return name, mod
    return None, None


dev_name, dev = _device()


def _synchronize():
    # torch.<dev>.synchronize() so a kernel that was merely enqueued still
    # counts as executed before we declare success.
    (torch.cuda if dev_name == "cuda" else dev).synchronize()


# ── Device + FlagGems ──────────────────────────────────────────────────────
if dev is None or not dev.is_available():
    failures.append("device available")
    print("FAIL device available: no vendor device visible — the preinstalled "
          "SDK/driver is missing or mismatched for this backend")
else:
    def _device_op():
        # use_gems() redirects torch ops to FlagGems kernels; running one on
        # the device proves both the device runtime and the flag_gems triton
        # path execute, not just import.
        import flag_gems
        flag_gems.use_gems()
        a = torch.randn(64, 64, device=dev_name)
        b = a * 2 + 1
        _synchronize()
        return f"{dev_name}:{a.device.index}, result shape {tuple(b.shape)}"

    check("flag_gems.use_gems() + device op", _device_op)


# ── Compiler JIT + execution ───────────────────────────────────────────────
def _compile_probe():
    # inductor spawns a subprocess pool per-process by default; single-thread
    # the compile so the probe exercises the compiler deterministically and
    # stays clear of the fork-under-compile crashes the backends document.
    os.environ.setdefault("TORCHINDUCTOR_COMPILE_THREADS", "1")
    a = torch.randn(64, 64, device=dev_name)
    fn = torch.compile(lambda x: torch.nn.functional.gelu(x * 1.5))
    out = fn(a)
    _synchronize()
    return f"kernel ran, out shape {tuple(out.shape)}"


check("torch.compile (active compiler) JIT + execute", _compile_probe)

# ── Verdict ────────────────────────────────────────────────────────────────
if failures:
    print(f"\n{len(failures)} smoke check(s) failed: " + ", ".join(failures))
    sys.exit(1)
print("\nbundle smoke probe passed")
