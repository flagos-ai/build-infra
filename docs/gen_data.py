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
    # Comments don't continue — a `#` line ending with `\` does not swallow
    # the next line; otherwise a build instruction that follows a
    # commented-out continuation loses its apt-get install packages.
    logical, buf = [], ""
    for line in path.read_text().splitlines():
        s = line.rstrip()
        if s.lstrip().startswith("#"):
            logical.append(s)
            buf = ""
        elif s.endswith("\\"):
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
        # Split on && / || / ; first — multiple apt-get install calls may
        # appear in the same logical line (e.g. ascend Containerfile).
        for frag in re.split(r"&&|\|\||;", st):
            am = re.search(r"apt-get\s+install\s+(.*)", frag)
            if am:
                for tok in am.group(1).split():
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


def runtime_packages(spec: dict, flaggems_version: str = "") -> list:
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

    fg = f"flag_gems=={flaggems_version}" if flaggems_version else "flag_gems"
    items.append({"pkg": fg, "muted": False})
    items.sort(key=lambda x: x["pkg"].lower())
    return items


# --- App image launch data ---------------------------------------

# Default app-image versions, matching the workflow_dispatch defaults in
# .github/workflows/megatron-app-image.yml / vllm-app-image.yml. Repo names
# embed the app version with no dash; the tag carries the stack version plus,
# for megatron, the MLF fork version (mlf_version '+' -> '_').
#
# vllm is split per repacked version: deps_app keys are 'vllm<version>'
# (configs.yaml), and the version segment — not this default — drives the
# repo name / tag / package string. The bare 'vllm' entry here only supplies
# the workflow_dispatch default version and the shared launcher / CMD data.
APP_IMAGE_DEFAULTS = {
    "megatron_training": {"app_version": "0.17.1", "fork_version": "0.2.1", "package": "megatron-core"},
    "megatron_rl":       {"app_version": "0.17.1", "fork_version": "0.2.1", "package": "megatron-core"},
    "vllm":              {"app_version": "0.24.0", "fork_version": "", "package": "vllm"},
}

# Launcher-with-args examples for the docs pages, verbatim from the app
# Containerfile comments (megatron-train --model-type GPT; vllm-serve override
# --model <path> --port 9000). megatron_rl has no launcher yet — empty list.
APP_LAUNCH_EXAMPLES = {
    "megatron_training": ["megatron-train", "--model-type", "GPT"],
    "megatron_rl": [],
    "vllm": ["vllm-serve", "--model", "<path>", "--port", "9000"],
}

# Per-app launcher + default CMD, verbatim from the app Containerfiles.
# megatron_rl has no launcher yet (Containerfile.rl only sets WORKDIR) — the
# page renders a placeholder instead.
APP_LAUNCHERS = {
    "megatron_training": "megatron-train",
    "megatron_rl": "",
    "vllm": "vllm-serve",
}
APP_CMD_DEFAULTS = {
    "megatron_training": ["megatron-train"],
    "megatron_rl": [],  # inherits the runtime image's CMD ["bash"]
    "vllm": [
        "vllm-serve", "--model", "/data/models/Qwen/Qwen3-4B", "--port", "8031",
        "--gpu-memory-utilization", "0.6", "--enforce-eager", "--trust-remote-code",
        "--max-model-len", "2048", "--dtype", "bfloat16",
    ],
}

# App image repos already published to Harbor are tracked by the status
# matrix: `packaging/{megatron|vllm}/status_matrix.{app}.yaml` carries an
# `image_tag` on the published backend block — the verifier who pushes the
# image records the tag, and a backend with a tag is published (single source,
# no separate boolean to drift). Combos without a tag are not published yet
# and render as placeholders.
def app_published_tag(app: str, name: str) -> str:
    """Exact Harbor tag of a published app image combo, from the status
    matrix's `image_tag` field; "" if unpublished or not recorded.

    The megatron fork segments and the vllm plugin segments in those tags are
    the workflow inputs actually used (mlf_version / plugin_fl_version) —
    upstream branch heads that a build cannot discover inside the container,
    so the matrix is the only record of what went into each pushed tag.
    """
    component = "megatron" if app.startswith("megatron") else "vllm"
    path = (
        find_repo_root() / "packaging" / component / f"status_matrix.{app}.yaml"
    )
    if not path.is_file():
        return ""
    matrix = load_yaml(path)
    return ((matrix.get("backends") or {}).get(name) or {}).get("image_tag") or ""


