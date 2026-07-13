#!/usr/bin/env python3
"""Generate the Hugo data file for the build-infra docs site.

Reads the source-of-truth files and emits docs/data/images.yaml (git-ignored),
which the Hugo shortcodes/content-adapters render into the base and runtime
image catalogs and per-image pages. Regenerate before `hugo build` / `hugo serve`.

Sources:
  - configs.yaml            vendors/backends: python, triton, flagtree, deps, env
  - base/<vendor>-<backend> base OS (FROM), OCI labels, apt + SDK packages
  - .github/build-config.yml registry prefixes + per-vendor `run` flags

Only backends that have a base/ file are emitted (others aren't buildable).
Each entry has a `base` section (from the containerfile) and a `runtime`
section (the software stack from configs.yaml).
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


def _dedup(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def parse_containerfile(path: Path) -> dict:
    """Summarize a base containerfile: base OS, OCI labels, and installed
    system (apt) + vendor SDK packages — so docs readers needn't open it."""
    # Join line-continuations into logical lines.
    logical, buf = [], ""
    for line in path.read_text().splitlines():
        s = line.rstrip()
        if s.endswith("\\"):
            buf += s[:-1] + " "
        else:
            logical.append(buf + s)
            buf = ""
    if buf:
        logical.append(buf)

    base_os, labels, system_packages, sdk_packages = None, {}, [], []
    for ll in logical:
        st = ll.strip()
        m = re.match(r"FROM\s+(\S+)", st)
        if m and base_os is None:
            base_os = m.group(1)
        for lm in re.finditer(
            r'LABEL\s+org\.opencontainers\.image\.(\w+)\s*=\s*"([^"]*)"', ll
        ):
            labels[lm.group(1)] = lm.group(2)
        # apt packages
        am = re.search(r"apt-get\s+install\s+(.*)", st)
        if am:
            frag = re.split(r"&&|\|\||;", am.group(1))[0]
            for tok in frag.split():
                if tok.startswith("-") or tok in ("apt-get", "install"):
                    continue
                system_packages.append(tok)
        # SDK package filenames from ENV *_PACKAGE / *_PKG / PKGS
        if st.startswith("ENV "):
            for km, vm in re.findall(r'([A-Z0-9_]+)=("[^"]*"|\S+)', st[4:]):
                if km.endswith(("_PACKAGE", "_PKG")) or km == "PKGS":
                    for v in vm.strip('"').split():
                        if v:
                            sdk_packages.append(v)

    return {
        "base_os": base_os,
        "labels": labels,
        "system_packages": _dedup(system_packages),
        "sdk_packages": _dedup(sdk_packages),
    }


def prefix_for(config: dict, layer: str) -> str:
    """Registry prefix for a layer, or "" if that layer's prefix isn't set yet."""
    reg = config.get("registry") or {}
    host = reg.get("host")
    p = (reg.get("prefixes") or {}).get(layer)
    return f"{host}/{p}" if (host and p) else ""


def pick(deps, name):
    for d in deps or []:
        if isinstance(d, str) and d.startswith(name):
            return d
    return ""


def software_stack(spec: dict) -> list:
    """The runtime software stack: torch + compiler + FlagGems."""
    deps = spec.get("deps") or []
    stack = []
    torch = pick(deps, "torch==")
    if torch:
        stack.append(torch)
    if spec.get("triton"):
        stack.append(spec["triton"])
    if spec.get("flagtree"):
        stack.append(spec["flagtree"])
    stack.append("flag_gems")  # installed at runtime; version not pinned in configs
    return stack


def main():
    repo_root = find_repo_root()
    configs = load_yaml(repo_root / "configs.yaml")
    build_config = load_yaml(repo_root / ".github" / "build-config.yml")

    base_prefix = prefix_for(build_config, "base")
    runtime_prefix = prefix_for(build_config, "runtime")
    run_cfg = build_config.get("run") or {}
    run_default = run_cfg.get("default", "")
    run_vendors = run_cfg.get("vendors") or {}

    def image(prefix, kind, name, tag):
        base = f"flagos-{kind}-{name}"
        base = f"{prefix}/{base}" if prefix else base
        return f"{base}:{tag}"

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
            env = spec.get("env") or {}

            backends.append(
                {
                    "name": name,
                    "vendor": vendor,
                    "backend": backend,
                    "sdk_version": backend,
                    "run": run_vendors.get(vendor, run_default),
                    "base": {
                        "image": image(base_prefix, "base", name, f"{version}-{revision}"),
                        "os": meta["base_os"] or "",
                        "system_packages": meta["system_packages"],
                        "sdk_packages": meta["sdk_packages"],
                        "env": env.get("base") or {},
                    },
                    "runtime": {
                        "image": image(runtime_prefix, "runtime", name, "latest"),
                        "python": spec.get("python", ""),
                        "stack": software_stack(spec),
                        "deps": spec.get("deps") or [],
                        "env": env.get("runtime") or {},
                    },
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
