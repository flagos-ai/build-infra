#!/usr/bin/env python3
"""Generate a per-image description markdown — the single source rendered by the
docs site, committed as an in-repo maintainer file, and pushed as the Harbor
repository description.

It combines STATIC data from docs/data/images.yaml (architecture, chip models,
container toolkit, SDK components, env, launch command) with the RESOLVED
system-package versions actually baked into the built image. Those versions come
from a per-backend TSV (`<name>.tsv`, lines "package\tversion") produced in CI by
`dpkg-query` inside the image — see .github/workflows/base-descriptions.yml.

The body starts at H2 (no H1): Hugo supplies the page title from the front
matter, and Harbor shows the repository name as the top heading — so the same
body reads correctly in both once the front matter is stripped for Harbor.

Usage:
  python docs/gen_descriptions.py                    # all -> docs/content/en/base/<name>.md
  python docs/gen_descriptions.py nvidia-cuda13.3    # one -> stdout
  VERSIONS_DIR=/path python docs/gen_descriptions.py # resolve versions from <dir>/<name>.tsv
"""

import os
import sys
from pathlib import Path

import yaml


def repo_root() -> Path:
    d = Path(__file__).resolve().parent.parent
    if (d / "configs.yaml").is_file():
        return d
    sys.exit("Error: cannot locate repository root")


def clean_version(v: str) -> str:
    """Debian version -> upstream version users recognise.

    Strip the epoch ("4:") and the Debian/Ubuntu revision ("-1ubuntu1") — both
    are packaging bookkeeping. "4:11.2.0-1ubuntu1" -> "11.2.0". Native packages
    (no "-") keep their version as-is.
    """
    if ":" in v:
        v = v.split(":", 1)[1]
    if "-" in v:
        v = v.rsplit("-", 1)[0]
    return v


def load_versions(versions_dir: Path | None, name: str) -> dict:
    """package -> baked upstream version, from <versions_dir>/<name>.tsv."""
    if not versions_dir:
        return {}
    f = versions_dir / f"{name}.tsv"
    if not f.is_file():
        return {}
    out = {}
    for line in f.read_text().splitlines():
        if "\t" in line:
            pkg, ver = line.split("\t", 1)
            out[pkg.strip()] = clean_version(ver.strip())
    return out


def render(entry: dict, versions: dict) -> str:
    """Compose the description markdown for one backend."""
    base = entry["base"]
    name = entry["name"]
    lines: list[str] = []

    # Hugo front matter (docs title/ordering). Stripped before Harbor upload.
    lines += ["---", f'title: "{name}"', "---", ""]

    # Base OS of the container (a fact about the image, not a host prerequisite).
    if base.get("os"):
        lines += [f"Base image: `{base['os']}`", ""]

    # ── Prerequisites ────────────────────────────────────────────
    lines += ["## Prerequisites", ""]
    lines.append(f"- **Architecture:** {base.get('arch', '')}")
    hw = base.get("hardware") or []
    if hw:
        lines.append(f"- **Chip models:** {', '.join(hw)}")
    toolkit = entry.get("run_prereq") or ""
    if toolkit:
        lines.append(f"- **Host container toolkit:** {toolkit}")
    lines.append("")

    # ── System packages (explicit apt, with baked-in versions) ──
    pkgs = base.get("system_packages") or []
    if pkgs:
        lines += ["## System packages", ""]
        lines += ["Explicitly installed; the version is the one baked into this image:", ""]
        for p in sorted(pkgs):
            ver = versions.get(p)
            lines.append(f"- `{p}` — {ver}" if ver else f"- `{p}`")
        lines.append("")

    # ── SDK components (already versioned in configs) ───────────
    sdk = base.get("sdk") or []
    if sdk:
        lines += ["## SDK components", ""]
        for s in sdk:
            lines.append(f"- {s}")
        lines.append("")

    # ── Environment ─────────────────────────────────────────────
    env = base.get("env") or {}
    if env:
        lines += ["## Environment", ""]
        for k, v in env.items():
            lines.append(f"- `{k}={v}`")
        lines.append("")

    # ── Launch ──────────────────────────────────────────────────
    run_flags = entry.get("run") or ""
    flags = f"{run_flags} " if run_flags else ""
    lines += ["## Launch", ""]
    lines += ["Start an interactive shell in the container:", ""]
    lines += ["```bash", f"docker run --rm -it {flags}{base['image']} bash", "```", ""]

    # ── Verify ──────────────────────────────────────────────────
    # Shown as a SEPARATE command to run INSIDE the launched container (not
    # folded into the `docker run` line): some vendor runtimes take a moment or
    # hang on the first container start, so users run the device check on its
    # own and can retry it independently.
    verify = entry.get("verify")
    if verify:
        lines += ["## Verify", ""]
        lines += [
            "Inside the container, confirm the accelerator is visible "
            "(the first run may take a moment):",
            "",
        ]
        lines += ["```bash", verify, "```", ""]

    return "\n".join(lines).rstrip() + "\n"


def main():
    root = repo_root()
    images = yaml.safe_load((root / "docs" / "data" / "images.yaml").read_text())
    backends = {b["name"]: b for b in images.get("backends", [])}

    vdir = os.environ.get("VERSIONS_DIR")
    versions_dir = Path(vdir).resolve() if vdir else None

    requested = sys.argv[1:]
    if requested:
        for name in requested:
            if name not in backends:
                sys.exit(f"Error: '{name}' not in images.yaml")
            print(render(backends[name], load_versions(versions_dir, name)))
        return

    out_dir = root / "docs" / "content" / "en" / "base"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, entry in backends.items():
        md = render(entry, load_versions(versions_dir, name))
        (out_dir / f"{name}.md").write_text(md)
    print(f"Wrote {len(backends)} descriptions to {out_dir}")


if __name__ == "__main__":
    main()
