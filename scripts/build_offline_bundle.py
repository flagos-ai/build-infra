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

from __future__ import annotations

"""Build the FlagOS offline one-click installer bundle (FEP-0139).

Reads configs.yaml (runtime layer) and packaging/<app>/app-versions.yaml (app
layer) — the same resolution logic scripts/build_runtime.py and the app
Containerfile use — then gathers the full wheel closure with `pip download`
against the internal indexes, stages a hermetic CPython + uv, and assembles a
self-contained tarball that installs offline:

    python scripts/build_offline_bundle.py vllm nvidia-cuda12.8
    python scripts/build_offline_bundle.py vllm nvidia-cuda12.8 --push

The tarball (dist/flagos-vllm-nvidia-cuda12.8-2.3.0.tar.gz) contains
scripts/offline/install.sh (filled) plus the payload. The install never touches
the network: `pip install --no-index --find-links wheelhouse/`. One bundle
carries every version in app-versions.yaml; `install.sh --vllm-version <ver>`
installs exactly one.

The downloads run under the backend's own CPython (the same managed
standalone CPython the runtime Containerfile installs), NOT the build host's
interpreter: a host python 3.10 would otherwise fetch cp310 wheels for a
backend pinned to 3.12. Index order per step mirrors the Containerfile
(vendor last for runtime deps/compilers, vendor first for flag_gems and the
app layer), so the wheel set — and the MANIFEST source per wheel — matches
what the images install.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_runtime import load_yaml, resolve_backend, resolve_build_args

FILESTORE = "https://resource.flagos.net/repository/flagos-filestore"
UV_VERSION = "0.11.30"
UV_PYTHON_MIRROR = f"{FILESTORE}/uv-python"
# Seed packages the venv needs before any requirements file can install
# (mirrors `uv venv --seed` in the runtime Containerfile).
SEED_REQS = ["pip", "setuptools", "wheel"]


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def host_arch() -> str:
    """uname -m spelling the filestore uv tarball uses (x86_64 / aarch64).

    The bundle build runs on the target-platform runner (self-hosted, on the
    vendor hardware — same assumption every image build in this repo makes), so
    the host arch IS the target arch; `pip download` resolves natively.
    """
    m = platform.machine()
    return {"x86_64": "x86_64", "amd64": "x86_64",
            "aarch64": "aarch64", "arm64": "aarch64"}.get(m, m)


def load_app_versions(app: str) -> dict:
    """packaging/<app>/app-versions.yaml → {"0.24.0": {"vllm": ..., "plugin": ...}}."""
    path = repo_root() / "packaging" / app / "app-versions.yaml"
    if not path.exists():
        sys.exit(f"Error: {path} not found (the recorded app-version pins)")
    return (load_yaml(path) or {}).get("versions") or {}


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        sys.exit(f"command failed ({r.returncode}): {' '.join(str(c) for c in cmd)}")
    return r


def download(url: str, dest: Path, name: str) -> None:
    print(f"==> fetching {name} from filestore")
    run(["curl", "-fsSL", "--retry", "3", "-o", str(dest), url])


def stage_uv(stage: Path) -> Path:
    """Download the filestore uv, extract to stage/python/, return the uv binary."""
    pydir = stage / "python"
    pydir.mkdir(parents=True, exist_ok=True)
    tarball = stage / f"uv-{host_arch()}-{UV_VERSION}-linux-gnu.tar.gz"
    download(f"{FILESTORE}/utils/uv-{host_arch()}-{UV_VERSION}-linux-gnu.tar.gz",
             tarball, "uv")
    # --strip-components=1: the tarball's top dir holds `uv` (+ LICENSE).
    run(["tar", "xzf", str(tarball), "-C", str(pydir), "--strip-components=1"])
    tarball.unlink()
    uv = pydir / "uv"
    if not uv.exists():
        sys.exit(f"Error: {uv} not found after extraction")
    return uv


def stage_cpython(uv: Path, python_version: str, stage: Path) -> tuple[Path, str]:
    """uv-install the standalone CPython, tar it into stage/python/.

    Returns (cpython_dir, tarball_name). The tree is also used to create the
    download venv (build_venv), so the wheels fetched are for the backend's
    own CPython version.
    """
    env = dict(os.environ)
    env["UV_PYTHON_INSTALL_MIRROR"] = UV_PYTHON_MIRROR
    run([str(uv), "python", "install", python_version,
         "--python-preference", "only-managed", "-q"], env=env)

    share = Path.home() / ".local" / "share" / "uv" / "python"
    matches = sorted(share.glob(f"cpython-{python_version}-linux-*-gnu"))
    if not matches:
        sys.exit(f"Error: uv installed no cpython-{python_version} tree under {share}")
    cpython_dir = matches[0]

    tarball_name = f"{cpython_dir.name}.tar.gz"
    pydir = stage / "python"
    pydir.mkdir(parents=True, exist_ok=True)
    run(["tar", "czf", str(pydir / tarball_name), "-C", str(cpython_dir.parent),
         cpython_dir.name])
    return cpython_dir, tarball_name


def build_venv(uv: Path, cpython_dir: Path, mirror: str) -> Path:
    """Create a throwaway download venv from the managed CPython; return its pip."""
    bv = Path(tempfile.mkdtemp(prefix="flagos-bldvenv-"))
    env = dict(os.environ)
    env["UV_DEFAULT_INDEX"] = mirror
    env["UV_HTTP_TIMEOUT"] = "120"
    run([str(uv), "venv", str(bv), "--python", str(cpython_dir / "bin" / "python3"),
         "--seed", "--relocatable"], env=env)
    pip = bv / "bin" / "pip"
    if not pip.exists():
        sys.exit(f"Error: {pip} not found after venv creation")
    return pip


def pip_download(pip: Path, reqs: list[str], dest: Path, report: Path,
                 index: str, extras: list[str], *, pre: bool) -> None:
    """pip download one closure into dest; --report captures per-wheel source.

    index is the primary --index-url; extras become --extra-index-url entries
    AFTER it (so `extras` listed last win exact-version ties, matching the
    Containerfile's "vendor last" rule where the Containerfile puts the vendor
    last).
    """
    if not reqs:
        return
    cmd = [str(pip), "download", "--no-cache-dir", "--dest", str(dest),
           "--report", str(report)]
    if pre:
        cmd.append("--pre")
    cmd += ["--index-url", index]
    for e in extras:
        cmd += ["--extra-index-url", e]
    cmd += ["--trusted-host", "resource.flagos.net"]
    cmd += reqs
    run(cmd)


def merge_reports(reports: list[Path]) -> dict:
    """filename -> source index URL, merged from several pip download reports."""
    merged: dict[str, str] = {}
    for rep in reports:
        if not rep.exists():
            continue
        data = json.loads(rep.read_text())
        for item in data.get("install", []):
            info = item.get("download_info") or {}
            url = info.get("url") or ""
            if not url.endswith(".whl"):
                continue
            merged[url.rsplit("/", 1)[-1]] = url
    return merged


def source_index(url: str) -> str:
    """Turn a concrete file URL into the repository name it came from."""
    if "repository/" not in url:
        return url.split("/")[2] if "://" in url else url
    return url.split("repository/", 1)[1].split("/", 1)[0]


def write_manifest(dest: Path, wheels: list[Path], sources: dict[str, str]) -> None:
    lines = [
        "# Offline bundle MANIFEST — wheel filename, sha256, source index.",
        f"# {len(wheels)} wheels.",
    ]
    for whl in sorted(wheels):
        sha = hashlib.sha256(whl.read_bytes()).hexdigest()
        src = sources.get(whl.name, "unknown")
        lines.append(f"{whl.name}\t{sha}\t{source_index(src)}")
    (dest / "MANIFEST").write_text("\n".join(lines) + "\n")


def fill_template(template: Path, dest: Path, mapping: dict) -> None:
    text = template.read_text()
    for key, val in mapping.items():
        text = text.replace(f"@{key}@", val)
    leftover = [line for line in text.splitlines() if "@" in line]
    if leftover:
        sys.exit("Error: unreplaced @TOKEN@ in install.sh:\n" + "\n".join(leftover))
    out = dest / "install.sh"
    out.write_text(text)
    out.chmod(0o755)


def serialize_env(env_lines: str, extra: list[str]) -> str:
    """Join RUNTIME_ENV/APP_ENV lines with any extra KEY=value pairs."""
    lines = [ln for ln in env_lines.splitlines() if ln.strip()]
    lines += [ln for ln in extra if ln.strip()]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the FlagOS offline one-click installer bundle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("app", help="App name (vllm)")
    parser.add_argument("backend", help="Backend key (nvidia-cuda12.8)")
    parser.add_argument("--push", action="store_true",
                        help="Upload the tarball to flagos-filestore/offline/")
    parser.add_argument("--flaggems", default="",
                        help="FlagGems wheel version override (default: configs.yaml)")
    parser.add_argument("--out-dir", default=str(repo_root() / "dist"),
                        help="Where to write the tarball")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the resolved pins and stop before any download")
    args = parser.parse_args()

    root = repo_root()
    configs = load_yaml(root / "configs.yaml")
    backend_info, vendor, backend = resolve_backend(args.backend, configs)

    # Runtime layer — reuse build_runtime's resolver so bundle == image.
    build_args = resolve_build_args(backend_info, vendor, backend, configs, root)
    deps = build_args["DEPS"].split()
    prereqs = build_args["RUNTIME_PREREQS"].split()
    flagtree_pkg = build_args["FLAGTREE_PKG"]
    triton_pkg = build_args["TRITON_PKG"]
    triton_extra = build_args["TRITON_EXTRA_PKGS"].split()
    flagos_pypi = build_args["FLAGOS_PYPI"]
    daily_pypi = build_args["DAILY_PYPI"]
    extra_pypi = build_args["EXTRA_PYPI"]
    python_version = build_args["PYTHON_VERSION"]
    runtime_env = build_args["RUNTIME_ENV"]
    flaggems = args.flaggems or configs.get("flaggems", "")
    version = configs["version"]

    # App layer — recorded pins (packaging/<app>/app-versions.yaml).
    versions = load_app_versions(args.app)
    app_deps = backend_info.get("deps_app") or {}
    # env.app keys are the bare app name (vllm), not the versioned key.
    app_env_map = ((backend_info.get("env") or {}).get("app") or {}).get(args.app, {})
    app_env = "\n".join(f"{k}={v}" for k, v in app_env_map.items())
    # The app image sets VLLM_PLUGINS=fl as image ENV; bare metal gets it in
    # app_env.sh so a plain `vllm-serve` works identically.
    app_env = serialize_env(app_env, ["VLLM_PLUGINS=fl"])

    # Runtime top-level pins (requirements.txt) — the shared layer, installed
    # into site-packages. Compilers are NOT here: install.sh puts them in side
    # dirs via the compiler pins below.
    runtime_top = deps + prereqs + [f"flag_gems=={flaggems}"]
    # Compiler side-dir pins (downloaded for the wheelhouse, installed to
    # $PREFIX/opt/*, never into site-packages).
    compiler_reqs = ([flagtree_pkg] if flagtree_pkg else []) + \
                    ([triton_pkg] if triton_pkg else []) + triton_extra

    # Per-version app delta (requirements-<version>.txt).
    deltas: dict[str, list[str]] = {}
    for ver, pins in versions.items():
        key = f"{args.app}{ver}"
        if key not in app_deps:
            print(f"note: backend {args.backend} has no deps_app key '{key}' — "
                  f"skipping {args.app} {ver} (key presence = supported)")
            continue
        deltas[ver] = [f"vllm=={pins['vllm']}", f"vllm-plugin-fl=={pins['plugin']}"] \
            + list(app_deps[key])
    if not deltas:
        sys.exit(f"Error: no supported {args.app} versions for backend {args.backend}")

    bundle_name = f"flagos-{args.app}-{vendor}-{backend}-{version}"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tarball = out_dir / f"{bundle_name}.tar.gz"

    if args.dry_run:
        print(f"bundle:    {bundle_name}")
        print(f"tarball:   {tarball}")
        print(f"backend:   {vendor}-{backend}  python {python_version}  "
              f"(downloads resolve natively on the target runner)")
        print(f"indexes:   primary/extra per step (mirror-first for deps/compilers, "
              f"vendor-first for flag_gems + app)")
        print(f"  flagos:  {flagos_pypi}")
        print(f"  daily:   {daily_pypi}")
        print(f"  mirror:  {extra_pypi}")
        print(f"runtime:   {' '.join(runtime_top)}")
        print(f"compilers: {' '.join(compiler_reqs) or '(none)'}")
        for ver in sorted(deltas):
            print(f"  {args.app} {ver}: {' '.join(deltas[ver])}")
        return

    # ── Stage into a temp dir, then tar ─────────────────────────────────────
    stage = Path(tempfile.mkdtemp(prefix="flagos-bundle-"))
    stage_root = stage / bundle_name
    (stage_root / "wheelhouse").mkdir(parents=True, exist_ok=True)
    wheelhouse = stage_root / "wheelhouse"

    # Hermetic CPython + uv FIRST: the download venv must be the backend's own
    # CPython version, so `pip download` fetches that version's wheels.
    print("==> staging hermetic CPython + uv")
    uv = stage_uv(stage)
    cpython_dir, cpython_tarball = stage_cpython(uv, python_version, stage)
    pip = build_venv(uv, cpython_dir, extra_pypi)

    reports: list[Path] = []

    # Index order mirrors the Containerfile:
    #   deps/prereqs + compilers: mirror primary, vendor last
    #   flag_gems:                vendor primary, daily+mirror extra, --pre
    #   app delta:                vendor primary, mirror extra
    print("==> downloading runtime deps + prereqs (mirror first, vendor last)")
    rep = stage / "runtime-report.json"
    pip_download(pip, deps + prereqs, wheelhouse, rep, extra_pypi, [flagos_pypi], pre=False)
    reports.append(rep)

    print("==> downloading flag_gems (vendor first, --pre)")
    rep = stage / "flaggems-report.json"
    pip_download(pip, [f"flag_gems=={flaggems}"], wheelhouse, rep, flagos_pypi,
                 [e for e in (daily_pypi, extra_pypi) if e], pre=True)
    reports.append(rep)

    print("==> downloading compiler wheels (mirror first, vendor last)")
    rep = stage / "compiler-report.json"
    pip_download(pip, compiler_reqs, wheelhouse, rep, extra_pypi, [flagos_pypi], pre=False)
    reports.append(rep)

    print("==> downloading seed packages (pip/setuptools/wheel)")
    rep = stage / "seed-report.json"
    pip_download(pip, SEED_REQS, wheelhouse, rep, extra_pypi, [], pre=False)
    reports.append(rep)

    for ver in sorted(deltas):
        print(f"==> downloading {args.app} {ver} delta (vendor first)")
        rep = stage / f"app-{ver}-report.json"
        pip_download(pip, deltas[ver], wheelhouse, rep, flagos_pypi, [extra_pypi], pre=False)
        reports.append(rep)

    # ── requirements files ──────────────────────────────────────────────────
    (stage_root / "requirements.txt").write_text("\n".join(runtime_top) + "\n")
    for ver in sorted(deltas):
        (stage_root / f"requirements-{ver}.txt").write_text("\n".join(deltas[ver]) + "\n")

    # ── MANIFEST ────────────────────────────────────────────────────────────
    sources = merge_reports(reports)
    write_manifest(stage_root, sorted(wheelhouse.glob("*.whl")), sources)

    # ── install.sh (filled template) ────────────────────────────────────────
    template = Path(__file__).resolve().parent / "offline" / "install.sh"
    default_compiler = "flagtree" if flagtree_pkg else ("triton" if triton_pkg else "none")
    fill_template(template, stage_root, {
        "APP": args.app,
        "VENDOR": vendor,
        "BACKEND": backend,
        "VERSION": version,
        "PYTHON_VERSION": python_version,
        "CPYTHON_TARBALL": cpython_tarball,
        "DEFAULT_COMPILER": default_compiler,
        "FLAGTREE_PIN": flagtree_pkg,
        "TRITON_PIN": triton_pkg,
        "TRITON_EXTRA": " ".join(triton_extra),
        "APP_ENV": app_env,
        "RUNTIME_ENV": runtime_env,
        "SDK_NOTE": "NVIDIA driver only — torch+cu128 bundles the CUDA runtime",
    })

    # ── assemble the tarball ────────────────────────────────────────────────
    print(f"==> assembling {tarball}")
    with tarfile.open(tarball, "w:gz") as tf:
        tf.add(stage_root, arcname=bundle_name)
    shutil.rmtree(stage)

    print(f"Done: {tarball} ({tarball.stat().st_size / 1e6:.0f} MB)")

    if args.push:
        token = os.environ.get("NEXUS_TOKEN", "")
        if not token:
            sys.exit("Error: --push needs NEXUS_TOKEN in the environment")
        url = f"{FILESTORE}/offline/{tarball.name}"
        print(f"==> uploading to {url}")
        run(["curl", "-f", "-u", token, "--upload-file", str(tarball), url])


if __name__ == "__main__":
    main()
