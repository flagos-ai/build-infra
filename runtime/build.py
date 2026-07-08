#!/usr/bin/env python3
"""Build FlagGems runtime container images.

Reads runtime/configs.yaml and FlagGems's src/flag_gems/backends.yaml to
resolve build arguments, then invokes `docker build` with the appropriate
--build-arg values.

Usage:
    python runtime/build.py <backend-key> --flaggems-dir <path> [options]

Examples:
    python runtime/build.py nvidia-cuda128 --flaggems-dir ../FlagGems --dry-run
    python runtime/build.py ascend-cann900 --flaggems-dir ../FlagGems --tag latest
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


def resolve_backend(backend_arg: str, configs: dict):
    """Resolve user input to (backends_yaml_key, variant).

    configs.yaml maps vendor → [variants]. The variant uses human-readable
    names (e.g. "cuda12.8"), while backends.yaml keys strip dots
    (e.g. "nvidia-cuda128").

    Accepts input in either form:
      - configs.yaml style: "nvidia-cuda12.8"
      - backends.yaml style: "nvidia-cuda128"
      - vendor shorthand: "metax" (if single variant)

    Returns (backends_yaml_key, variant_suffix) where:
      - backends_yaml_key is the key in backends.yaml (dots stripped)
      - variant_suffix is the configs.yaml variant (for base image name)
    """
    cfg_backends = configs.get("backends", {})

    def strip_dots(s):
        return s.replace(".", "")

    # Try matching against all vendor-variant combinations
    for vendor, variants in cfg_backends.items():
        for variant in variants:
            full_dotted = f"{vendor}-{variant}"
            full_stripped = f"{vendor}-{strip_dots(variant)}"
            if backend_arg in (full_dotted, full_stripped):
                # Multi-variant: backends.yaml key has dots stripped
                return full_stripped, variant
            if backend_arg == vendor and len(variants) == 1:
                # Single-variant shorthand
                return vendor, variant

    # Try matching vendor name with multiple variants
    if backend_arg in cfg_backends:
        variants = cfg_backends[backend_arg]
        if len(variants) > 1:
            names = [f"{backend_arg}-{v}" for v in variants]
            sys.exit(
                f"Error: '{backend_arg}' has multiple variants: "
                f"{', '.join(names)}"
            )

    sys.exit(f"Error: '{backend_arg}' not found in configs.yaml backends")


def resolve_base_image(variant: str, configs: dict) -> str:
    """Derive base image name: {prefix}-{variant}:{tag}."""
    prefix = configs.get("base_image_prefix", "flagos-base")
    tag = configs.get("base_image_tag", "latest")
    return f"{prefix}-{variant}:{tag}"


def resolve_build_args(
    backend_key: str,
    variant: str,
    configs: dict,
    backends: dict,
    *,
    base_image_override: str | None = None,
    extra_pypi_override: str | None = None,
    include_tests_override: str | None = None,
) -> dict[str, str]:
    """Resolve all docker build-arg values for a given backend."""

    backend_info = backends.get("backends", {}).get(backend_key)
    if backend_info is None:
        sys.exit(f"Error: '{backend_key}' not found in backends.yaml")

    vendor = backend_key.split("-")[0]
    pypi_base = backends.get("pypi_base", "")
    mirror = backends.get("mirror", "https://mirrors.aliyun.com/pypi/simple")

    args = {
        "BASE_IMAGE": base_image_override or resolve_base_image(variant, configs),
        "PYTHON_VERSION": backend_info.get("python", "3.12"),
        "FLAGOS_PYPI": pypi_base.format(vendor=vendor) if pypi_base else "",
        "EXTRA_PYPI": extra_pypi_override or mirror,
        "EXTRAS_GROUP": backend_key,
        "INCLUDE_TESTS": include_tests_override or "true",
    }

    # Optional hooks from backends.yaml
    for key in ("pre_install", "post_install"):
        val = backend_info.get(key, "")
        if isinstance(val, str):
            val = val.strip()
        if val:
            args[key.upper()] = val

    return args


def main():
    parser = argparse.ArgumentParser(
        description="Build FlagGems runtime container images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "backend",
        help="Backend key (e.g. nvidia-cuda128, ascend-cann900, metax)",
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
    flaggems_dir = Path(args.flaggems_dir).resolve()

    configs_path = script_dir / "configs.yaml"
    backends_path = flaggems_dir / "src" / "flag_gems" / "backends.yaml"
    containerfile = script_dir / "Containerfile"

    if not configs_path.exists():
        sys.exit(f"Error: {configs_path} not found")
    if not backends_path.exists():
        sys.exit(f"Error: {backends_path} not found")
    if not containerfile.exists():
        sys.exit(f"Error: {containerfile} not found")

    configs = load_yaml(configs_path)
    backends = load_yaml(backends_path)

    backend_key, variant = resolve_backend(args.backend, configs)

    build_args = resolve_build_args(
        backend_key,
        variant,
        configs,
        backends,
        base_image_override=args.base_image,
        extra_pypi_override=args.extra_pypi,
        include_tests_override=args.include_tests,
    )

    image_name = f"flaggems-{backend_key}"

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
