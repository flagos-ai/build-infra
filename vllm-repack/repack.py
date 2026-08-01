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

"""
Repack a Python wheel by removing unwanted Requires-Dist entries from its
METADATA, recording every change in a .deps-manifest.yaml for traceability.

Usage:
    python repack.py /path/to/vllm-0.25.1-xxx.whl
    python repack.py --extra-indexes https://... vllm.whl

By default the script also recursively audits every retained dependency:
any dep whose own METADATA declares torch / triton / nvidia is repacked
as well (stripping those declarations) so that pip won't pull a
conflicting version over the vendor-provided one.  All output lands in
output/ — a single directory ready for upload to a vendor PyPI.

Pass --no-recurse to skip this and only repack the top-level wheel.

Design:
    - Only blacklisted deps (torch_chain, cuda_only, orphaned) are stripped
      from the top-level wheel's Requires-Dist.
    - Indirect deps that declare torch/triton are discovered automatically
      by pip-resolving the repacked wheel's retained deps, downloading each,
      and inspecting its METADATA.  No manual "also_repack" list.
    - No version suffix — pip + --extra-index-url to vendor PyPI ensures the
      repacked wheel is used, without uv-style auto-upgrade behavior.
    - The default download index is https://mirrors.aliyun.com/pypi/simple/
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
CACHE_DIR = SCRIPT_DIR / "cache"
OUTPUT_DIR = SCRIPT_DIR / "output"
VERSION_SUFFIX = ""


# ── helpers ────────────────────────────────────────────────────────────


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dirs():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── METADATA parsing ────────────────────────────────────────────────────


_REQUIRES_DIST_RE = re.compile(r"^Requires-Dist:\s*(.+)$", re.IGNORECASE)
_NAME_RE = re.compile(r"^([A-Za-z0-9_.-]+)")


def parse_requires_dist(metadata_text: str) -> list[dict]:
    """Return list of {raw, name, extra} for each Requires-Dist line."""
    results = []
    for line in metadata_text.splitlines():
        m = _REQUIRES_DIST_RE.match(line)
        if not m:
            continue
        raw = m.group(1).strip()
        name_match = _NAME_RE.match(raw)
        name = name_match.group(1) if name_match else raw
        # Detect extras marker e.g. humming-kernels[cu13]==0.1.10
        extra = None
        em = re.match(r"^[^[]+\[([^\]]+)\]", raw)
        if em:
            extra = em.group(1)
        results.append({"raw": raw, "name": name, "extra": extra})
    return results


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _strip_requires_dist_lines(metadata_text: str, names_to_remove: set[str]) -> str:
    """Remove lines whose package name (case-insensitive, normalised) is in the set."""
    keep: list[str] = []
    for line in metadata_text.splitlines():
        m = _REQUIRES_DIST_RE.match(line)
        if m:
            name = _NAME_RE.match(m.group(1).strip())
            if name and _normalize(name.group(1)) in names_to_remove:
                continue
        keep.append(line)
    return "\n".join(keep) + "\n"


_METADATA_VERSION_RE = re.compile(r"^Metadata-Version:\s*.+$", re.MULTILINE | re.IGNORECASE)
_LICENSE_EXPRESSION_RE = re.compile(r"^License-Expression:\s*.+$", re.MULTILINE | re.IGNORECASE)
_LICENSE_FILE_RE = re.compile(r"^License-File:\s*.+\n?", re.MULTILINE | re.IGNORECASE)
_DYNAMIC_RE = re.compile(r"^Dynamic:\s*.+\n?", re.MULTILINE | re.IGNORECASE)
_VERSION_LOCAL_RE = re.compile(r"^Version:\s*(.+?)\+.+$", re.MULTILINE | re.IGNORECASE)
_WHEEL_TAG_RE = re.compile(r"^Tag:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_VLLM_PLATFORM_TAG = "cp38-abi3-manylinux_2_35_x86_64"


def _downgrade_metadata_version(text: str) -> str:
    """Rewrite Metadata-Version 2.4 → 2.2, converting 2.4-only fields.

    Core Metadata 2.4 (PEP 639) introduced License-Expression and License-File,
    and bumped the Dynamic list. Nexus rejects 2.4 wheels, so we downgrade to
    2.2 by rewriting the version line and converting license fields.
    """
    # Check if already 2.2 or earlier
    m = re.search(r"^Metadata-Version:\s*([\d.]+)", text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return text
    ver = m.group(1)
    if float(ver) < 2.3:
        return text  # already 2.2 or older — nothing to do

    # Extract License-Expression value (we'll convert it to License:)
    license_text = None
    mle = re.search(r"^License-Expression:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    if mle:
        license_text = mle.group(1).strip()

    # 1. Rewrite Metadata-Version
    text = _METADATA_VERSION_RE.sub("Metadata-Version: 2.2", text)

    # 2. Replace License-Expression with License (2.2 format)
    if license_text:
        text = _LICENSE_EXPRESSION_RE.sub(f"License: {license_text}", text)

    # 3. Remove License-File (not supported in 2.2)
    text = _LICENSE_FILE_RE.sub("", text)

    # 4. Remove Dynamic fields (2.2 Dynamic list is incomplete for 2.4-made wheels)
    text = _DYNAMIC_RE.sub("", text)

    # 5. Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


def _strip_local_version(text: str) -> str:
    """Strip local version suffix (+xxx) from the Version: line in METADATA.

    e.g. 'Version: 0.20.2+empty' → 'Version: 0.20.2'
    """
    return _VERSION_LOCAL_RE.sub(r"Version: \1", text)


def _add_version_suffix(text: str, suffix: str) -> str:
    """Add local version suffix (+suffix) to the Version: line in METADATA.

    e.g. 'Version: 0.20.2' -> 'Version: 0.20.2+flagos'
    """
    # Match the Version line and extract just the version number
    match = re.search(r'^Version:\s*([^\s+]+)', text, re.MULTILINE | re.IGNORECASE)
    if match:
        version = match.group(1).strip()
        # Remove any existing suffix first
        version = re.sub(r'\+.*$', '', version)
        new_version = f"{version}+{suffix}"
        # Replace the entire Version line
        text = re.sub(r'^(Version:\s*)[^\s+]+', rf'\g<1>{new_version}', text,
                      flags=re.MULTILINE | re.IGNORECASE, count=1)
    return text


def _read_wheel_file(whl_path: Path, dist_info_dir: str) -> str:
    """Read the WHEEL file from a wheel's .dist-info directory."""
    with zipfile.ZipFile(whl_path) as z:
        return z.read(f"{dist_info_dir}/WHEEL").decode("utf-8")


