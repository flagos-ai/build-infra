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

"""Build FlagGems runtime container images.

Reads configs.yaml (the single source of truth for vendor/backend
dependencies) to resolve build arguments, then invokes `docker build`
with the appropriate --build-arg values.

Usage:
    python scripts/build_runtime.py <backend-key> [options]

Examples:
    python scripts/build_runtime.py nvidia-cuda12.8 --dry-run
    python scripts/build_runtime.py ascend-cann9.0.0 --tag latest
    python scripts/build_runtime.py metax --push
    python scripts/build_runtime.py nvidia-cuda12.8 --flaggems 5.4.0.dev601+g03122362d   # override
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from version import image_version

import yaml


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_backend(backend_arg: str, configs: dict):
    """Resolve user input to (backend_info, vendor, backend).

    configs.yaml maps vendor → {backend: {spec}}.

    Accepts:
      - "nvidia-cuda12.8" (vendor-backend)
      - "metax" (vendor shorthand, if single backend)

    Returns (backend_info, vendor, backend) where:
      - backend_info is the backend spec dict from configs.yaml
      - vendor is the vendor name
      - backend is the configs.yaml backend name (for base/runtime image names)
    """
    vendors = configs.get("vendors", {})

    for vendor, backends in vendors.items():
        for backend, backend_info in backends.items():
            if backend_arg == f"{vendor}-{backend}":
                return backend_info, vendor, backend
            if backend_arg == vendor and len(backends) == 1:
                return backend_info, vendor, backend

    # Vendor name with multiple backends
    if backend_arg in vendors:
        backends = vendors[backend_arg]
        if len(backends) > 1:
            names = [f"{backend_arg}-{b}" for b in backends]
            sys.exit(
                f"Error: '{backend_arg}' has multiple backends: "
                f"{', '.join(names)}"
            )

    sys.exit(f"Error: '{backend_arg}' not found in configs.yaml vendors")


def git_describe(repo_root: Path) -> str | None:
    """build-infra release version via `git describe --tags` ("v" stripped).

    Same scheme build_base.py stamps onto the base image tag.
    """
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    desc = r.stdout.strip()
    if desc[:1] == "v" and desc[1:2].isdigit():
        desc = desc[1:]
    return desc or None


def base_registry(repo_root: Path) -> str | None:
    """Base-image registry prefix ({host}/{prefixes.base}) from build-config.yml."""
    cfg_path = repo_root / ".github" / "build-config.yml"
    if not cfg_path.exists():
        return None
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f) or {}
    reg = cfg.get("registry") or {}
    host = reg.get("host")
    prefix = (reg.get("prefixes") or {}).get("base")
    return f"{host}/{prefix}" if host and prefix else None


def runtime_registry(repo_root: Path) -> str | None:
    """Runtime-image registry prefix ({host}/{prefixes.runtime}) from build-config.yml."""
    cfg_path = repo_root / ".github" / "build-config.yml"
    if not cfg_path.exists():
        return None
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f) or {}
    reg = cfg.get("registry") or {}
    host = reg.get("host")
    prefix = (reg.get("prefixes") or {}).get("runtime")
    return f"{host}/{prefix}" if host and prefix else None


def resolve_base_image(
    vendor: str, backend: str, configs: dict, repo_root: Path
) -> str:
    """Full base image ref for the runtime FROM.

    {registry}/{prefix}-{vendor}-{backend}:{version}

    The version comes from the base image's Containerfile LABEL +
    per-backend git revision count (see version.image_version).
    Falls back to git describe when the Containerfile has no version LABEL.
    Falls back to :latest when no git tag is reachable (shallow checkout).
    """
    prefix = configs.get("base_image_prefix", "flagos-base")
    name = f"{vendor}-{backend}"
    version = image_version(repo_root, name)
    if version is None:
        version = git_describe(repo_root)
    if not version:
        print(
            "warning: no git tag reachable — base image tag defaults to :latest",
            file=sys.stderr,
        )
        version = "latest"
    img = f"{prefix}-{name}:{version}"
    registry = base_registry(repo_root)
    return f"{registry}/{img}" if registry else img


def resolve_build_args(
    backend_info: dict,
    vendor: str,
    backend: str,
    configs: dict,
    repo_root: Path,
    *,
    base_image_override: str | None = None,
    extra_pypi_override: str | None = None,
    include_tests_override: str | None = None,
) -> dict[str, str]:
    """Resolve all docker build-arg values for a given backend."""

    pypi_base = configs.get("pypi_base", "")
    pypi_daily = configs.get("pypi_daily", "")
    mirror = configs.get("mirror", "https://mirrors.aliyun.com/pypi/simple")

    # Dependencies: explicit vendor packages from configs.yaml deps: (torch,
    # torchvision, etc.). Passed directly — no extras, no resolver ambiguity.
    # Extras are unreliable across vendor indexes because uv resolves by package
    # name and can't distinguish torch==2.8.0+metax from torch==2.9.0+musa.
    deps = " ".join(backend_info.get("deps", []))

    # C++ extension extra — a single named wheel (flag-gems-cpp-cuda) with no
    # multi-index resolution ambiguity. Empty when the backend has no C++ support.
    cpp_backend = str(backend_info.get("cmake_backend", "")).lower()
    cpp_extra = f"cpp-{cpp_backend}" if cpp_backend else ""

    # Both compilers are installed (when configured). FlagTree is the default
    # (installed to /flagos); Triton is installed to /opt/triton (side dir,
    # switched via PYTHONPATH). When only Triton is configured, it goes to
    # /flagos as the sole compiler (backward compat).
    flagtree = backend_info.get("flagtree", "")
    triton = backend_info.get("triton", "")
    triton_post = backend_info.get("triton_post_install", [])
    triton_extra = " ".join(triton_post) if isinstance(triton_post, list) else ""

    args = {
        "BASE_IMAGE": base_image_override
        or resolve_base_image(vendor, backend, configs, repo_root),
        "PYTHON_VERSION": backend_info.get("python", "3.12"),
        "FLAGOS_PYPI": pypi_base.format(vendor=vendor) if pypi_base else "",
        "DAILY_PYPI": pypi_daily,
        "EXTRA_PYPI": extra_pypi_override or mirror,
        "DEPS": deps,
        "CPP_EXTRA": cpp_extra,
        "FLAGTREE_PKG": flagtree,
        "TRITON_PKG": triton,
        "TRITON_EXTRA_PKGS": triton_extra,
        "INCLUDE_TESTS": include_tests_override or "false",
    }

    return args


def _upload_cpp_wheel(vendor: str, wheel: Path, configs: dict, repo_root: Path) -> None:
    """Upload a cpp wheel to the vendor's PyPI via twine."""
    token = os.environ.get("NEXUS_TOKEN", "")
    if not token:
        print(f"  skip cpp upload for {vendor}: NEXUS_TOKEN not set", file=sys.stderr)
        return
    user, _, pw = token.partition(":")
    env = os.environ.copy()
    env["TWINE_USERNAME"] = user
    env["TWINE_PASSWORD"] = pw
    pypi_base = configs.get("pypi_base", "")
    upload_url = pypi_base.format(vendor=vendor).rstrip("/").removesuffix("/simple")
    print(f"  uploading {wheel.name} to {upload_url} ...")
    subprocess.run(
        [
            sys.executable, "-m", "twine", "upload",
            "--repository-url", f"{upload_url}/",
            "--non-interactive",
            str(wheel),
        ],
        check=True, env=env,
    )
    print(f"  cpp wheel uploaded to {vendor}")


