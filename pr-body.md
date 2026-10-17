metax now carries everything `flagtree-wheel-daily.yml`'s gate asserts: it takes
`FLAGTREE_WHEEL_NAME` and writes the `setup.cfg` `Source-Commit` carrier, and its
builder stage is published (`flagos-dev/flagtree-builder-metax:2.3.0`). The row
only needs enabling.

Verified on the daily's own shape before flipping it, two clean h20 builds:
`0.7.0+metax3.6` (206,981,211 B) and `main` at `0.7.1.dev20261017` (207,012,151 B),
both passing max GLIBC 2.34, pybind11 internals v11, and the `Source-Commit` line
in METADATA.

The row declares `ref: main` explicitly, like nvidia's: the Containerfile's default
is the vendor release a local build reproduces, which is not the line the daily
tracks.

README: the daily section is no longer about one backend, and the consumer caveat
now names all three distributions.

Opened by Claude Code on the maintainer's behalf.
