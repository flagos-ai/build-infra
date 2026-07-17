#!/usr/bin/env python3
"""Generate a per-image description markdown — the single source rendered by the
docs site, committed as an in-repo maintainer file, and pushed as the Harbor
repository description.

It combines STATIC data from docs/data/images.yaml (architecture, chip models,
container toolkit, SDK components, env, launch command) with the RESOLVED
system-package versions actually baked into the built image. Those versions come
from a per-backend TSV (`<name>.tsv`, lines "package\tversion") produced in CI by
`dpkg-query` inside the image — see .github/workflows/base-descriptions.yml.

Both languages are generated from the same language-neutral data: only the prose
and section headers differ (the STRINGS table below), while the technical values
(chip models, SDK strings, package names, env, launch/verify commands) are
verbatim in both. This keeps en/ and zh-cn/ in lockstep — the reason both are
emitted from one generator rather than a per-language shortcode.

Two output flavors feed three consumers:
  - "web"   -> docs/content/{en,zh-cn}/base/*.md — the Hugo site. Keeps front
               matter and renders the container-toolkit caveat as an info marker
               that shows a Bootstrap tooltip on hover (styled in
               docs/assets/docs/scss/custom/structure/_content.scss).
  - "plain" -> base/*.md (English) — the in-repo image readme and the source for
               the Harbor repository description. No front matter, no tooltip.
These are separate files, so the web pages can be polished (HTML/CSS) without
touching the plain readmes.

The body starts at H2 (no H1): Hugo supplies the page title from the front
matter, and Harbor shows the repository name as the top heading — so the same
body reads correctly in both.

Usage:
  python docs/gen_descriptions.py                    # all langs + plain -> files
  python docs/gen_descriptions.py nvidia-cuda13.3    # one backend, all langs + plain -> stdout
  VERSIONS_DIR=/path python docs/gen_descriptions.py # resolve versions from <dir>/<name>.tsv
"""

import os
import sys
from pathlib import Path

import yaml


# Prose and section headers per language. Keys mirror the labels in
# i18n/zh-cn.toml so the two Chinese renderings stay consistent. Everything the
# docs pipeline treats as data (chip models, SDK strings, package names, env,
# launch/verify commands) is language-neutral and NOT listed here — it renders
# verbatim in both languages.
LANGS = ("en", "zh-cn")

STRINGS = {
    "en": {
        "prerequisites": "Prerequisites",
        "architecture": "Architecture",
        "chip_models": "Chip models",
        "host_driver": "Host driver",
        "toolkit": "Container toolkit",
        "toolkit_optional": "*(optional)*",
        "toolkit_tooltip": "only for the toolkit launch below; the plain docker/podman command needs none",
        "image_contents": "Image contents",
        "base_image": "Base image",
        "system_packages": "System packages",
        "system_packages_note": "Explicitly installed; the version is the one baked into this image:",
        "sdk_components": "SDK components",
        "environment": "Environment",
        "launch": "Launch",
        "launch_toolkit_optional": "**With the container toolkit** *(optional)*:",
        "launch_toolkit": "**With the container toolkit**:",
        "launch_raw_both": "**Without a toolkit** — plain docker / podman:",
        "launch_raw_only": "Start an interactive shell (works with docker or podman):",
        "launch_generic": "Start an interactive shell in the container:",
        "verify": "Verify",
        "verify_note": "Inside the container, confirm the accelerator is visible:",
    },
    "zh-cn": {
        "prerequisites": "前置条件",
        "architecture": "架构",
        "chip_models": "芯片型号",
        "host_driver": "宿主机驱动",
        "toolkit": "容器工具包",
        "toolkit_optional": "*(可选)*",
        "toolkit_tooltip": "仅用于下方的工具包启动方式；直接使用 docker/podman 的命令无需安装",
        "image_contents": "镜像内容",
        "base_image": "基础镜像",
        "system_packages": "系统软件包",
        "system_packages_note": "显式安装；此处版本即为该镜像中实际打包的版本：",
        "sdk_components": "SDK 组件",
        "environment": "环境变量",
        "launch": "启动",
        "launch_toolkit_optional": "**使用容器工具包** *(可选)*：",
        "launch_toolkit": "**使用容器工具包**：",
        "launch_raw_both": "**无需工具包** —— 直接使用 docker / podman：",
        "launch_raw_only": "启动交互式 shell（docker 或 podman 均可）：",
        "launch_generic": "在容器中启动交互式 shell：",
        "verify": "验证",
        "verify_note": "在容器内，确认加速器可见：",
    },
}


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


