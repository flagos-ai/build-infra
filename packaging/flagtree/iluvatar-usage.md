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

# FlagTree for Iluvatar (CoreX) — user guide

`iluvatar` is one Dockerfile with two stages, and it produces two things:

| You want | Build |
|---|---|
| the `flagtree` wheel | the `builder` stage |
| an image to run it in — CoreX 4.5.0 + the wheel | the default stage |

The wheel is a **drop-in for the vendor's**: same version string
(`0.7.0rc2+iluvatar3.6`), same `cp312` tag. It is rebuilt on Ubuntu 22.04, which
is the point — the vendor's own wheel is built on 24.04, so its `libtriton.so`
needs GLIBC 2.38 and a 22.04 host refuses to load it.

The commands below run in the directory holding `iluvatar`.

## Get the wheel without building

```sh
docker pull harbor.baai.ac.cn/flagos-dev/flagtree-builder-iluvatar-corex4.5.0:2.2.0
cid=$(docker create harbor.baai.ac.cn/flagos-dev/flagtree-builder-iluvatar-corex4.5.0:2.2.0)
docker cp "$cid:/wheels/." .
docker rm "$cid"
# flagtree-0.7.0rc2+iluvatar3.6-cp312-cp312-linux_x86_64.whl
```

## Build it

```sh
docker build --target builder -t flagtree-builder-iluvatar:local -f iluvatar .   # wheel only, ~3.7 GB
docker build                     -t flagtree-iluvatar:local        -f iluvatar .   # wheel + CoreX image, ~15 GB
```

`--target builder` is what keeps CoreX out. Either way the wheel lands in
`/wheels` in the image — `docker create` + `docker cp` as above.

Needs a network (Docker Hub, github, and the FlagOS filestore for the SDK and
prebuilt deps), ~60 GB of free disk while it compiles, and about 10 minutes. No
GPU is involved.

## Use the wheel

```sh
pip install --force-reinstall --no-deps flagtree-0.7.0rc2+iluvatar3.6-*.whl
```

It owns the `triton` package, so it replaces any `triton` already installed —
including the vendor's. Install the vendor's torch first
(`torch==2.10.0+corex.4.5.0.20260804`, from the `flagos-pypi-iluvatar` index).
Python 3.12 is required (`cp312`).

```sh
python -c "import triton; from triton.backends import backends; print(triton.__version__, list(backends.keys()))"
# 3.6.0 ['iluvatar']
```

## What the build already checked

The build refuses to produce an image unless the wheel passes all of: a clean
version string (no `+git<sha>`), the `cp312` tag, no `GLIBC_2.38` /
`GLIBCXX_3.4.31` / `GLIBCXX_3.4.32` / `__isoc23_` symbol in `libtriton.so`, the
plugin's symbol linked in, and pybind11 internals v12 (the vendor's). So if
`docker build` finished, these hold.

The wheel is built against glibc 2.34 / GLIBCXX 3.4.30, so it loads on 22.04 and
anything newer. It does not need a card to import or compile.
