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
"""Add files to a built wheel in place, leaving its name alone.

    inject-bitcode.py WHEEL --add ARCPATH=SRCPATH [--add ...]

The wheel name is the pin (`build-flagcx-wheel.sh --print-pin`), so the archive
is rewritten under the name it already has. A re-named wheel would install under
the same version and the pin would then name whichever file the index happened
to keep.

Rewriting rather than appending because `RECORD` is inside the archive: an
appended file that no `RECORD` row covers is one `pip uninstall` leaves behind
and `pip install --require-hashes`-style checks reject. Every row is written
back verbatim except the ones being added, and the added ones are hashed the way
installers expect (`sha256=` + urlsafe-b64, padding stripped — PEP 376's spelling
of both `RECORD`'s hash column and a `--hash` argument).

Why this is a post-build step at all: FlagCX's `setup.py` declares
`package_data={"flagcx": ["lib/*.so"]}`, so a `.bc` dropped into the tree before
the build is not collected, and widening that glob is a FlagCX change the wheel
line's first step is meant not to need.
"""
import argparse
import base64
import csv
import hashlib
import io
import os
import stat
import sys
import tempfile
import zipfile


def record_hash(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
    return "sha256=" + digest.rstrip(b"=").decode("ascii")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("wheel", help="the built wheel, rewritten in place")
    ap.add_argument(
        "--add",
        action="append",
        default=[],
        metavar="ARCPATH=SRCPATH",
        help="file to add; repeatable",
    )
    args = ap.parse_args()

    additions = []
    for spec in args.add:
        arcname, sep, src = spec.partition("=")
        if not sep or not arcname or not src:
            sys.exit(f"--add wants ARCPATH=SRCPATH, got {spec!r}")
        with open(src, "rb") as fh:
            additions.append((arcname, fh.read()))

    with zipfile.ZipFile(args.wheel) as zin:
        names = zin.namelist()
        records = [n for n in names if n.endswith(".dist-info/RECORD")]
        if len(records) != 1:
            sys.exit(f"{args.wheel}: {len(records)} RECORD members, expected 1")
        record_name = records[0]
        # A second copy of a path already in the archive would make the wheel
        # carry two versions of it, and installers take whichever comes first.
        for arcname, _ in additions:
            if arcname in names:
                sys.exit(f"{args.wheel}: already carries {arcname}")
        record = zin.read(record_name)
        items = [(i.filename, zin.read(i.filename)) for i in zin.infolist()]

    rows = list(csv.reader(io.StringIO(record.decode("utf-8"))))
    for arcname, data in additions:
        rows.append([arcname, record_hash(data), str(len(data))])
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    new_record = out.getvalue().encode("utf-8")

    # Same directory, so the replace is a rename and the wheel is never
    # half-written where a reader could pick it up.
    mode = stat.S_IMODE(os.stat(args.wheel).st_mode)
    fd, tmpname = tempfile.mkstemp(
        dir=os.path.dirname(os.path.abspath(args.wheel)), suffix=".tmp"
    )
    os.close(fd)
    try:
        with zipfile.ZipFile(tmpname, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, data in items:
                zout.writestr(name, new_record if name == record_name else data)
            for arcname, data in additions:
                zout.writestr(arcname, data)
        # mkstemp creates 0600 and a wheel is a published artifact: a wheel only
        # its builder can read is a wheel nobody can install from a shared tree.
        os.chmod(tmpname, mode)
        os.replace(tmpname, args.wheel)
    finally:
        if os.path.exists(tmpname):
            os.unlink(tmpname)

    for arcname, data in additions:
        print(f">>> +{arcname} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
