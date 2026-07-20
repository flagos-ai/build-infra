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

"""Release FlagGems wheels — RELEASE.md steps 5a + 5b + 5c.

Usage::

    python3 scripts/release_flaggems.py build-python --ref v5.3.1 [--outdir DIR]
    python3 scripts/release_flaggems.py upload-python WHEEL [--dry-run]
    python3 scripts/release_flaggems.py build-cpp BACKEND --ref v5.3.1 [--outdir DIR]
    python3 scripts/release_flaggems.py upload-cpp BACKEND WHEEL [--dry-run]
    python3 scripts/release_flaggems.py update-config VERSION

The NEXUS_TOKEN env var is required for upload commands (``user:token``).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FLAGGEMS_REPO = "https://github.com/flagos-ai/FlagGems.git"

# ── helpers ──────────────────────────────────────────────────────────────────


def _load_configs() -> dict:
    with open(ROOT / "configs.yaml") as f:
        return yaml.safe_load(f) or {}


def _pypi_urls(cfg: dict) -> dict[str, str]:
    """Return {vendor: pypi_url} for every vendor in configs.yaml."""
    template = cfg.get("pypi_base", "")
    urls: dict[str, str] = {}
    for vendor in (cfg.get("vendors") or {}):
        urls[vendor] = template.replace("{vendor}", vendor)
    return urls


def _cmake_backends(cfg: dict) -> list[str]:
    """Return backend names that have a cmake_backend."""
    backends: list[str] = []
    vendors = cfg.get("vendors") or {}
    for vendor, specs in vendors.items():
        for bk_name, spec in (specs or {}).items():
            if spec.get("cmake_backend"):
                backends.append(f"{vendor}-{bk_name}")
    return sorted(backends)


def _venv() -> str:
    """Return a version string from the FlagGems ref (strip leading 'v').

    "v5.3.1" -> "5.3.1".  The wheel filename already carries the version
    via setuptools_scm; this is for display and for the configs.yaml update.
    """
    return sys.argv[sys.argv.index("--ref") + 1].lstrip("v")


# ── build-python ─────────────────────────────────────────────────────────────


def cmd_build_python(args: argparse.Namespace) -> str:
    """Build the pure-Python flag_gems wheel.  Returns the wheel path."""
    outdir = args.outdir or str(ROOT / "wheels")
    os.makedirs(outdir, exist_ok=True)

    env = os.environ.copy()
    env["FLAGGEMS_REF"] = args.ref
    env["OUTDIR"] = outdir
    subprocess.run(
        ["bash", str(ROOT / "flaggems-builder" / "build.sh")],
        env=env, check=True,
    )
    wheels = sorted(Path(outdir).glob("flag_gems-*.whl"))
    if not wheels:
        sys.exit("ERROR: no flag_gems wheel produced")
    print(f"Wheel: {wheels[-1]}")
    return str(wheels[-1])


# ── upload-python ─────────────────────────────────────────────────────────────


def cmd_upload_python(args: argparse.Namespace) -> None:
    """Push the same py3-none-any wheel to every vendor PyPI."""
    cfg = _load_configs()
    urls = _pypi_urls(cfg)
    wheel = Path(args.wheel)

    for vendor, url in sorted(urls.items()):
        print(f">>> uploading to {vendor}: {url}")
        if args.dry_run:
            print(f"    [dry-run] would upload {wheel.name} to {url}")
            continue
        _twine_upload(wheel, url)

    print(f"Uploaded to {len(urls)} vendor PyPIs.")


# ── build-cpp ─────────────────────────────────────────────────────────────────


VENDOR_MAP: dict[str, str] = {
    "CUDA": "cuda",
    "NPU": "npu",
    "GCU": "gcu",
    "IX": "ix",
    "MUSA": "musa",
}


def cmd_build_cpp(args: argparse.Namespace) -> str:
    """Build a cpp operator wheel inside the base image.  Returns wheel path."""
    cfg = _load_configs()
    vendor, bk = args.backend.split("-", 1)
    specs = (cfg.get("vendors") or {}).get(vendor, {}).get(bk)
    if not specs:
        sys.exit(f"Error: backend '{args.backend}' not in configs.yaml")

    cmake_backend = specs.get("cmake_backend")
    if not cmake_backend:
        sys.exit(f"Error: backend '{args.backend}' has no cmake_backend")

    v = VENDOR_MAP.get(cmake_backend)
    if not v:
        sys.exit(f"Error: unknown cmake_backend '{cmake_backend}' (no VENDOR_MAP entry)")

    # Resolve image ref.
    images = yaml.safe_load(
        (ROOT / "docs" / "data" / "images.yaml").read_text()
    )
    entry = next(
        (b for b in images.get("backends", []) if b["name"] == args.backend), None
    )
    if not entry:
        sys.exit(f"Error: '{args.backend}' not in images.yaml (run gen_data.py first)")
    image = entry["base"]["image"]

    outdir = args.outdir or str(ROOT / "wheels-cpp")
    os.makedirs(outdir, exist_ok=True)

    # Run everything inside docker to use the vendor's toolchain.
    script = f"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq git python3-pip >/dev/null 2>&1

git clone --quiet "{FLAGGEMS_REPO}" /tmp/FlagGems
cd /tmp/FlagGems
git fetch --quiet --tags --force origin || true
git checkout --quiet "{args.ref}"
echo "FlagGems @ $(git describe --tags 2>/dev/null || echo '{args.ref}')"

tools/set_cpp_vendor.sh {v}

# pip wheel outside the source tree so setuptools_scm doesn't see a dirty repo.
mkdir -p /tmp/wheel-out
export CMAKE_ARGS="-DFLAGGEMS_BUILD_C_EXTENSIONS=ON -DFLAGGEMS_BACKEND={cmake_backend} -DCMAKE_BUILD_TYPE=Release"
python3 -m pip wheel ./cpp --no-deps --no-build-isolation -w /tmp/wheel-out

# --- .so checks: catch rpath / DT_NEEDED issues early (no torch needed) ---
pip install --no-index --find-links=/tmp/wheel-out flag-gems-cpp-{v} 2>/dev/null || \
  pip install /tmp/wheel-out/*.whl
SO=$(python3 -c "from flag_gems import c_operators; print(c_operators.__file__)")
echo "  .so path: $SO"
echo ">>> DT_NEEDED:"
readelf -d "$SO" | grep 'NEEDED' | sed 's/.*\[//;s/\]//' | sort
echo ">>> rpath / runpath:"
readelf -d "$SO" | grep -iE 'RPATH|RUNPATH' || echo "  (none — relies on LD_LIBRARY_PATH)"
for lib in $(readelf -d "$SO" | grep 'NEEDED' | sed 's/.*\[//;s/\]//'); do
  if ! ldconfig -p | grep -q "$lib"; then
    echo "  ! WARNING: $lib not in ldconfig cache — must be in LD_LIBRARY_PATH"
  fi
done
echo "OK  cpp extension .so built for {v}"

# Copy out.
cp /tmp/wheel-out/*.whl /host-out/
"""
    host_out = os.path.abspath(outdir)
    print(f"Building cpp wheel for {args.backend} ({v}) inside {image} ...")
    subprocess.run(
        ["docker", "run", "--rm", "-v", f"{host_out}:/host-out", image, "bash", "-c", script],
        check=True,
    )

    wheels = sorted(Path(outdir).glob("flag_gems_cpp_*.whl"))
    if not wheels:
        sys.exit("ERROR: no cpp wheel produced")
    print(f"Wheel: {wheels[-1]}")
    return str(wheels[-1])


