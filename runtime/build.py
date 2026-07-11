#!/usr/bin/env python3
"""Build FlagGems runtime container images.

Reads configs.yaml and FlagGems's src/flag_gems/backends.yaml to resolve
build arguments, then invokes `docker build` with the appropriate
--build-arg values.

Usage:
    python runtime/build.py <backend-key> --flaggems-dir <path> [options]

Examples:
    python runtime/build.py nvidia-cuda12.8 --flaggems-dir ../FlagGems --dry-run
    python runtime/build.py ascend-cann9.0.0 --flaggems-dir ../FlagGems --tag latest
    python runtime/build.py metax --flaggems-dir ../FlagGems --push
"""

import argparse
import re
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
    """Resolve user input to (flaggems_key, vendor, backend).

    configs.yaml maps vendor → {backends: [...], env: {...}}.

    Accepts:
      - "nvidia-cuda12.8" (vendor-backend)
      - "metax" (vendor shorthand, if single backend)

    Returns (flaggems_key, vendor, backend) where:
      - flaggems_key is the key in FlagGems backends.yaml (dots stripped)
      - vendor is the vendor name
      - backend is the configs.yaml backend name (for base image name)
    """
    vendors = configs.get("vendors", {})

    for vendor, info in vendors.items():
        backends = info.get("backends", [])
        for backend in backends:
            if backend_arg == f"{vendor}-{backend}":
                flaggems_key = f"{vendor}-{backend.replace('.', '')}"
                return flaggems_key, vendor, backend
            if backend_arg == vendor and len(backends) == 1:
                return vendor, vendor, backend

    # Vendor name with multiple backends
    if backend_arg in vendors:
        backends = vendors[backend_arg].get("backends", [])
        if len(backends) > 1:
            names = [f"{backend_arg}-{b}" for b in backends]
            sys.exit(
                f"Error: '{backend_arg}' has multiple backends: "
                f"{', '.join(names)}"
            )

    sys.exit(f"Error: '{backend_arg}' not found in configs.yaml vendors")


def parse_labels(containerfile: Path) -> dict[str, str]:
    """Extract OCI LABEL values from a containerfile."""
    labels = {}
    with open(containerfile) as f:
        for line in f:
            m = re.match(
                r'LABEL\s+org\.opencontainers\.image\.(\w+)\s*=\s*"([^"]*)"', line
            )
            if m:
                labels[m.group(1)] = m.group(2)
    return labels


def resolve_base_image(
    vendor: str, backend: str, configs: dict, repo_root: Path
) -> str:
    """Derive base image name by reading version/revision from the base containerfile.

    Image name: {prefix}-{vendor}-{backend}:{version}-{revision}
    """
    prefix = configs.get("base_image_prefix", "flagos-base")
    base_file = repo_root / "base" / f"{vendor}-{backend}"

    if base_file.exists():
        labels = parse_labels(base_file)
        version = labels.get("version", "latest")
        revision = labels.get("revision", "0")
        tag = f"{version}-{revision}"
    else:
        tag = "latest"

    return f"{prefix}-{vendor}-{backend}:{tag}"


def resolve_build_args(
    flaggems_key: str,
    vendor: str,
    backend: str,
    configs: dict,
    backends_yaml: dict,
    repo_root: Path,
    *,
    base_image_override: str | None = None,
    extra_pypi_override: str | None = None,
    include_tests_override: str | None = None,
) -> dict[str, str]:
    """Resolve all docker build-arg values for a given backend."""

    backend_info = backends_yaml.get("backends", {}).get(flaggems_key)
    if backend_info is None:
        sys.exit(f"Error: '{flaggems_key}' not found in backends.yaml")

    pypi_base = backends_yaml.get("pypi_base", "")
    mirror = backends_yaml.get("mirror", "https://mirrors.aliyun.com/pypi/simple")

    args = {
        "BASE_IMAGE": base_image_override
        or resolve_base_image(vendor, backend, configs, repo_root),
        "PYTHON_VERSION": backend_info.get("python", "3.12"),
        "FLAGOS_PYPI": pypi_base.format(vendor=vendor) if pypi_base else "",
        "EXTRA_PYPI": extra_pypi_override or mirror,
        "EXTRAS_GROUP": flaggems_key,
        "INCLUDE_TESTS": include_tests_override or "true",
    }

    # Optional triton-specific post-install packages from backends.yaml
    # These are only needed when using triton (not flagtree).
    triton_post = backend_info.get("triton_post_install", [])
    if isinstance(triton_post, list) and triton_post:
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
        help="Path to FlagGems source tree (used as build context and for backends.yaml)",
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
    backends_path = flaggems_dir / "src" / "flag_gems" / "backends.yaml"
    containerfile = script_dir / "Containerfile"

    if not configs_path.exists():
        sys.exit(f"Error: {configs_path} not found")
    if not backends_path.exists():
        sys.exit(f"Error: {backends_path} not found")
    if not containerfile.exists():
        sys.exit(f"Error: {containerfile} not found")

    configs = load_yaml(configs_path)
    backends_yaml = load_yaml(backends_path)

    # TODO: Remove FLAGGEMS_VERSION once we switch to wheel-based install.
    flaggems_version = get_flaggems_version(flaggems_dir)

    flaggems_key, vendor, backend = resolve_backend(args.backend, configs)

    build_args = resolve_build_args(
        flaggems_key,
        vendor,
        backend,
        configs,
        backends_yaml,
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
        tag = f"{image_name}:latest"

    cmd = ["docker", "build"]
    for key, value in build_args.items():
        cmd.extend(["--build-arg", f"{key}={value}"])
    cmd.extend(["-f", str(containerfile), "-t", tag, str(flaggems_dir)])

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
