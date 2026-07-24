---
title: Upgrading uv
weight: 20
---

<!--
 Copyright 2026 FlagOS Contributors

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
-->

`runtime/Containerfile` pins a specific uv version and downloads it from the
internal filestore.  uv is used to create the virtual environment and install
all Python packages.

## Why uv and CPython-standalone move together

When a Containerfile has `uv venv --python 3.11` and the base image lacks
Python 3.11, uv downloads a standalone CPython build from
[python-build-standalone][pbs].  The release tag uv uses is **hardcoded in the
uv binary** — each uv version binds to exactly one tag.  Bump uv → the tag
changes → the cached tarballs on the filestore must be updated.

[pbs]: https://github.com/astral-sh/python-build-standalone/releases

| uv version | python-build-standalone release tag |
|---|---|
| 0.11.30   | `20260718`                          |

## Finding the new release tag

After downloading the new uv binary to any runner:

```bash
# Quick — grep the binary
strings uv | grep -oE 'cpython-[0-9.]+%2B[0-9]+-[a-z0-9_-]+-install_only[^"]*\\.tar\\.gz' | sort -u

# Accurate — force a reinstall with verbose
uv python install --reinstall --no-cache -v cpython-3.11.15-linux-$(uname -m)-gnu 2>&1 | grep Downloading
# → https://releases.astral.sh/github/python-build-standalone/releases/download/<TAG>/...
```

## Files to mirror

For each tag, download the `*_stripped` variants (smaller) for the Python
minor versions and architectures in use.  Three versions (3.10, 3.11, 3.12)
× two architectures (x86_64, aarch64) = **6 files** per tag.

Upload to:

```
flagos-filestore/uv-python/<TAG>/<filename>
```

## Containerfile changes

- Bump the uv version in the `curl` line inside `runtime/Containerfile`.
- The `UV_PYTHON_INSTALL_MIRROR` variable (below) does not change — uv
  appends the tag path internally.

## Mirror (configured 2026-07-24)

`UV_PYTHON_INSTALL_MIRROR` lets uv download CPython from the filestore
instead of GitHub.  Once the 6 files are uploaded, add this env line before
`uv venv` in the Containerfile:

```dockerfile
ENV UV_PYTHON_INSTALL_MIRROR=https://resource.flagos.net/repository/flagos-filestore/uv-python
```

Until the mirror is populated, uv falls back to GitHub, which is slow
from CN runners.