def app_image_data(app_prefix: str, app: str, name: str, stack_version: str) -> dict:
    """Per-app launch data for one backend: the image ref (published combos
    carry the exact Harbor tag from the status matrix's `image_tag`, the rest
    get the workflow-default derivation), the published status, and the
    launcher / default CMD for the docs page.

    App keys are 'megatron_training' / 'megatron_rl' / 'vllm<version>' — vllm
    is split per repacked version (configs.yaml deps_app.vllm<version>), and
    the key's version segment drives the vllm repo name / tag / package string.
    megatron repos are named {app}{app_version}-{vendor}-{backend} (app name +
    version, no separator) and tagged {stack}-{fork_version}; vllm repos are
    named vllm{vllm_version}-{vendor}-{backend} and tagged {stack} (a non-empty
    plugin_fl_version input would append -{fork} to the tag).
    """
    base_app = "vllm" if app.startswith("vllm") else app
    d = APP_IMAGE_DEFAULTS[base_app]
    # vllm versions come from the deps_app key (vllm0.20.2 -> 0.20.2), not the
    # workflow default in APP_IMAGE_DEFAULTS.
    app_version = app.removeprefix("vllm") if app.startswith("vllm") else d["app_version"]
    if app.startswith("megatron"):
        repo = f"{app}{app_version}-{name}"
        tag = f"{stack_version}-{d['fork_version']}"
    else:
        repo = f"vllm{app_version}-{name}"
        tag = stack_version
    published_tag = app_published_tag(app, name)
    base = f"{app_prefix}/{repo}" if app_prefix else repo
    # Install spec, verbatim from the app Containerfiles: megatron apps select
    # the [training]/[rl] extra of megatron-core; vllm pins the +flagos wheel
    # (a bare version would pull torch over the pinned vendor torch).
    if app.startswith("megatron"):
        package = f"megatron-core[{app.split('_', 1)[1]}]=={app_version}"
    else:
        package = f"vllm=={app_version}+flagos"
    # vllm-plugin-FL rides in the same image as vllm itself. Its version is the
    # tag's plugin segment (the workflow input plugin_fl_version, '+' -> '_'),
    # and is not discoverable inside the container at build time — so published
    # combos carry it here, back-derived from the exact Harbor tag. Unpublished
    # combos get an empty spec and the page shows only the vllm wheel.
    plugin_package = (
        f"vllm-plugin-fl=={published_tag.split('-', 1)[1].replace('_', '+')}"
        if app.startswith("vllm") and published_tag and "-" in published_tag
        else ""
    )
    return {
        "image": f"{base}:{published_tag or tag}",
        "published": bool(published_tag),
        "app_version": f"{d['package']} {app_version}",
        "package": package,
        "plugin_package": plugin_package,
        "launcher": APP_LAUNCHERS[base_app],
        "cmd": APP_CMD_DEFAULTS[base_app],
        "example": APP_LAUNCH_EXAMPLES[base_app],
    }


def main():
    repo_root = find_repo_root()
    configs = load_yaml(repo_root / "configs.yaml")
    build_config = load_yaml(repo_root / ".github" / "build-config.yml")

    base_prefix = prefix_for(build_config, "base")
    runtime_prefix = prefix_for(build_config, "runtime")
    app_prefix = prefix_for(build_config, "app")
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

            ver = image_version(repo_root) or _git_describe(repo_root)

            # Merge dpkg-installed system-level packages (e.g. libfmt8 for
            # tsingmicro) — these are exceptions declared in configs.yaml, not
            # the SDK .debs that get their own section.
            sys_pkgs = list(meta["system_packages"])
            for p in spec.get("system_dpkg", []) or []:
                sys_pkgs.append(p)

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
                        "system_packages": _dedup(sys_pkgs),
                        "sdk": sdk,
                        "env": env.get("base") or {},
                    },
                    "runtime": {
                        "image": image(runtime_prefix, "runtime", name, configs["version"]),
                        "python": spec.get("python", ""),
                        "packages": runtime_packages(spec, configs.get("flaggems", "")),
                        "env": env.get("runtime") or {},
                    },
                    "app": {
                        # Per-app env vars (configs.yaml env.app.{app}) — consumed
                        # by generate_matrix.py --app for app image builds.
                        "env": env.get("app") or {},
                        # Per-app launch data for the docs site: image ref,
                        # published status, launcher and default CMD. Which apps
                        # a backend builds/verifies/publishes is decided by
                        # configs.yaml deps_app.{app} — key presence means the app
                        # is buildable here, so the launch pages follow deps_app,
                        # not a hardcoded app list.
                        "images": {
                            a: app_image_data(app_prefix, a, name, configs["version"])
                            for a in spec.get("deps_app") or {}
                            if a in APP_IMAGE_DEFAULTS or a.startswith("vllm")
                        },
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
