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
    python runtime/build.py <backend-key> --flaggems-dir <path> [options]

Examples:
    python runtime/build.py nvidia-cuda12.8 --flaggems-dir ../FlagGems --dry-run
    python runtime/build.py ascend-cann9.0.0 --flaggems-dir ../FlagGems --tag latest
    python runtime/build.py metax --flaggems-dir ../FlagGems --push
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def get_flaggems_version(flaggems_dir: Path) -> str:
    """Get FlagGems version from git describe.

    TODO: Remove once we switch to wheel-based install — the wheel
    will carry the correct version and setuptools-scm won't be needed.
    """
    try:
        result = subprocess.run(
            ["git", "describe", "--tags"],
            cwd=flaggems_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            # Convert git describe output to setuptools-scm format:
            #   "v5.4.0.dev0-528-g0283c119d" → "5.4.0.dev528+g0283c119d"
            desc = result.stdout.strip().lstrip("v")
            parts = desc.split("-")
            if len(parts) >= 3:
                tag = parts[0]  # "5.4.0.dev0"
                distance = parts[-2]  # "528"
                commit = parts[-1]  # "g0283c119d"
                # Replace ".dev0" with ".dev{distance}"
                if ".dev" in tag:
                    tag = tag[: tag.index(".dev")]
                return f"{tag}.dev{distance}+{commit}"
            else:
                # Exact tag, no commits after
                return parts[0]
    except FileNotFoundError:
        pass
    return "0.0.0"


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

    Same scheme base/build.py stamps onto the base image tag.
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

    {registry}/{prefix}-{vendor}-{backend}:{git-version}

    The tag comes from build-infra's `git describe --tags` — the SAME version
    base/build.py stamps onto the pushed base image. (PR #99 removed the
    version/revision LABELs, so this no longer reads them.) Falls back to :latest
    with a warning when no tag is reachable (shallow checkout — use fetch-depth: 0).
    """
    prefix = configs.get("base_image_prefix", "flagos-base")
    version = git_describe(repo_root)
    if not version:
        print(
            "warning: no git tag reachable — base image tag defaults to :latest",
            file=sys.stderr,
        )
        version = "latest"
    name = f"{prefix}-{vendor}-{backend}:{version}"
    registry = base_registry(repo_root)
    return f"{registry}/{name}" if registry else name


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

    # Install spec: fold the per-vendor C++ operators extra into the FlagGems
    # extras when the backend supports C++ (cmake_backend set). The C++ extra
    # token is the cmake backend lowercased (CUDA -> cuda -> cpp-cuda), NOT the
    # vendor name. The extras resolve flag_gems + flag-gems-cpp-<backend> wheels.
    extras = backend_info.get("extras", "")
    cpp_backend = str(backend_info.get("cmake_backend", "")).lower()
    if cpp_backend:
        extras_spec = f"{extras},cpp-{cpp_backend}" if extras else f"cpp-{cpp_backend}"
    else:
        extras_spec = extras

    # Compiler: prefer flagtree (the blessed default); fall back to triton only
    # when the backend has no flagtree entry (flagtree unsupported for it).
    # A single compiler is baked; the flagtree<->triton switch is a later task.
    flagtree = backend_info.get("flagtree", "")
    triton = backend_info.get("triton", "")
    if flagtree:
        compiler, compiler_pkg = "flagtree", flagtree
    elif triton:
        compiler, compiler_pkg = "triton", triton
    else:
        compiler, compiler_pkg = "", ""

    args = {
        "BASE_IMAGE": base_image_override
        or resolve_base_image(vendor, backend, configs, repo_root),
        "PYTHON_VERSION": backend_info.get("python", "3.12"),
        "FLAGOS_PYPI": pypi_base.format(vendor=vendor) if pypi_base else "",
        "DAILY_PYPI": pypi_daily,
        "EXTRA_PYPI": extra_pypi_override or mirror,
        "EXTRAS_GROUP": extras_spec,
        "COMPILER": compiler,
        "COMPILER_PKG": compiler_pkg,
        "INCLUDE_TESTS": include_tests_override or "false",
    }

    # Optional triton-specific post-install packages from configs.yaml.
    # Only relevant when the baked compiler is triton — skip under flagtree.
    triton_post = backend_info.get("triton_post_install", [])
    if compiler == "triton" and isinstance(triton_post, list) and triton_post:
        pkgs = " ".join(triton_post)
        flagos_pypi = args["FLAGOS_PYPI"]
        extra_pypi = args["EXTRA_PYPI"]
        cmd = (
            f"uv pip install --no-cache-dir"
            f" --default-index {flagos_pypi}"
            f" --index {extra_pypi}"
            f" {pkgs}"
        )
        args["TRITON_POST_INSTALL"] = cmd

    return args


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
        "--flaggems-dir",
        required=True,
        help="Path to FlagGems source tree — used ONLY to derive the wheel "
        "version (git describe); no longer the docker build context.",
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
    flaggems_dir = Path(args.flaggems_dir).resolve()

    configs_path = repo_root / "configs.yaml"
    containerfile = script_dir / "Containerfile"

    if not configs_path.exists():
        sys.exit(f"Error: {configs_path} not found")
    if not containerfile.exists():
        sys.exit(f"Error: {containerfile} not found")

    configs = load_yaml(configs_path)

    # TODO: Remove FLAGGEMS_VERSION once we switch to wheel-based install.
    flaggems_version = get_flaggems_version(flaggems_dir)

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
    build_args["FLAGGEMS_VERSION"] = flaggems_version

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
    cmd.extend(["-f", str(containerfile), "-t", tag, str(script_dir)])

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

    if args.push:
        print(f"Pushing {tag}...")
        result = subprocess.run(["docker", "push", tag])
        if result.returncode != 0:
            sys.exit(f"docker push failed with exit code {result.returncode}")

    print(f"Done: {tag}")


if __name__ == "__main__":
    main()