def main():
    parser = argparse.ArgumentParser(
        description="Build FlagGems runtime container images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "backend",
        help="Backend key (e.g. nvidia-cuda12.8, ascend-cann9.0.0, metax)",
    )
    parser.add_argument(
        "--flaggems",
        default="",
        help="FlagGems wheel version override (default: from configs.yaml)",
    )
    parser.add_argument("--base-image", help="Override base image")
    parser.add_argument("--extra-pypi", help="Override extra PyPI mirror URL")
    parser.add_argument(
        "--include-tests",
        choices=["true", "false"],
        help="Override whether to include tests",
    )
    parser.add_argument(
        "--registry",
        help="Container registry prefix (e.g. harbor.baai.ac.cn/flagos21)",
    )
    parser.add_argument("--tag", "-t", help="Override image tag")
    parser.add_argument("--push", action="store_true", help="Push after building")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print command without executing"
    )

    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    runtime_dir = repo_root / "runtime"

    configs_path = repo_root / "configs.yaml"
    containerfile = runtime_dir / "Containerfile"

    if not configs_path.exists():
        sys.exit(f"Error: {configs_path} not found")
    if not containerfile.exists():
        sys.exit(f"Error: {containerfile} not found")

    configs = load_yaml(configs_path)

    backend_info, vendor, backend = resolve_backend(args.backend, configs)

    build_args = resolve_build_args(
        backend_info,
        vendor,
        backend,
        configs,
        repo_root,
        base_image_override=args.base_image,
        extra_pypi_override=args.extra_pypi,
        include_tests_override=args.include_tests,
    )
    build_args["FLAGGEMS_VERSION"] = args.flaggems or configs.get("flaggems", "")

    # cpp wheel build: derive FlagGems git ref from version ("5.3.1" → "v5.3.1")
    flaggems_ver = build_args["FLAGGEMS_VERSION"]
    flaggems_ref = f"v{flaggems_ver}" if flaggems_ver and not flaggems_ver.startswith("v") else flaggems_ver
    build_args["FLAGGEMS_REF"] = flaggems_ref if build_args.get("CPP_EXTRA") else ""

    image_name = f"flagos-runtime-{vendor}-{backend}"

    if args.tag:
        tag = args.tag
    elif args.registry:
        tag = f"{args.registry}/{image_name}:latest"
    else:
        registry = runtime_registry(repo_root)
        tag = f"{registry}/{image_name}:latest" if registry else f"{image_name}:latest"

    cmd = ["docker", "build"]
    for key, value in build_args.items():
        cmd.extend(["--build-arg", f"{key}={value}"])
    # Wheel-based install: the image installs FlagGems from PyPI, so the build
    # context no longer needs the FlagGems source tree (no COPY). Use runtime/
    # as a trivial context. --flaggems-dir is kept only to derive the version.
    cmd.extend(["-f", str(containerfile), "-t", tag, str(runtime_dir)])

    if args.dry_run:
        print("Would run:")
        print("  " + " \\\n    ".join(cmd))
        print()
        print("Build args:")
        for k, v in build_args.items():
            print(f"  {k}={v}")
        return

    print(f"Building {tag}...")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"docker build failed with exit code {result.returncode}")

    # ── cpp wheel: upload to vendor PyPI ──────────────────────────
    cpp_extra = build_args.get("CPP_EXTRA", "")
    if cpp_extra and args.push:
        cpp_dir = Path(f"wheels-cpp-{backend}")
        container_id = subprocess.run(
            ["docker", "create", tag], capture_output=True, text=True, check=True
        ).stdout.strip()
        try:
            cpp_dir.mkdir(exist_ok=True)
            subprocess.run(
                ["docker", "cp", f"{container_id}:/app/cpp-wheels/.", str(cpp_dir)],
                check=True,
            )
            for wheel in sorted(cpp_dir.glob("flag_gems_cpp_*.whl")):
                _upload_cpp_wheel(vendor, wheel, configs, repo_root)
        finally:
            subprocess.run(["docker", "rm", container_id], capture_output=True)

    if args.push:
        print(f"Pushing {tag}...")
        result = subprocess.run(["docker", "push", tag])
        if result.returncode != 0:
            sys.exit(f"docker push failed with exit code {result.returncode}")

    print(f"Done: {tag}")


if __name__ == "__main__":
    main()
