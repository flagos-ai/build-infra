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


def wrap_cmd(cmd: str, width: int = 84) -> str:
    """Wrap a long `docker run …` / wrapper-launcher command onto multiple lines
    (one flag per continuation line) so the code block doesn't scroll sideways.
    Short commands are left as-is."""
    if len(cmd) <= width:
        return cmd
    head = "docker run --rm -it"
    if cmd.startswith(head + " "):
        rest = cmd[len(head) + 1:]
    else:  # wrapper launcher, e.g. `metax-docker …`
        head, _, rest = cmd.partition(" ")
    toks = rest.split(" ")
    tail = f"{toks[-2]} {toks[-1]}"  # "<image> bash"
    toks = toks[:-2]
    groups, i = [], 0
    while i < len(toks):
        if toks[i].startswith("-") and i + 1 < len(toks) and not toks[i + 1].startswith("-"):
            groups.append(f"{toks[i]} {toks[i + 1]}"); i += 2
        else:
            groups.append(toks[i]); i += 1
    out = [f"{head} \\"] + [f"  {g} \\" for g in groups] + [f"  {tail}"]
    return "\n".join(out)


def render(entry: dict, versions: dict) -> str:
    """Compose the description markdown for one backend."""
    base = entry["base"]
    name = entry["name"]
    lines: list[str] = []

    # Hugo front matter (docs title/ordering). Stripped before Harbor upload.
    lines += ["---", f'title: "{name}"', "---", ""]

    # ── Prerequisites ────────────────────────────────────────────
    lines += ["## Prerequisites", ""]
    lines.append(f"- **Architecture:** {base.get('arch', '')}")
    hw = base.get("hardware") or []
    if hw:
        lines.append(f"- **Chip models:** {', '.join(hw)}")
    drv = base.get("driver") or ""
    if drv:
        lines.append(f"- **Host driver:** {drv}")
    toolkit = entry.get("run_prereq") or ""
    if toolkit:
        # The container toolkit is only needed for the toolkit launch. Where a
        # raw/generic tier also exists it's optional; only truly required for
        # toolkit-only backends.
        has_raw = any(t["kind"] in ("raw", "generic") for t in (entry.get("launch") or []))
        if has_raw:
            lines.append(f"- **Container toolkit** *(optional — only for the toolkit launch below; the plain docker/podman command needs none)*: {toolkit}")
        else:
            lines.append(f"- **Container toolkit:** {toolkit}")
    lines.append("")

    # ── Image contents (base OS + system packages + SDK components) ──
    pkgs = base.get("system_packages") or []
    sdk = base.get("sdk") or []
    if base.get("os") or pkgs or sdk:
        lines += ["## Image contents", ""]
        if base.get("os"):
            lines += ["### Base image", "", f"`{base['os']}`", ""]
        if pkgs:
            lines += ["### System packages", ""]
            lines += ["Explicitly installed; the version is the one baked into this image:", ""]
            for p in sorted(pkgs):
                ver = versions.get(p)
                lines.append(f"- `{p}` — {ver}" if ver else f"- `{p}`")
            lines.append("")
        if sdk:
            lines += ["### SDK components", ""]
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
    # One block per launch tier (see gen_data.launch_tiers). When both a toolkit
    # and a raw tier exist, the toolkit is labelled optional and the raw one is the
    # no-toolkit/podman path; a lone tier gets a plain header. The toolkit version
    # is not repeated here — it's in Prerequisites.
    image = base["image"]
    tiers = entry.get("launch") or []
    both = any(t["kind"] == "toolkit" for t in tiers) and any(t["kind"] == "raw" for t in tiers)
    if tiers:
        lines += ["## Launch", ""]
        for t in tiers:
            cmd = wrap_cmd(t["template"].replace("{image}", image))
            if t["kind"] == "toolkit":
                opt = " *(optional)*" if both else ""
                hdr = f"**With the container toolkit**{opt}:"
            elif t["kind"] == "raw":
                hdr = ("**Without a toolkit** — plain docker / podman:" if both
                       else "Start an interactive shell (works with docker or podman):")
            else:  # generic
                hdr = "Start an interactive shell in the container:"
            lines += [hdr, "", "```bash", cmd, "```", ""]

    # ── Verify ──────────────────────────────────────────────────
    # A SEPARATE command to run INSIDE the launched container (not folded into the
    # docker run line): some vendor runtimes hang on first touch, so users run the
    # device check on its own and can retry it independently.
    verify = entry.get("verify")
    if verify:
        lines += ["## Verify", ""]
        lines += ["Inside the container, confirm the accelerator is visible:", ""]
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