def _get_wheel_tag(wheel_text: str) -> str:
    """Extract the Tag value from a WHEEL file."""
    m = _WHEEL_TAG_RE.search(wheel_text)
    return m.group(1).strip() if m else "py3-none-any"


def _rewrite_wheel_tag(wheel_text: str, new_tag: str) -> str:
    """Replace the Tag line in a WHEEL file."""
    return _WHEEL_TAG_RE.sub(f"Tag: {new_tag}", wheel_text)


def _extract_name_version(requires_dist_line: str):
    """Return (name, version_spec_no_marker) from a raw Requires-Dist string.

    Strips extras like [cu13] and environment markers like ; platform_system == ... .
    """
    raw = requires_dist_line.strip()
    # Split off environment marker
    pkg_spec = raw.split(";", 1)[0].strip()

    # Strip extras brackets e.g. humming-kernels[cu13]==0.1.10 → humming-kernels==0.1.10
    pkg_spec = re.sub(r"\[.*\]", "", pkg_spec)

    m = _NAME_RE.match(pkg_spec)
    name = m.group(1).strip() if m else pkg_spec

    # Version spec is everything after the name
    version_spec = pkg_spec[len(name):].strip()

    return name, version_spec


# ── classification ─────────────────────────────────────────────────────


def classify(rd: dict, config: dict):
    """Return one of: 'torch_chain', 'cuda_only', 'orphaned', 'keep'."""
    nn = _normalize(rd["name"])
    for item in config.get("remove_torch_chain", []):
        if _normalize(item) == nn:
            return "torch_chain"
    for item in config.get("remove_cuda_only", []):
        if _normalize(item) == nn:
            return "cuda_only"
    for item in config.get("remove_orphaned", []):
        if _normalize(item) == nn:
            return "orphaned"
    return "keep"


# ── wheel I/O ──────────────────────────────────────────────────────────


