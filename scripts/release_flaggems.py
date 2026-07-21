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

"""Release FlagGems wheels — RELEASE.md steps 5a + 5b.

Usage::

    python3 scripts/release_flaggems.py build-python --ref v5.3.1 [--outdir DIR]
    python3 scripts/release_flaggems.py upload-python WHEEL [--dry-run]
    python3 scripts/release_flaggems.py build-cpp BACKEND --ref v5.3.1 --runtime-image IMG [--outdir DIR]
    python3 scripts/release_flaggems.py upload-cpp BACKEND WHEEL [--dry-run]

Cpp wheel build runs inside the runtime:v1 container (built in step 4
with --no-flaggems) — its venv already has torch + deps + compilers,
so ``pip wheel ./cpp`` just works.

The NEXUS_TOKEN env var is required for upload commands (``user:token``).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    """Push the same py3-none-any wheel to every vendor PyPI in parallel."""
    cfg = _load_configs()
    urls = _pypi_urls(cfg)
    wheel = Path(args.wheel)

    if args.dry_run:
        for vendor, url in sorted(urls.items()):
            print(f"[dry-run] would upload {wheel.name} to {vendor}: {url}")
        return

    token = os.environ.get("NEXUS_TOKEN", "")
    if not token:
        sys.exit("ERROR: NEXUS_TOKEN env var is empty or unset")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_twine_upload, wheel, url): vendor
            for vendor, url in urls.items()
        }
        ok, fail = 0, 0
        for f in as_completed(futures):
            vendor = futures[f]
            try:
                f.result()
                print(f"  OK  {vendor}")
                ok += 1
            except Exception as exc:
                print(f"  FAIL {vendor}: {exc}")
                fail += 1

    print(f"Uploaded to {ok}/{len(urls)} vendor PyPIs (errors: {fail}).")
    if fail:
        sys.exit(1)


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


# ── build-cpp ─────────────────────────────────────────────────────────────────

VENDOR_MAP: dict[str, str] = {
    "CUDA": "cuda",
    "NPU": "npu",
    "GCU": "gcu",
    "IX": "ix",
    "MUSA": "musa",
}


def cmd_build_cpp(args: argparse.Namespace) -> str:
    """Build a cpp operator wheel inside runtime:v1.  Returns wheel path."""
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
        sys.exit(f"Error: unknown cmake_backend '{cmake_backend}'")

    # Build deps from configs.yaml (pinned so the build is reproducible).
    build_deps = " ".join(cfg.get("flaggems_cpp_build_deps", []))

    outdir = args.outdir or str(ROOT / "wheels-cpp")
    os.makedirs(outdir, exist_ok=True)
    host_out = os.path.abspath(outdir)

    script_path = str(ROOT / "scripts" / "build_cpp_wheel.sh")
    with open(script_path) as fh:
        script = fh.read()

    print(f"Building cpp wheel for {args.backend} ({v}) inside {args.runtime_image} ...")
    # Use bash -c so we don't need to bind-mount the script file — some runner
    # Docker configurations reject file mounts from checkout directories.
    subprocess.run(
        [
            "docker", "run", "--rm",
            "--entrypoint", "bash",
            "-v", f"{host_out}:/tmp/wheel-out",
            "-e", f'FLAGGEMS_REF={args.ref}',
            "-e", f'FLAGGEMS_CPP_VENDOR={v}',
            "-e", f'FLAGGEMS_CMAKE_ARGS=-DFLAGGEMS_BUILD_C_EXTENSIONS=ON -DFLAGGEMS_BACKEND={cmake_backend} -DCMAKE_BUILD_TYPE=Release',
            "-e", f'SETUPTOOLS_SCM_PRETEND_VERSION={args.ref.lstrip("v")}',
            "-e", f'FLAGGEMS_BUILD_DEPS={build_deps}',
            args.runtime_image,
            "-c", script,
        ],
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
    bc = subs.add_parser("build-cpp", help="Build cpp wheel inside runtime:v1")
    bc.add_argument("backend", help="Backend name, e.g. nvidia-cuda12.8")
    bc.add_argument("--ref", required=True, help="FlagGems git tag/ref")
    bc.add_argument("--runtime-image", required=True,
                    help="runtime:v1 image ref (built with --no-flaggems in step 4)")
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
