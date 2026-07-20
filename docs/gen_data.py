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

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# load version.py from sibling scripts/ directory
_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_scripts_dir))
from version import image_version

import yaml


def find_repo_root() -> Path:
    d = Path(__file__).resolve().parent.parent
    if (d / "base").is_dir() and (d / "configs.yaml").is_file():
        return d
    sys.exit("Error: cannot locate repository root (base/ + configs.yaml)")


def _git_describe(repo_root: Path) -> str:
    """Fallback version when a Containerfile has no version LABEL."""
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=repo_root, capture_output=True, text=True,
        )
    except FileNotFoundError:
        return "latest"
    desc = r.stdout.strip() if r.returncode == 0 else ""
    if not desc:
        return "latest"
    if desc[0] == "v" and desc[1:2].isdigit():
        desc = desc[1:]
    return desc


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


def _resolve(tok: str, varmap: dict) -> str:
    """Substitute ${VAR}/$VAR from varmap, iteratively (handles nesting)."""
    for _ in range(6):
        new = re.sub(
            r"\$\{(\w+)\}|\$(\w+)",
            lambda m: varmap.get(m.group(1) or m.group(2), m.group(0)),
            tok,
        )
        if new == tok:
            break
        tok = new
    return tok


def parse_containerfile(path: Path, extra_vars: dict | None = None) -> dict:
    """Summarize a base containerfile: base OS, OCI labels, and installed
    system (apt) packages — so docs readers needn't open it."""
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

    # Variable values: extra_vars (e.g. PYTHON_VERSION from configs) win, then
    # ARG/ENV defaults from the containerfile.
    varmap = dict(extra_vars or {})
    for ll in logical:
        m = re.match(r"\s*(?:ARG|ENV)\s+(.*)", ll)
        if m:
            for k, qv, uv in re.findall(r'(\w+)=(?:"([^"]*)"|(\S+))', m.group(1)):
                varmap.setdefault(k, qv or uv)
    for k in list(varmap):
        varmap[k] = _resolve(varmap[k], varmap)

    base_os, labels, system_packages = None, {}, []
    for ll in logical:
        st = ll.strip()
        if st.startswith("#"):
            continue  # commented-out line — not actually installed
        m = re.match(r"FROM\s+(\S+)", st)
        if m and base_os is None:
            base_os = m.group(1)
        for lm in re.finditer(
            r'LABEL\s+org\.opencontainers\.image\.(\w+)\s*=\s*"([^"]*)"', ll
        ):
            labels[lm.group(1)] = lm.group(2)
        # apt packages: take valid package tokens only (skip flags, redirects,
        # operators, comments), with ${VAR} resolved.
        am = re.search(r"apt-get\s+install\s+(.*)", st)
        if am:
            frag = re.split(r"&&|\|\||;", am.group(1))[0]
            for tok in frag.split():
                tok = _resolve(tok, varmap)
                if re.fullmatch(r"[a-z0-9][a-z0-9+.:-]*", tok):
                    system_packages.append(tok)

    return {
        "base_os": base_os,
        "labels": labels,
        "system_packages": _dedup(system_packages),
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


def runtime_packages(spec: dict) -> list:
    """Merged, sorted 'Major Python packages' list for the runtime image:
    deps + the compiler (flagtree and/or triton) + FlagGems.

    triton and its triton_post_install (e.g. triton_ascend) are one compiler
    entry. When a usable flagtree is present, the triton entry is `muted`
    (flagtree is the default; triton is the fallback).
    """
    items = [{"pkg": d, "muted": False} for d in (spec.get("deps") or [])]

    flagtree = spec.get("flagtree")
    if flagtree:
        items.append({"pkg": flagtree, "muted": False})

    triton = spec.get("triton")
    if triton:
        post = spec.get("triton_post_install") or []
        label = f"{triton} (+ {', '.join(post)})" if post else triton
        items.append({"pkg": label, "muted": bool(flagtree)})

    items.append({"pkg": "flag_gems", "muted": False})
    items.sort(key=lambda x: x["pkg"].lower())
    return items


def main():
    repo_root = find_repo_root()
    configs = load_yaml(repo_root / "configs.yaml")
    build_config = load_yaml(repo_root / ".github" / "build-config.yml")

    base_prefix = prefix_for(build_config, "base")
    runtime_prefix = prefix_for(build_config, "runtime")
    run_cfg = build_config.get("run") or {}
    run_default = run_cfg.get("default", "")
    run_vendors = run_cfg.get("vendors") or {}
    run_prereq = run_cfg.get("prereq") or {}
    verify_vendors = (build_config.get("verify") or {}).get("vendors") or {}

    def launch_tiers(vendor):
        """Ordered launch tiers for a vendor: a list of {kind, template}. `kind`
        is 'toolkit' (recommended, needs the container toolkit), 'raw' (device
        passthrough, docker/podman), or 'generic' (plain run, no device flags).
        `template` carries an `{image}` placeholder so each renderer can drop in
        the base or runtime image. Renderers map `kind` to a label (English in
        gen_descriptions, i18n in the Hugo shortcodes), so the list is
        language-neutral.

        Presence rules on the vendor's run entry (a map): a `toolkit`/`toolkit_cmd`
        key -> toolkit tier; a `raw` key -> raw tier (empty string -> generic);
        no `raw` key -> no raw tier (toolkit-only). A legacy bare string is raw
        flags; an unlisted vendor gets a generic tier from the default."""
        rv = run_vendors.get(vendor)
        d = rv if isinstance(rv, dict) else {}
        tiers = []
        if d.get("toolkit_cmd"):
            tiers.append({"kind": "toolkit", "template": d["toolkit_cmd"]})
        elif d.get("toolkit"):
            tiers.append({"kind": "toolkit", "template": f"docker run --rm -it {d['toolkit']} {{image}} bash"})
        if isinstance(rv, dict) and "raw" in d:
            raw = d["raw"]
        elif isinstance(rv, str):
            raw = rv
        elif rv is None:
            raw = run_default  # unlisted vendor -> generic
        else:
            raw = None         # dict without a raw key -> toolkit-only
        if raw is not None:
            flags = f"{raw} " if raw else ""
            tiers.append({"kind": "raw" if raw else "generic",
                          "template": f"docker run --rm -it {flags}{{image}} bash"})
        return tiers

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
            meta = parse_containerfile(cf, {"PYTHON_VERSION": spec.get("python", "")})
            env = spec.get("env") or {}
            sdk = spec.get("sdk") or []
            # Architecture from the SDK notes (they embed the target arch).
            sdk_blob = " ".join(sdk).lower()
            arch = "aarch64" if ("aarch64" in sdk_blob or "arm64" in sdk_blob) else "x86_64"

            ver = image_version(repo_root, name) or _git_describe(repo_root)

            backends.append(
                {
                    "name": name,
                    "vendor": vendor,
                    "backend": backend,
                    "launch": launch_tiers(vendor),
                    "run_prereq": run_prereq.get(vendor, ""),
                    "verify": verify_vendors.get(vendor, ""),
                    "base": {
                        "image": image(base_prefix, "base", name, ver),
                        "os": meta["base_os"] or "",
                        "arch": arch,
                        "hardware": spec.get("hardware") or [],
                        "driver": spec.get("driver", ""),
                        "system_packages": meta["system_packages"],
                        "sdk": sdk,
                        "env": env.get("base") or {},
                    },
                    "runtime": {
                        "image": image(runtime_prefix, "runtime", name, "latest"),
                        "python": spec.get("python", ""),
                        "packages": runtime_packages(spec),
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
