#!/usr/bin/env python3
"""Generate the Hugo data file for the build-infra docs site.

Reads the source-of-truth files and emits docs/data/images.yaml (git-ignored),
which the Hugo shortcodes render into the image catalog and per-image reference
tables. Regenerate before `hugo build` / `hugo serve`.

Sources:
  - configs.yaml            vendors/backends: python, triton, flagtree, deps, env
  - base/<vendor>-<backend> OCI version/revision labels + FROM (base OS)
  - .github/build-config.yml registry host + base path prefix

Only backends that have a base/ file are emitted (others aren't buildable).
"""

import re
import sys
from pathlib import Path

import yaml


def find_repo_root() -> Path:
    d = Path(__file__).resolve().parent.parent
    if (d / "base").is_dir() and (d / "configs.yaml").is_file():
        return d
    sys.exit("Error: cannot locate repository root (base/ + configs.yaml)")


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def parse_containerfile(path: Path) -> dict:
    """Extract FROM (base OS) and OCI version/revision labels."""
    base_os = None
    labels = {}
    with open(path) as f:
        for line in f:
            m = re.match(r"\s*FROM\s+(\S+)", line)
            if m and base_os is None:
                base_os = m.group(1)
            m = re.match(
                r'\s*LABEL\s+org\.opencontainers\.image\.(\w+)\s*=\s*"([^"]*)"', line
            )
            if m:
                labels[m.group(1)] = m.group(2)
    return {"base_os": base_os, "labels": labels}


def registry_prefix(config: dict) -> str:
    reg = config.get("registry") or {}
    host = reg.get("host")
    prefix = (reg.get("prefixes") or {}).get("base")
    if host and prefix:
        return f"{host}/{prefix}"
    return host or ""


def pick_torch(deps: list) -> str:
    for d in deps or []:
        if isinstance(d, str) and d.startswith("torch=="):
            return d
    return ""


def main():
    repo_root = find_repo_root()
    configs = load_yaml(repo_root / "configs.yaml")
    build_config = load_yaml(repo_root / ".github" / "build-config.yml")
    prefix = registry_prefix(build_config)

    backends = []
    for vendor, vbackends in configs.get("vendors", {}).items():
        for backend, spec in vbackends.items():
            name = f"{vendor}-{backend}"
            cf = repo_root / "base" / name
            if not cf.is_file():
                continue  # not buildable — no base image
            meta = parse_containerfile(cf)
            version = meta["labels"].get("version", "latest")
            revision = meta["labels"].get("revision", "0")
            image_name = f"flagos-base-{name}"
            image = f"{prefix}/{image_name}" if prefix else image_name
            image = f"{image}:{version}-{revision}"

            env = spec.get("env") or {}
            backends.append(
                {
                    "name": name,
                    "vendor": vendor,
                    "backend": backend,
                    "image": image,
                    "base_os": meta["base_os"] or "",
                    "python": spec.get("python", ""),
                    "cmake_backend": spec.get("cmake_backend", ""),
                    "triton": spec.get("triton", ""),
                    "flagtree": spec.get("flagtree", ""),
                    "torch": pick_torch(spec.get("deps")),
                    "extras": spec.get("extras", ""),
                    "env_base": env.get("base") or {},
                    "env_runtime": env.get("runtime") or {},
                    "deps": spec.get("deps") or [],
                }
            )

    backends.sort(key=lambda b: b["name"])

    out_dir = repo_root / "docs" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "images.yaml"
    with open(out_path, "w") as f:
        yaml.safe_dump(
            {"backends": backends}, f, sort_keys=False, allow_unicode=True, width=1000
        )

    print(f"Wrote {out_path} ({len(backends)} backends)")


if __name__ == "__main__":
    main()