# ── upload-cpp ───────────────────────────────────────────────────────────────


def cmd_upload_cpp(args: argparse.Namespace) -> None:
    """Push a cpp wheel to its vendor's PyPI."""
    cfg = _load_configs()
    vendor = args.backend.split("-", 1)[0]
    url = _pypi_urls(cfg).get(vendor)
    if not url:
        sys.exit(f"Error: vendor '{vendor}' has no PyPI URL")
    wheel = Path(args.wheel)
    print(f">>> uploading to {vendor}: {url}")
    if args.dry_run:
        print(f"    [dry-run] would upload {wheel.name} to {url}")
        return
    _twine_upload(wheel, url)
    print(f"Uploaded to {vendor}.")


def _twine_upload(wheel: Path, repo_url: str) -> None:
    """Upload a single wheel to a PyPI repo via twine.

    Credentials are passed via env vars so they never appear in logs.
    The ``repo_url`` is a pip index URL (ends with ``/simple``);
    twine needs the bare repository URL, so that suffix is stripped.
    """
    token = os.environ.get("NEXUS_TOKEN", "")
    if not token:
        sys.exit("ERROR: NEXUS_TOKEN env var is empty or unset")
    user, _, pw = token.partition(":")
    env = os.environ.copy()
    env["TWINE_USERNAME"] = user
    env["TWINE_PASSWORD"] = pw
    # twine wants the bare repo URL, not the pip index URL.
    upload_url = repo_url.rstrip("/").removesuffix("/simple")
    subprocess.run(
        [
            sys.executable, "-m", "twine", "upload",
            "--repository-url", f"{upload_url}/",
            "--non-interactive",
            str(wheel),
        ],
        check=True, env=env,
    )


