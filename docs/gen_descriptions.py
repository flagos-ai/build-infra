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
        "base_image_ref": "Built on",
        "system_packages": "System packages",
        "system_packages_note": "Explicitly installed; the version is the one baked into this image:",
        "sdk_components": "SDK components",
        "python_version": "Python",
        "major_packages": "Major Python packages",
        "fallback_note": "Greyed = fallback compiler (flagtree is the default; triton is used only if flagtree is unavailable).",
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
        "base_image_ref": "基于",
        "system_packages": "系统软件包",
        "system_packages_note": "显式安装；此处版本即为该镜像中实际打包的版本：",
        "sdk_components": "SDK 组件",
        "python_version": "Python",
        "major_packages": "主要 Python 软件包",
        "fallback_note": "灰色 = 备用编译器（默认使用 flagtree；仅当 flagtree 不可用时才回退到 triton）。",
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

# Apache 2.0 copyright header — HTML comment, web flavor only.
# Harbor can't parse HTML comments in repository descriptions, so the plain
# flavor (base/*.md and runtime/*.md) omits this.
COPYRIGHT = [
    "<!--",
    " Copyright 2026 FlagOS Contributors",
    "",
    " Licensed under the Apache License, Version 2.0 (the \"License\");",
    " you may not use this file except in compliance with the License.",
    " You may obtain a copy of the License at",
    "",
    "     http://www.apache.org/licenses/LICENSE-2.0",
    "",
    " Unless required by applicable law or agreed to in writing, software",
    " distributed under the License is distributed on an \"AS IS\" BASIS,",
    " WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.",
    " See the License for the specific language governing permissions and",
    " limitations under the License.",
    "-->",
]


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


def _prerequisites(entry: dict, s: dict, web: bool) -> list[str]:
    """Prerequisites section shared by base and runtime: arch, chip models,
    host driver, container toolkit (with optional tooltip on the web)."""
    base = entry["base"]
    lines = [f"## {s['prerequisites']}", ""]
    lines.append(f"- **{s['architecture']}:** {base.get('arch', '')}")
    hw = base.get("hardware") or []
    if hw:
        lines.append(f"- **{s['chip_models']}:** {', '.join(hw)}")
    drv = base.get("driver") or ""
    if drv:
        lines.append(f"- **{s['host_driver']}:** {drv}")
    toolkit = entry.get("run_prereq") or ""
    if toolkit:
        has_raw = any(t["kind"] in ("raw", "generic") for t in (entry.get("launch") or []))
        if has_raw:
            if web:
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
    return lines


def _launch(entry: dict, s: dict, image: str) -> list[str]:
    """Launch section: one tier per block, substituting the given image name."""
    tiers = entry.get("launch") or []
    both = any(t["kind"] == "toolkit" for t in tiers) and any(t["kind"] == "raw" for t in tiers)
    lines = []
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
    return lines


def _verify(entry: dict, s: dict) -> list[str]:
    """Verify section: command to run inside the launched container."""
    verify = entry.get("verify")
    lines = []
    if verify:
        lines += [f"## {s['verify']}", ""]
        lines += [s["verify_note"], ""]
        lines += ["```bash", verify, "```", ""]
    return lines


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

    # Hugo front matter — web flavor only.
    if web:
        # Apache 2.0 copyright header (only for web — Harbor can't parse HTML comments).
        lines += COPYRIGHT
        lines += ["---", f'title: "{name}"', "---", ""]

    # ── Prerequisites (shared with runtime) ──
    lines += _prerequisites(entry, s, web)

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

    # ── Environment (base image env vars) ──
    env = base.get("env") or {}
    if env:
        lines += [f"## {s['environment']}", ""]
        for k, v in env.items():
            lines.append(f"- `{k}={v}`")
        lines.append("")

    # ── Launch (shared with runtime) ──
    lines += _launch(entry, s, base["image"])

    # ── Verify (shared with runtime) ──
    lines += _verify(entry, s)

    return "\n".join(lines).rstrip() + "\n"


