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


PKG_RE = re.compile(r"\.(?:run|deb|tar\.gz|tar\.xz|tgz|zip|whl)$")


def _resolve_vars(s: str, varmap: dict, depth: int = 0) -> str:
    """Substitute ${VAR}/$VAR from varmap, iteratively (handles nesting)."""
    if depth > 10 or "$" not in s:
        return s
    new = re.sub(
        r"\$\{(\w+)\}|\$(\w+)",
        lambda m: varmap.get(m.group(1) or m.group(2), m.group(0)),
        s,
    )
    return new if new == s else _resolve_vars(new, varmap, depth + 1)


def extract_sdk_packages(logical: list) -> list:
    """Vendor SDK package files actually downloaded from the file store.

    Captures the token after `${FILE_STORE}/` (the real package), resolving
    ARG/ENV vars, `for X in ${LIST}` loops, and `fn="...${X}..."` constructions.
    Avoids `curl -o <localname>` targets and unused/stray ARG declarations.
    """
    # ARG/ENV variable values (values may reference other vars).
    varmap = {}
    for ll in logical:
        m = re.match(r"\s*(?:ARG|ENV)\s+(.*)", ll)
        if not m:
            continue
        for km, qv, uv in re.findall(r'(\w+)=(?:"([^"]*)"|(\S+))', m.group(1)):
            varmap[km] = qv or uv
    for k in list(varmap):
        varmap[k] = _resolve_vars(varmap[k], varmap)

    # `for X in ${LIST}` → X ranges over the (space-split) resolved list.
    loopvars = {}
    for ll in logical:
        for lm in re.finditer(r"for\s+(\w+)\s+in\s+\$\{(\w+)\}", ll):
            loopvars[lm.group(1)] = _resolve_vars(
                "${" + lm.group(2) + "}", varmap
            ).split()

    # `fn="...${X}..."` filename constructions.
    fnvars = {}
    for ll in logical:
        for fm in re.finditer(r'(\w+)="([^"]*\$\{?\w+\}?[^"]*)"', ll):
            fnvars.setdefault(fm.group(1), fm.group(2))

    def expand(base: str) -> list:
        m = re.fullmatch(r"\$\{?(\w+)\}?", base)
        if not m:
            return [base]
        name = m.group(1)
        if name in loopvars:
            return list(loopvars[name])
        if name in fnvars:
            tmpl = fnvars[name]
            for lv, vals in loopvars.items():
                if re.search(r"\$\{?" + lv + r"\}?", tmpl):
                    return [re.sub(r"\$\{?" + lv + r"\}?", v, tmpl) for v in vals]
            return [tmpl]
        return [varmap.get(name, base)]

    found = []
    for ll in logical:
        for fm in re.finditer(r"\$\{FILE_?STORE\}/(\S+)", ll):
            raw = fm.group(1).strip("\"';\\")
            base = raw.split("/")[-1]
            for cand in expand(base):
                c = _resolve_vars(cand, varmap)
                if "$" not in c and PKG_RE.search(c):
                    found.append(c)
    return _dedup(found)


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

    base_os, labels, system_packages = None, {}, []
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

    return {
        "base_os": base_os,
        "labels": labels,
        "system_packages": _dedup(system_packages),
        "sdk_packages": extract_sdk_packages(logical),
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
            bsdk = spec.get("sdk") or {}  # per-backend package descriptions

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
                        "sdk_packages": [
                            {"file": p, "desc": bsdk.get(p, "")}
                            for p in meta["sdk_packages"]
                        ],
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
