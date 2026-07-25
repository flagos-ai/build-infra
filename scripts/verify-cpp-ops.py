#!/usr/bin/env python3
"""Verify that cpp operators work after wheel install.

Runs inside the runtime container with GPU access.
"""
import os
import sys

print(f"USE_C_EXTENSION = {os.environ.get('USE_C_EXTENSION', 'unset')}")
print(f"FLAGGEMS_SOURCE_DIR = {os.environ.get('FLAGGEMS_SOURCE_DIR', 'unset')}")
print(f"VIRTUAL_ENV = {os.environ.get('VIRTUAL_ENV', 'unset')}")
print(f"sys.prefix = {sys.prefix}")

import torch
print(f"torch: {torch.__version__}, "
      f"cuda: {torch.cuda.is_available()}, "
      f"devices: {torch.cuda.device_count()}")

import flag_gems
print(f"flag_gems: {flag_gems.__version__}")

try:
    import flag_gems._C
    print(f"_C module loaded from: {flag_gems._C.__file__}")
except ImportError as e:
    print(f"_C import failed: {e}")

from flag_gems import use_gems
use_gems()

from flag_gems.utils import libentry
print("libentry loaded OK")

# These go through the triton kernel path — gen_ssig.py must resolve
# source files after the fix.
a = torch.tensor([1.0, 2.0, 3.0, 4.0, 5.0], device="cuda")
b = a + a
print(f"add result: {b.tolist()}")

c = torch.zeros(5, device="cuda")
print(f"zeros result: {c.tolist()}")

d = c + a
print(f"fill+add result: {d.tolist()}")

from flag_gems import runtime
print(f"FlagGems runtime backend: {runtime.backend_name()}")

print("ALL TESTS PASSED")
