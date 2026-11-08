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

"""Release the TransformerEngine-FL dispatch-layer wheel.

One pure-Python (py3-none-any) wheel, built once and uploaded to every
NON-NVIDIA vendor PyPI plus the daily index. See
packaging/transformer-engine/DESIGN.md for why NVIDIA is excluded and why the
wheel is SDK-independent.

Usage::

    python3 scripts/release_te_fl.py build-python  --ref v2.17.0+fl.0.3.0 [--outdir DIR]
    python3 scripts/release_te_fl.py build-python  --ref main --version 2.17.0+fl.0.3.0
    python3 scripts/release_te_fl.py upload-python WHEEL [--dry-run]

The NEXUS_TOKEN env var is required for upload commands (``user:token``).
"""

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Vendors this line never uploads to. NVIDIA uses the official TransformerEngine:
# TE-FL's native build is stock-TE kernels and its dispatch layer only adds the
# (slower, flagos-default) indirection there. See DESIGN.md "Why NVIDIA is not
# on this line".
NON_TE_FL_VENDORS = {"nvidia"}

# ── helpers ──────────────────────────────────────────────────────────────────


def _load_configs() -> dict:
    with open(ROOT / "configs.yaml") as f:
        return yaml.safe_load(f) or {}


def _pypi_urls(cfg: dict) -> dict[str, str]:
    """Return {vendor: pypi_url} for every non-NVIDIA vendor in configs.yaml."""
    template = cfg.get("pypi_base", "")
    urls: dict[str, str] = {}
    for vendor in cfg.get("vendors") or {}:
        if vendor in NON_TE_FL_VENDORS:
            continue
        urls[vendor] = template.replace("{vendor}", vendor)
    return urls


# ── build-python ─────────────────────────────────────────────────────────────


def cmd_build_python(args: argparse.Namespace) -> str:
    """Build the pure-Python transformer_engine (dispatch-layer) wheel."""
    outdir = args.outdir or str(ROOT / "wheels")
    os.makedirs(outdir, exist_ok=True)

    env = os.environ.copy()
    env["TE_FL_REF"] = args.ref
    env["OUTDIR"] = outdir
    if args.version:
        env["TE_FL_VERSION"] = args.version
    subprocess.run(
        ["bash", str(ROOT / "packaging" / "transformer-engine" / "build.sh")],
        env=env,
        check=True,
    )
    wheels = sorted(Path(outdir).glob("transformer_engine-*.whl"))
    if not wheels:
        sys.exit("ERROR: no transformer_engine wheel produced")
    print(f"Wheel: {wheels[-1]}")
    return str(wheels[-1])


# ── upload-python ─────────────────────────────────────────────────────────────


def cmd_upload_python(args: argparse.Namespace) -> None:
    """Push the same py3-none-any wheel to every non-NVIDIA vendor PyPI.

    The tagged release wheel also goes to the daily index (flagos-pypi-daily),
    for the same reason as the flaggems line: a daily build off a freshly-pushed
    tag would otherwise lack that exact release version until the next commit.
    """
    cfg = _load_configs()
    urls = _pypi_urls(cfg)
    daily = cfg.get("pypi_daily")
    if daily:
        urls["daily"] = daily
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
            sys.executable,
            "-m",
            "twine",
            "upload",
            "--repository-url",
            f"{upload_url}/",
            "--non-interactive",
            str(wheel),
        ],
        check=True,
        env=env,
    )


# ── cli ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subs = parser.add_subparsers(dest="cmd", required=True)

    bp = subs.add_parser("build-python", help="Build pure-Python dispatch wheel")
    bp.add_argument("--ref", required=True, help="TE-FL tag/ref to build")
    bp.add_argument(
        "--version",
        default="",
        help="Full wheel version (<upstream>+fl.<flver>); derived from an exact "
        "tag when omitted",
    )
    bp.add_argument("--outdir", default="", help="output dir (default ./wheels)")
    bp.set_defaults(func=cmd_build_python)

    up = subs.add_parser(
        "upload-python", help="Upload wheel to every non-NVIDIA vendor PyPI"
    )
    up.add_argument("wheel", help="path to the built wheel")
    up.add_argument("--dry-run", action="store_true", help="list lanes, no upload")
    up.set_defaults(func=cmd_upload_python)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