# ── update-config ────────────────────────────────────────────────────────────


def cmd_update_config(args: argparse.Namespace) -> None:
    """Write flaggems: field in configs.yaml, commit, open PR."""
    version = args.version.lstrip("v")
    config_path = ROOT / "configs.yaml"

    with open(config_path) as f:
        content = f.read()

    import re

    new_content = re.sub(
        r"^flaggems:.*$", f'flaggems: "{version}"', content, count=1, flags=re.MULTILINE
    )
    if new_content == content:
        print(f"flaggems is already set to {version} — nothing to do")
        return

    with open(config_path, "w") as f:
        f.write(new_content)

    subprocess.run(["git", "add", str(config_path)], check=True, cwd=ROOT)
    branch = f"auto/flaggems-{version}"
    subprocess.run(
        ["git", "checkout", "-b", branch], check=True, cwd=ROOT,
    )
    subprocess.run(
        ["git", "commit", "-m", f"chore: bump flaggems to {version}"],
        check=True, cwd=ROOT,
    )
    subprocess.run(
        ["git", "push", "-f", "origin", branch], check=True, cwd=ROOT,
    )

    body = (
        f"Set FlagGems version to `{version}` in configs.yaml.\n\n"
        f"Part of the release workflow (RELEASE.md step 5c)."
    )
    subprocess.run(
        [
            "gh", "pr", "create",
            "--base", "main", "--head", branch,
            "--title", f"chore: bump flaggems to {version}",
            "--body", body,
        ],
        check=True, cwd=ROOT,
    )
    print(f"PR opened: flaggems → {version}")


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Release FlagGems wheels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # build-python
    bp = subs.add_parser("build-python", help="Build pure-Python wheel")
    bp.add_argument("--ref", required=True, help="FlagGems git tag/ref")
    bp.add_argument("--outdir", help="Output directory for the wheel")
    bp.set_defaults(func=lambda a: cmd_build_python(a))

    # upload-python
    up = subs.add_parser("upload-python", help="Upload wheel to all vendor PyPIs")
    up.add_argument("wheel", help="Path to flag_gems-*.whl")
    up.add_argument("--dry-run", action="store_true", help="Print without uploading")
    up.set_defaults(func=lambda a: cmd_upload_python(a))

    # build-cpp
    bc = subs.add_parser("build-cpp", help="Build cpp wheel inside base image")
    bc.add_argument("backend", help="Backend name, e.g. nvidia-cuda12.8")
    bc.add_argument("--ref", required=True, help="FlagGems git tag/ref")
    bc.add_argument("--outdir", help="Output directory for the cpp wheel")
    bc.set_defaults(func=lambda a: cmd_build_cpp(a))

    # upload-cpp
    uc = subs.add_parser("upload-cpp", help="Upload cpp wheel to vendor PyPI")
    uc.add_argument("backend", help="Backend name, e.g. nvidia-cuda12.8")
    uc.add_argument("wheel", help="Path to flag_gems_cpp_*.whl")
    uc.add_argument("--dry-run", action="store_true", help="Print without uploading")
    uc.set_defaults(func=lambda a: cmd_upload_cpp(a))

    # update-config
    ug = subs.add_parser("update-config", help="Set flaggems version + open PR")
    ug.add_argument("version", help="Version, e.g. 5.3.1 or v5.3.1")
    ug.set_defaults(func=lambda a: cmd_update_config(a))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