def read_wheel_metadata(whl_path: Path) -> tuple[str, str]:
    """Return (metadata_text, dist_info_dir_name)."""
    with zipfile.ZipFile(whl_path) as z:
        for name in z.namelist():
            if name.endswith(".dist-info/METADATA"):
                return z.read(name).decode("utf-8"), name.split("/")[0]
    raise ValueError(f"No .dist-info/METADATA found in {whl_path}")


def rewrite_wheel(src: Path, dst: Path, metadata_text: str, dist_info_dir: str,
                  old_dist_info_dir=None, wheel_text=None):
    """Copy src → dst, replacing METADATA content. Handles src == dst safely.

    When old_dist_info_dir differs from dist_info_dir (e.g. stripping the +empty
    local version suffix from the directory name), files are transparently
    relocated.  When wheel_text is provided, the WHEEL file is also replaced.
    """
    if old_dist_info_dir is None:
        old_dist_info_dir = dist_info_dir
    if src.resolve() == dst.resolve():
        fd, tmpname = tempfile.mkstemp(dir=dst.parent, suffix=".tmp")
        os.close(fd)
        tmp = Path(tmpname)
        _rewrite_wheel_impl(src, tmp, metadata_text, dist_info_dir,
                           old_dist_info_dir, wheel_text)
        tmp.replace(dst)
    else:
        _rewrite_wheel_impl(src, dst, metadata_text, dist_info_dir,
                           old_dist_info_dir, wheel_text)


def _rewrite_wheel_impl(src: Path, dst: Path, metadata_text: str,
                         dist_info_dir: str, old_dist_info_dir: str,
                         wheel_text=None):
    rename_dir = old_dist_info_dir != dist_info_dir
    with zipfile.ZipFile(src) as zin:
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                old_path = item.filename
                if rename_dir and old_path.startswith(f"{old_dist_info_dir}/"):
                    new_path = f"{dist_info_dir}/{old_path[len(old_dist_info_dir) + 1:]}"
                    item = zipfile.ZipInfo(new_path, item.date_time)
                if old_path == f"{old_dist_info_dir}/METADATA":
                    zout.writestr(item, metadata_text)
                elif wheel_text is not None and old_path == f"{old_dist_info_dir}/WHEEL":
                    zout.writestr(item, wheel_text)
                else:
                    zout.writestr(item, data)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def wheel_name_to_filename(name: str, version: str, tag: str = "py3-none-any") -> str:
    """Convert package name + version to a wheel filename.
    When repacking an empty-build wheel, pass the platform tag to avoid
    pip preferring the upstream wheel over the repacked one."""
    safe_name = re.sub(r"[-_.]+", "_", name)
    return f"{safe_name}-{version}-{tag}.whl"


# ── dependency download helpers ─────────────────────────────────────────



def _is_valid_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return len(z.namelist()) > 0 and z.testzip() is None
    except (zipfile.BadZipFile, OSError):
        return False

_JSON_HEADERS = {"Accept": "application/json"}



def _version_matches(version: str, spec: str) -> bool:
    """Lightweight PEP 440 version matching.  Handles ==, >=, <=, !=, <, >.
    Returns True if `version` satisfies `spec`.
    """
    spec = spec.strip()
    v = _parse_version(version)

    # Split on comma for compound specs like '<1.0.0,>=0.2.1'
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if not parts:
        return True

    for part in parts:
        # Support whitespace-separated compound as well: '>=0.2.1,<1.0.0'
        sub_parts = [s.strip() for s in part.split() if s.strip()]
        for sp in sub_parts:
            op, target = _parse_spec_part(sp)
            if op is None:
                return False
            tv = _parse_version(target)
            if not _check_op(v, op, tv):
                return False
    return True


def _parse_version(v_str: str):
    """Parse a version string into a tuple of ints for comparison."""
    # Strip any epoch prefix
    if "!" in v_str:
        v_str = v_str.split("!", 1)[1]
    # Take only the release segment (before first pre/post/dev marker)
    release = v_str
    for sep in ("a", "b", "rc", ".post", ".dev", "+", "-"):
        idx = release.find(sep)
        if idx != -1:
            release = release[:idx]
    return tuple(int(x) for x in release.split(".") if x.isdigit())