def render(entry: dict, versions: dict, lang: str = "en", flavor: str = "web") -> str:
    """Compose the description markdown for one backend in `lang`.

    Only prose/headers are localized (from STRINGS); every technical value —
    chip models, SDK strings, package names, env, launch/verify commands —
    renders verbatim, so the two languages stay structurally identical.

    Two flavors, because the same content feeds three consumers with different
    needs:
      - "web"   — the Hugo site. Keeps the Hugo front matter and renders the
                  container-toolkit caveat as an info marker that shows a
                  Bootstrap tooltip on hover, so the page stays uncluttered but
                  the explanation is one hover away.
      - "plain" — the in-repo base/<name>.md readme and the Harbor repository
                  description. No front matter, no tooltip: the toolkit line is
                  just "*(optional)*" with the caveat dropped (these surfaces
                  render plain markdown and have no hover affordance).
    """
    s = STRINGS[lang]
    web = flavor == "web"
    base = entry["base"]
    name = entry["name"]
    lines: list[str] = []

    # Hugo front matter (docs title/ordering) — web flavor only. The plain flavor
    # feeds a repo readme / Harbor description, where the front matter is noise.
    if web:
        lines += ["---", f'title: "{name}"', "---", ""]

    # ── Prerequisites ────────────────────────────────────────────
    lines += [f"## {s['prerequisites']}", ""]
    lines.append(f"- **{s['architecture']}:** {base.get('arch', '')}")
    hw = base.get("hardware") or []
    if hw:
        lines.append(f"- **{s['chip_models']}:** {', '.join(hw)}")
    drv = base.get("driver") or ""
    if drv:
        lines.append(f"- **{s['host_driver']}:** {drv}")
    toolkit = entry.get("run_prereq") or ""
    if toolkit:
        # The container toolkit is only needed for the toolkit launch. Where a
        # raw/generic tier also exists it's optional; only truly required for
        # toolkit-only backends. On the web that "why" is a Bootstrap tooltip
        # shown on hovering an info marker (the Lotus Docs theme initializes
        # every [data-bs-toggle="tooltip"] on load); in the plain flavor it's
        # dropped (no hover), leaving a bare "*(optional)*".
        has_raw = any(t["kind"] in ("raw", "generic") for t in (entry.get("launch") or []))
        if has_raw:
            if web:
                # Emit the emphasis as literal <em> rather than markdown "*...*":
                # Goldmark does not re-parse markdown inside an inline HTML span.
                # The caveat is a separate info marker; the tooltip shows on hover
                # (and keyboard focus) — Bootstrap's default trigger.
                label = s["toolkit_optional"].strip("*")
                opt = (
                    f"<em>{label}</em> "
                    '<button type="button" class="toolkit-optional-info" '
                    'data-bs-toggle="tooltip" '
                    f'data-bs-title="{s["toolkit_tooltip"]}" '
                    f'aria-label="{s["toolkit_tooltip"]}">&#9432;</button>'
                )
            else:
                opt = s["toolkit_optional"]
            lines.append(f"- **{s['toolkit']}** {opt}: {toolkit}")
        else:
            lines.append(f"- **{s['toolkit']}:** {toolkit}")
    lines.append("")

    # ── Image contents (base OS + system packages + SDK components) ──
    pkgs = base.get("system_packages") or []
    sdk = base.get("sdk") or []
    if base.get("os") or pkgs or sdk:
        lines += [f"## {s['image_contents']}", ""]
        if base.get("os"):
            lines += [f"### {s['base_image']}", "", f"`{base['os']}`", ""]
        if pkgs:
            lines += [f"### {s['system_packages']}", ""]
            lines += [s["system_packages_note"], ""]
            for p in sorted(pkgs):
                ver = versions.get(p)
                lines.append(f"- `{p}` — {ver}" if ver else f"- `{p}`")
            lines.append("")
        if sdk:
            lines += [f"### {s['sdk_components']}", ""]
            for item in sdk:
                lines.append(f"- {item}")
            lines.append("")

    # ── Environment ─────────────────────────────────────────────
    env = base.get("env") or {}
    if env:
        lines += [f"## {s['environment']}", ""]
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
        lines += [f"## {s['launch']}", ""]
        for t in tiers:
            cmd = wrap_cmd(t["template"].replace("{image}", image))
            if t["kind"] == "toolkit":
                hdr = s["launch_toolkit_optional"] if both else s["launch_toolkit"]
            elif t["kind"] == "raw":
                hdr = s["launch_raw_both"] if both else s["launch_raw_only"]
            else:  # generic
                hdr = s["launch_generic"]
            lines += [hdr, "", "```bash", cmd, "```", ""]

    # ── Verify ──────────────────────────────────────────────────
    # A SEPARATE command to run INSIDE the launched container (not folded into the
    # docker run line): some vendor runtimes hang on first touch, so users run the
    # device check on its own and can retry it independently.
    verify = entry.get("verify")
    if verify:
        lines += [f"## {s['verify']}", ""]
        lines += [s["verify_note"], ""]
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
        # Spot-check to stdout: every requested backend, every language, both
        # flavors — so a single-backend check never silently covers just one.
        for name in requested:
            if name not in backends:
                sys.exit(f"Error: '{name}' not in images.yaml")
            versions = load_versions(versions_dir, name)
            for lang in LANGS:
                print(render(backends[name], versions, lang, "web"))
            print(render(backends[name], versions, "en", "plain"))
        return

    # Web flavor: every backend, every language, into the Hugo content tree. The
    # zh-cn pages stay in lockstep with en; both may use tooltips/HTML.
    total = 0
    for lang in LANGS:
        out_dir = root / "docs" / "content" / lang / "base"
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, entry in backends.items():
            md = render(entry, load_versions(versions_dir, name), lang, "web")
            (out_dir / f"{name}.md").write_text(md)
            total += 1
        print(f"Wrote {len(backends)} {lang} web pages to {out_dir}")

    # Plain flavor: English only, into base/<name>.md — the in-repo image readme
    # and the source for the Harbor repository description. Real files (no longer
    # symlinks into docs/), so the web pages can be polished independently.
    base_dir = root / "base"
    for name, entry in backends.items():
        md = render(entry, load_versions(versions_dir, name), "en", "plain")
        (base_dir / f"{name}.md").write_text(md)
    print(f"Wrote {len(backends)} plain readmes to {base_dir}")
    print(f"Total: {total + len(backends)} descriptions")


if __name__ == "__main__":
    main()
