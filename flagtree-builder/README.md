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

# flagtree-builder

Containerfiles that build **FlagTree wheels** on an old-glibc base so the
resulting `libtriton.so` loads on nodes with older glibc (e.g. the h100 CI
runner running Ubuntu 22.04 / glibc 2.35).

Files are named `{vendor}-{backend}`, one per target:

| File         | Target             | Base                        |
|--------------|--------------------|-----------------------------|
| `nvidia-cuda`| FlagTree for NVIDIA| Ubuntu 22.04 (glibc 2.35)   |

## Build

Run from inside this folder:

```sh
podman build -t flagtree-build:0.6.0 -f nvidia-cuda .

# behind a proxy:
podman build --build-arg http_proxy=$http_proxy --build-arg https_proxy=$https_proxy \
             -t flagtree-build:0.6.0 -f nvidia-cuda .
```

Useful build args (see the Containerfile for the full list):

- `FLAGTREE_REF` — git branch/tag to build (default `0.6.0`).
- `FLAGTREE_WHEEL_VERSION` — wheel version string (default `0.6.0`). A clean
  version (no `+git<sha>`) also needs `FLAGTREE_PYPI_KEY`; otherwise the wheel
  is versioned `<ver>.git<sha>`.
- `FLAGTREE_PYPI_KEY` — unlocks the clean version (md5-gated in FlagTree's
  `setup.py`).

The build runs in `Release` mode, which strips `libtriton.so` (~840 MB → ~150 MB)
and drops asserts. A smoke test installs the freshly built wheel and imports
`triton`, failing the build if the wheel is broken.

## Extract the wheel

The wheel is written to `/wheels` in the image:

```sh
id=$(podman create flagtree-build:0.6.0)
podman cp $id:/wheels ./wheels
podman rm $id
```