def _parse_spec_part(spec: str) -> tuple[str | None, str]:
    """Parse a single version specifier into (operator, version)."""
    for op in ("!=", ">=", "<=", "==", ">", "<", "~="):
        if spec.startswith(op):
            return op, spec[len(op):]
    # Bare version is treated as ==
    return "==", spec


def _check_op(v1: tuple, op: str, v2: tuple) -> bool:
    if op == "==":
        return v1 == v2
    elif op == "!=":
        return v1 != v2
    elif op == ">=":
        return v1 >= v2
    elif op == "<=":
        return v1 <= v2
    elif op == ">":
        return v1 > v2
    elif op == "<":
        return v1 < v2
    elif op == "~=":
        # Compatible release: ~= X.Y means >= X.Y, == X.*
        return v1 >= v2 and v1[:len(v2) - 1] == v2[:len(v2) - 1]
    return False


def _resolve_pip_version(name: str, version_spec: str, extra_indexes: list[str]) -> str | None:
    """Resolve a version specifier to an exact version using pip download.

    Prefers vendor-packaged names (e.g. torch with +das suffix) by checking
    extra indexes first.
    """
    indexes = ([ei.rstrip("/") + "/" for ei in extra_indexes]
               + ["https://mirrors.aliyun.com/pypi/simple/"])

    pypi_name = re.sub(r"\[.*\]", "", name)
    for base_url in indexes:
        url = f"{base_url}{pypi_name}/json"
        try:
            req = urllib.request.Request(url, headers=_JSON_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            continue

        versions = list(data.get("releases", {}).keys())
        versions.sort(key=lambda v: [int(x) for x in re.findall(r"\d+", v)] or [0])
        spec = version_spec.strip()
        for v in reversed(versions):
            if _version_matches(v, spec):
                return v
    return None


def _download_dep_wheel(name: str, version: str, extra_indexes: list[str]) -> Path:
    """Download a dependency wheel at exact version.  Returns wheel path."""
    indexes = ([ei.rstrip("/") + "/" for ei in extra_indexes]
               + ["https://mirrors.aliyun.com/pypi/simple/"])

    pypi_name = re.sub(r"\[.*\]", "", name)

    # Try JSON API first
    for base_url in indexes:
        try:
            url = f"{base_url}{pypi_name}/{version}/json"
            req = urllib.request.Request(url, headers=_JSON_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            for entry in data.get("urls", []):
                if entry.get("packagetype") == "bdist_wheel":
                    whl_url = entry.get("url")
                    fn = entry.get("filename", "")
                    if whl_url:
                        dst = CACHE_DIR / fn
                        if dst.exists() and dst.stat().st_size > 1024 and _is_valid_zip(dst):
                            return dst
                        print(f"    downloading {fn} ...")
                        _download_url(whl_url, dst)
                        return dst
        except Exception:
            continue

    # Fallback: pip download
    spec = f"{pypi_name}=={version}"
    r = subprocess.run(
        [sys.executable, "-m", "pip", "download", "--no-deps",
         "--dest", str(CACHE_DIR), "--no-cache-dir",
         "-i", indexes[0], spec],
        check=False, capture_output=True, text=True,
    )
    if r.returncode == 0:
        # Pip normalises package names (PyJWT→pyjwt, etc.).  Match any
        # wheel whose filename contains the exact version.
        whls = sorted(
            [p for p in CACHE_DIR.glob("*.whl") if f"-{version}-" in p.name],
            key=lambda p: p.stat().st_size,
        )
        if whls:
            return whls[-1]

    raise RuntimeError(f"Could not download {name}=={version}")


def _download_url(url: str, dst: Path):
    """Download a URL to a local path, with validation."""
    import urllib.request as _ur
    try:
        with _ur.urlopen(url, timeout=120) as resp:
            with open(dst, "wb") as f:
                shutil.copyfileobj(resp, f)
    except Exception as e:
        if dst.exists():
            dst.unlink()
        raise
    if not _is_valid_zip(dst):
        dst.unlink()
        raise RuntimeError(f"Downloaded file is not a valid zip: {dst.name}")


# ── indirect dep resolution & repacking ────────────────────────────────


def resolve_dep_versions(meta_text: str, extra_indexes: list[str]) -> dict[str, str]:
    """Resolve every non-extra Requires-Dist to an exact version.

    Uses a single 'pip install --dry-run --report' call for all retained
    deps — one pip resolution instead of N, vastly faster.

    Returns {name: version} for each retained dep.  Deps that are already
    stripped (torch_chain, cuda_only, orphaned) are excluded.
    """
    config = load_config()
    all_rd = parse_requires_dist(meta_text)
    exclude = set()
    for cat in ("remove_torch_chain", "remove_cuda_only", "remove_orphaned"):
        for item in config.get(cat, []):
            exclude.add(_normalize(item))

    # Collect all retained deps' pip specs
    specs: list[str] = []
    for rd in all_rd:
        nn = _normalize(rd["name"])
        if nn in exclude:
            continue
        if rd["extra"] is not None:
            continue
        if "; extra" in rd["raw"]:
            continue

        spec = rd["raw"].split(";", 1)[0].strip()  # drop markers
        pkg_spec = re.sub(r"\[.*\]", "", spec)       # drop extras
        m = _NAME_RE.match(pkg_spec)
        if m:
            specs.append(spec)

    if not specs:
        return {}

    # Build pip index args
    idx_args: list[str] = []
    for ei in extra_indexes:
        idx_args += ["--extra-index-url", ei]
    idx_args += ["--index-url", "https://mirrors.aliyun.com/pypi/simple/"]

    resolved: dict[str, str] = {}
    _report_path = None
    try:
        import tempfile as _tf
        with _tf.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as _f:
            _report_path = _f.name
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--dry-run",
             "--report", _report_path]
            + idx_args + specs,
            check=False, capture_output=True, text=True, timeout=300,
        )
        if r.returncode == 0:
            with open(_report_path) as _f:
                report = json.load(_f)
            for item in report.get("install", []):
                m = item.get("metadata", {})
                resolved[m.get("name", "")] = m.get("version", "")
    except Exception:
        pass
    finally:
        if _report_path:
            try:
                Path(_report_path).unlink(missing_ok=True)
            except Exception:
                pass

    if resolved:
        print(f"  pip resolved {len(resolved)} deps in one pass")
    else:
        print(f"  WARNING: pip resolution returned empty, falling back to per-dep")
        # Fallback: resolve one-by-one
        for rd in all_rd:
            nn = _normalize(rd["name"])
            if nn in exclude:
                continue
            if rd["extra"] is not None:
                continue
            if "; extra" in rd["raw"]:
                continue

            spec = rd["raw"].split(";", 1)[0].strip()
            pkg_spec = re.sub(r"\[.*\]", "", spec)
            m = _NAME_RE.match(pkg_spec)
            if not m:
                continue
            v = _resolve_pip_version(rd["name"], pkg_spec[m.end():].strip() or "", extra_indexes)
            if v:
                resolved[rd["name"]] = v

    return resolved