def render_runtime(entry: dict, lang: str = "en", flavor: str = "web") -> str:
    """Compose the runtime-image description markdown for one backend.

    Same two-flavor model as render(): ``"web"`` for the Hugo site (with
    front matter and tooltip) and ``"plain"`` for the in-repo readme +
    Harbor repository description.
    """
    s = STRINGS[lang]
    web = flavor == "web"
    name = entry["name"]
    base = entry["base"]
    runtime = entry["runtime"]
    lines: list[str] = []

    # Hugo front matter — web flavor only.
    if web:
        # Apache 2.0 copyright header (only for web — Harbor can't parse HTML comments).
        lines += COPYRIGHT
        lines += ["---", f'title: "{name}"', "---", ""]

    # ── Prerequisites (same as base page — inherited from base image) ──
    lines += _prerequisites(entry, s, web)

    # ── Image contents (base image ref + Python + major packages) ──
    lines += [f"## {s['image_contents']}", ""]

    if base.get("image"):
        lines += [f"### {s['base_image_ref']}", "", f"`{base['image']}`", ""]

    python_ver = runtime.get("python", "")
    if python_ver:
        lines += [f"### {s['python_version']}", "", python_ver, ""]

    packages = runtime.get("packages") or []
    if packages:
        lines += [f"### {s['major_packages']}", ""]
        has_muted = any(p.get("muted") for p in packages)
        for p in packages:
            pkg = p["pkg"]
            if p.get("muted"):
                if web:
                    lines.append(f'- <span class="muted"><code class="plain">{pkg}</code></span>')
                else:
                    lines.append(f"- `{pkg}` *(fallback)*")
            else:
                lines.append(f"- `{pkg}`")
        if has_muted:
            if web:
                lines += ["", f'<p class="muted"><em>{s["fallback_note"]}</em></p>']
            else:
                lines += ["", f"*{s['fallback_note']}*"]
        lines.append("")

    # ── Environment (runtime env vars) ──
    env = runtime.get("env") or {}
    if env:
        lines += [f"## {s['environment']}", ""]
        for k, v in env.items():
            lines.append(f"- `{k}={v}`")
        lines.append("")

    # ── Launch (runtime image name for launch commands) ──
    lines += _launch(entry, s, runtime["image"])

    # ── Verify ──
    lines += _verify(entry, s)

    return "\n".join(lines).rstrip() + "\n"


def main():
    root = repo_root()
    images = yaml.safe_load((root / "docs" / "data" / "images.yaml").read_text())
    backends = {b["name"]: b for b in images.get("backends", [])}

    vdir = os.environ.get("VERSIONS_DIR")
    versions_dir = Path(vdir).resolve() if vdir else None

    requested = sys.argv[1:]
    if requested:
        # Spot-check to stdout: every requested backend, every language, every
        # layer — so a single-backend check never silently covers just one layer.
        for name in requested:
            if name not in backends:
                sys.exit(f"Error: '{name}' not in images.yaml")
            versions = load_versions(versions_dir, name)
            for lang in LANGS:
                print(render(backends[name], versions, lang, "web"))
            print(render(backends[name], versions, "en", "plain"))
            for lang in LANGS:
                print(render_runtime(backends[name], lang, "web"))
            print(render_runtime(backends[name], "en", "plain"))
        return

    # ── Base images ──────────────────────────────────────────────
    total = 0

    # Base web flavor: docs/content/{en,zh-cn}/base/
    for lang in LANGS:
        out_dir = root / "docs" / "content" / lang / "base"
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, entry in backends.items():
            md = render(entry, load_versions(versions_dir, name), lang, "web")
            (out_dir / f"{name}.md").write_text(md)
            total += 1
        print(f"Wrote {len(backends)} {lang} base web pages to {out_dir}")

    # Base plain flavor: base/<name>.md
    base_dir = root / "base"
    for name, entry in backends.items():
        md = render(entry, load_versions(versions_dir, name), "en", "plain")
        (base_dir / f"{name}.md").write_text(md)
    print(f"Wrote {len(backends)} base plain readmes to {base_dir}")

    # ── Runtime images ───────────────────────────────────────────
    # Runtime web flavor: docs/content/{en,zh-cn}/runtime/
    for lang in LANGS:
        out_dir = root / "docs" / "content" / lang / "runtime"
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, entry in backends.items():
            md = render_runtime(entry, lang, "web")
            (out_dir / f"{name}.md").write_text(md)
            total += 1
        print(f"Wrote {len(backends)} {lang} runtime web pages to {out_dir}")

    # Runtime plain flavor: runtime/<name>.md
    runtime_dir = root / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    for name, entry in backends.items():
        md = render_runtime(entry, "en", "plain")
        (runtime_dir / f"{name}.md").write_text(md)
    print(f"Wrote {len(backends)} runtime plain readmes to {runtime_dir}")
    print(f"Total: {total + len(backends)} descriptions")


if __name__ == "__main__":
    main()