def audit_dep_meta(name: str, version: str, extra_indexes: list[str]) -> dict | None:
    """Download a dep wheel and inspect its METADATA for torch/triton.

    Returns dict with keys: name, version, requires_dist, has_suspect_deps,
    suspect_deps — or None if download/read fails.
    """
    config = load_config()
    strip_set = {_normalize(x) for x in config.get("strip_from_indirect", [])}

    try:
        whl_path = _download_dep_wheel(name, version, extra_indexes)
    except Exception:
        print(f"    !! cannot download {name}=={version}")
        return None

    meta_text, _ = read_wheel_metadata(whl_path)
    all_rd = parse_requires_dist(meta_text)

    suspects = []
    for rd in all_rd:
        nn = _normalize(rd["name"])
        if "; extra" in rd["raw"]:
            continue
        if nn in strip_set:
            suspects.append(rd["raw"])

    return {
        "name": name,
        "version": version,
        "requires_dist": [rd["raw"] for rd in all_rd],
        "has_suspect_deps": len(suspects) > 0,
        "suspect_deps": suspects,
    }


def repack_dep(name: str, version: str, extra_indexes: list[str],
               visited: set[str] | None = None) -> tuple[Path, Path, list[tuple[str, str]]] | None:
    """Download and repack an indirect dep, stripping its torch/triton deps.

    Returns (output_wheel, manifest_path, sub_deps) or None if nothing to strip.
    sub_deps is list of (name, version) for all repacked sub-dependencies.
    """
    if visited is None:
        visited = set()

    config = load_config()
    strip_set = {_normalize(x) for x in config.get("strip_from_indirect", [])}

    print(f"  repack: {name}=={version}")

    try:
        whl_path = _download_dep_wheel(name, version, extra_indexes)
    except Exception:
        print(f"    !! cannot download {name}=={version}")
        return None

    meta_text, dist_info_dir = read_wheel_metadata(whl_path)
    all_rd = parse_requires_dist(meta_text)

    removed = []
    for rd in all_rd:
        nn = _normalize(rd["name"])
        if "; extra" in rd["raw"]:
            continue
        if nn in strip_set:
            removed.append(rd)
            print(f"    strip {rd['raw']}")

    # Recurse into this dep's own dependencies first
    # Even if this dep has nothing to strip, its sub-deps might
    key = f"{_normalize(name)}-{version}"
    visited.add(key)
    sub_repacked_deps: list[tuple[str, str]] = []

    # Resolve and repack sub-dependencies
    dep_versions = resolve_dep_versions(meta_text, extra_indexes)
    for dep_name, dep_version in sorted(dep_versions.items()):
        sub_key = f"{_normalize(dep_name)}-{dep_version}"
        if sub_key in visited:
            continue

        info = audit_dep_meta(dep_name, dep_version, extra_indexes)
        if info is None or not info["has_suspect_deps"]:
            continue

        print(f"\n    --- sub-dep: {dep_name}=={dep_version} ---")
        result = repack_dep(dep_name, dep_version, extra_indexes, visited)
        if result:
            _, _, sub_sub_deps = result
            sub_repacked_deps.append((dep_name, dep_version))
            sub_repacked_deps.extend(sub_sub_deps)

    # If nothing to strip and no sub-deps repacked, skip this package
    if not removed and not sub_repacked_deps:
        return None

    # Now update this dep's METADATA with +flagos versions of sub-deps
    new_meta = _strip_requires_dist_lines(meta_text, strip_set)
    new_meta = _downgrade_metadata_version(new_meta)

    # Update sub-dependency versions to +flagos
    if sub_repacked_deps:
        print(f"    updating sub-dep versions:")
        for dep_name, dep_version in sub_repacked_deps:
            # Use pattern that matches both hyphen and underscore variants
            name_pattern = re.escape(dep_name).replace(r'\-', '[-_]').replace('_', '[-_]')
            pattern = rf"(^{name_pattern}==){re.escape(dep_version)}(\s*;|\s*$)"
            replacement = rf"\g<1>{dep_version}+flagos\g<2>"
            new_meta, count = re.subn(pattern, replacement, new_meta, flags=re.MULTILINE | re.IGNORECASE)
            if count > 0:
                print(f"      {dep_name}=={dep_version} -> {dep_version}+flagos")
            else:
                print(f"      WARNING: could not update {dep_name}=={dep_version}")

    # Add +flagos suffix for this package
    new_meta = _add_version_suffix(new_meta, "flagos")
    print(f"    add version suffix: +flagos")

    # Update dist_info_dir to include +flagos suffix
    old_dist_info_dir = dist_info_dir
    if dist_info_dir.endswith(".dist-info"):
        base = dist_info_dir[:-len(".dist-info")]
        dist_info_dir = f"{base}+flagos.dist-info"

    # Write manifest
    safe_name = _normalize(name)
    manifest_path = OUTPUT_DIR / f"{safe_name}-{version}+flagos.deps-manifest.yaml"
    manifest_data = {
        "source_wheel": whl_path.name,
        "source_sha256": sha256_file(whl_path),
        "package": name,
        "version": f"{version}+flagos",
        "modified_at": datetime.now(timezone.utc).isoformat(),
        "all_requires_dist": [rd["raw"] for rd in all_rd],
        "removed": [rd["raw"] for rd in removed],
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # Rewrite wheel with updated metadata
    output_name = wheel_name_to_filename(name, f"{version}+flagos")
    output_path = OUTPUT_DIR / output_name
    rewrite_wheel(whl_path, output_path, new_meta, dist_info_dir,
                  old_dist_info_dir if old_dist_info_dir != dist_info_dir else None)

    whl_path.unlink()  # cleanup original

    return output_path, manifest_path, sub_repacked_deps


# ── recursive repack ───────────────────────────────────────────────────


def repack_recursive(repacked_meta_text: str, extra_indexes: list[str],
                     visited: set[str] | None = None):
    """Resolve retained deps, audit each, repack those with torch/triton, recurse.

    visited tracks packages already handled to avoid infinite recursion.
    Returns list of (name, version, output_wheel, manifest_path) for each
    repacked dep.
    """
    if visited is None:
        visited = set()

    config = load_config()
    results: list[tuple] = []

    # Resolve all retained deps to exact versions
    dep_versions = resolve_dep_versions(repacked_meta_text, extra_indexes)
    print(f"\nResolved {len(dep_versions)} retained deps\n")

    # Audit each dep
    for dep_name, dep_version in sorted(dep_versions.items()):
        key = f"{_normalize(dep_name)}-{dep_version}"
        if key in visited:
            continue
        visited.add(key)

        info = audit_dep_meta(dep_name, dep_version, extra_indexes)
        if info is None:
            continue

        if not info["has_suspect_deps"]:
            continue

        print(f"\n--- {dep_name}=={dep_version} ---")
        for s in info["suspect_deps"]:
            print(f"  suspect: {s}")

        result = repack_dep(dep_name, dep_version, extra_indexes, visited)
        if result is None:
            continue

        output_wheel, manifest, sub_deps = result
        results.append((dep_name, dep_version, output_wheel, manifest))

        # Add sub-dependencies to results for tracking
        for sub_name, sub_version in sub_deps:
            results.append((sub_name, sub_version, None, None))

    return results


# ── main repack ────────────────────────────────────────────────────────


def repack_top_level(whl_path: Path, extra_indexes: list[str], recurse: bool = True):
    config = load_config()
    ensure_dirs()

    print(f"Repacking: {whl_path.name}")

    # 1. Read METADATA
    meta_text, dist_info_dir = read_wheel_metadata(whl_path)
    old_dist_info_dir = dist_info_dir

    # Handle empty / locally-built wheels: strip local version suffix
    # from both the .dist-info directory name and the METADATA text.
    # Then add +flagos suffix.
    stripped = re.sub(r"\+[^.]*", "", dist_info_dir)
    has_local = stripped != dist_info_dir
    if has_local:
        dist_info_dir = stripped
        meta_text = _strip_local_version(meta_text)
        print(f"  strip local version: {old_dist_info_dir} → {dist_info_dir}")

    # Add +flagos suffix to version
    meta_text = _add_version_suffix(meta_text, "flagos")
    print("  add version suffix: +flagos")

    # Also update dist_info_dir to include +flagos suffix
    if dist_info_dir.endswith(".dist-info"):
        base = dist_info_dir[:-len(".dist-info")]
        dist_info_dir = f"{base}+flagos.dist-info"
        print(f"  update dist-info dir: {old_dist_info_dir} -> {dist_info_dir}")

    # Read WHEEL file to determine the platform tag
    wheel_text = _read_wheel_file(whl_path, old_dist_info_dir)
    wheel_tag = _get_wheel_tag(wheel_text)

    all_rd = parse_requires_dist(meta_text)

    # 2. Classify every Requires-Dist
    removed: dict[str, list[str]] = {"torch_chain": [], "cuda_only": [], "orphaned": []}
    retained: list[str] = []

    for rd in all_rd:
        cat = classify(rd, config)
        if cat in ("torch_chain", "cuda_only", "orphaned"):
            removed[cat].append(rd["raw"])
        else:
            retained.append(rd["raw"])

    print(f"  keep:     {len(retained)}")
    for cat in ("torch_chain", "cuda_only", "orphaned"):
        if removed[cat]:
            print(f"  {cat}: {len(removed[cat])}")

    # 3. Build top-level manifest
    pkg_name = None
    pkg_version = None
    mvn = re.search(r"^Name:\s*(.+)$", meta_text, re.MULTILINE | re.IGNORECASE)
    mvv = re.search(r"^Version:\s*(.+)$", meta_text, re.MULTILINE | re.IGNORECASE)
    if mvn:
        pkg_name = mvn.group(1).strip()
    if mvv:
        pkg_version = mvv.group(1).strip()
        # Keep the +flagos suffix for output filename

    # 4. Strip & rewrite top-level wheel
    names_to_remove: set[str] = set()
    for cat in ("torch_chain", "cuda_only", "orphaned"):
        for rd_raw in removed.get(cat, []):
            nm = _NAME_RE.match(rd_raw)
            if nm:
                names_to_remove.add(_normalize(nm.group(1)))

    new_meta = _strip_requires_dist_lines(meta_text, names_to_remove)
    new_meta = _downgrade_metadata_version(new_meta)
    # Note: +flagos suffix already added to meta_text above, no need to add again

    # 5. Recursive indirect dep audit + repack
    repacked_deps: list[dict] = []
    all_repacked_packages: list[tuple[str, str]] = []  # All packages with their original versions
    if recurse:
        print(f"\n=== Recursive dependency audit ===")
        results = repack_recursive(new_meta, extra_indexes)
        for dep_name, dep_version, dep_whl, dep_manifest in results:
            if dep_whl and dep_manifest:  # Only direct repacks have wheel/manifest
                repacked_deps.append({
                    "package": dep_name,
                    "version": dep_version,
                    "wheel": dep_whl.name,
                    "manifest": dep_manifest.name,
                })
            all_repacked_packages.append((dep_name, dep_version))

    # 6. Update Requires-Dist for all repacked deps (add +flagos to their versions)
    if all_repacked_packages:
        print(f"\n=== Updating dependency versions ===")
        for dep_name, dep_version in all_repacked_packages:
            # Replace exact version match with +flagos suffix
            # Pattern: package==version -> package==version+flagos
            # Use normalized name for matching (pip uses underscores, METADATA uses hyphens)
            norm_name = _normalize(dep_name)
            # Match either original name or normalized variants (underscores/hyphens)
            name_pattern = re.escape(dep_name).replace(r'\-', '[-_]').replace('_', '[-_]')
            pattern = rf"(^{name_pattern}==){re.escape(dep_version)}(\s*;|\s*$)"
            replacement = rf"\g<1>{dep_version}+flagos\g<2>"
            new_meta, count = re.subn(pattern, replacement, new_meta, flags=re.MULTILINE | re.IGNORECASE)
            if count > 0:
                print(f"  updated: {dep_name}=={dep_version} -> {dep_version}+flagos")
            else:
                print(f"  WARNING: could not update {dep_name}=={dep_version} (not found in METADATA)")

    # 7. Rewrite top-level wheel with updated metadata
    output_name = wheel_name_to_filename(pkg_name or "package", pkg_version or "0.0.0", wheel_tag)
    output_path = OUTPUT_DIR / output_name
    # Pass None for wheel_text to keep original WHEEL file
    rewrite_wheel(whl_path, output_path, new_meta, dist_info_dir,
                  old_dist_info_dir, wheel_text=None)

    # 8. Write top-level manifest (now includes recursive results)
    # Use version with +flagos for manifest filename
    manifest_path = OUTPUT_DIR / f"{_normalize(pkg_name or 'unknown')}-{pkg_version or 'unknown'}.deps-manifest.yaml"
    manifest_data = {
        "source_wheel": whl_path.name,
        "source_sha256": sha256_file(whl_path),
        "package": pkg_name,
        "version": pkg_version,
        "modified_at": datetime.now(timezone.utc).isoformat(),
        "removed": {k: v for k, v in removed.items() if v},
        "repacked_deps": repacked_deps,
        "retained": retained,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\nDone:")
    print(f"  wheel:    {output_path}")
    print(f"  manifest: {manifest_path}")
    if repacked_deps:
        print(f"  indirect: {len(repacked_deps)} repacked → output/")

    return output_path, manifest_path


# ── CLI ────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Repack a Python wheel, stripping unwanted Requires-Dist entries."
    )
    parser.add_argument(
        "wheel",
        help="Path to .whl file to repack.",
    )
    parser.add_argument(
        "--extra-index",
        action="append",
        default=[],
        dest="extra_indexes",
        help="Additional PyPI index for resolving indirect dependencies.",
    )
    parser.add_argument(
        "--no-recurse",
        action="store_false",
        dest="recurse",
        help="Skip recursive dependency audit. Only repack the top-level wheel.",
    )
    args = parser.parse_args()

    whl_path = Path(args.wheel).resolve()
    if not whl_path.exists():
        print(f"Error: {whl_path} does not exist", file=sys.stderr)
        sys.exit(1)

    repack_top_level(whl_path, args.extra_indexes, recurse=args.recurse)


if __name__ == "__main__":
    main()
