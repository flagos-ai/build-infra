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
    python repack.py /path/to/vllm-0.25.1-xxx.whl          # single wheel
    python repack.py --from pypi vllm==0.25.1               # download first
    python repack.py --extra-index https://... vllm.whl     # add search index

The script puts repacked wheels + manifests under output/ and patched
indirect-dependency wheels under cache/.
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
DEPS_INDEX_PATH = SCRIPT_DIR / "deps-index.yaml"


# ── helpers ────────────────────────────────────────────────────────────


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dirs():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_deps_index():
    if not DEPS_INDEX_PATH.exists():
        return {}
    with open(DEPS_INDEX_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_deps_index(index):
    with open(DEPS_INDEX_PATH, "w", encoding="utf-8") as f:
        yaml.dump(index, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


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
_LICENSE_FILE_RE = re.compile(r"^License-File:\s*.+$", re.MULTILINE | re.IGNORECASE)
_DYNAMIC_RE = re.compile(r"^Dynamic:\s*.+$", re.MULTILINE | re.IGNORECASE)


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


def _extract_name_version(requires_dist_line: str):
    """Return (name, version_spec_no_marker) from a raw Requires-Dist string.

    Strips extras like [cu13] and environment markers like ; platform_system == ... .
    """
    raw = requires_dist_line.strip()
    # Split off environment marker
    pkg_spec = raw.split(";", 1)[0].strip()

    m = _NAME_RE.match(pkg_spec)
    name = m.group(1).strip() if m else pkg_spec

    # Version spec is everything after the name (may include extras brackets)
    version_spec = pkg_spec[len(name):].strip()

    return name, version_spec


# ── classification ─────────────────────────────────────────────────────


def classify(rd: dict, config: dict):
    """Return one of: 'torch_chain', 'cuda_only', 'orphaned', 'repack', 'keep'."""
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
    for item in config.get("also_repack", []):
        if _normalize(item) == nn:
            return "repack"
    return "keep"


# ── wheel I/O ──────────────────────────────────────────────────────────


def read_wheel_metadata(whl_path: Path) -> tuple[str, str]:
    """Return (metadata_text, dist_info_dir_name)."""
    with zipfile.ZipFile(whl_path) as z:
        for name in z.namelist():
            if name.endswith(".dist-info/METADATA"):
                return z.read(name).decode("utf-8"), name.split("/")[0]
    raise ValueError(f"No .dist-info/METADATA found in {whl_path}")


def rewrite_wheel(src: Path, dst: Path, metadata_text: str, dist_info_dir: str):
    """Copy src → dst, replacing METADATA content."""
    with zipfile.ZipFile(src) as zin:
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == f"{dist_info_dir}/METADATA":
                    zout.writestr(item, metadata_text)
                else:
                    zout.writestr(item, data)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def wheel_name_to_filename(name: str, version: str) -> str:
    """Convert package name + version to a wheel filename.
    Since we only replace METADATA we reuse the original (correct) tag."""
    safe_name = re.sub(r"[-_.]+", "_", name)
    return f"{safe_name}-{version}-py3-none-any.whl"


# ── indirect dep repacking ─────────────────────────────────────────────


def resolve_wheel(name: str, version: str, extra_indexes: list[str]) -> Path:
    """Download a wheel from PyPI JSON API.
    Returns path to downloaded .whl file.  `version` must be an exact version
    (e.g. '0.2.3'), not a specifier range.
    """
    import urllib.request as _ur

    # Try PyPI JSON API to get the wheel URL
    indexes = ["https://pypi.org/pypi/"] + [ei.rstrip("/") + "/" for ei in extra_indexes]
    wheel_url = None
    wheel_filename = None

    for base_url in indexes:
        try:
            url = f"{base_url}{name}/{version}/json"
            req = _ur.Request(url, headers=_JSON_HEADERS)
            with _ur.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            for entry in data.get("urls", []):
                if entry.get("packagetype") == "bdist_wheel":
                    # prefer manylinux/compatible wheels over platform-specific
                    fn = entry.get("filename", "")
                    wheel_url = entry.get("url")
                    if wheel_url:
                        wheel_filename = fn
                        break
            if wheel_url:
                break
        except Exception:
            continue

    if not wheel_url:
        raise RuntimeError(f"Could not find wheel for {name}=={version}")

    dst = CACHE_DIR / wheel_filename
    print(f"    downloading {wheel_filename} ...")
    try:
        with _ur.urlopen(wheel_url, timeout=120) as resp:
            with open(dst, "wb") as f:
                shutil.copyfileobj(resp, f)
    except Exception:
        # Fallback: try pip download
        import subprocess as _sp
        spec = f"{name}=={version}"
        _sp.run(
            [sys.executable, "-m", "pip", "download", "--no-deps", "--dest", str(CACHE_DIR), spec],
            check=True, capture_output=True,
        )
        whls = sorted(CACHE_DIR.glob(f"{re.sub(r'[-_.]', '[-_.]', name)}-{version}*.whl"))
        if whls:
            return whls[-1]
        raise

    return dst

_JSON_HEADERS = {"Accept": "application/json"}


def _resolve_version_from_pypi(name: str, version_spec: str, extra_indexes: list[str]) -> str | None:
    """Resolve a version specifier to an exact version using PyPI JSON API."""
    indexes = ["https://pypi.org/pypi/"] + [ei.rstrip("/") + "/" for ei in extra_indexes]
    for base_url in indexes:
        url = f"{base_url}{name}/json"
        try:
            req = urllib.request.Request(url, headers=_JSON_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            versions = list(data.get("releases", {}).keys())
            versions.sort(key=lambda v: [int(x) for x in re.findall(r"\d+", v)])
            version_spec_parsed = version_spec.strip()
            for v in reversed(versions):
                if _version_matches(v, version_spec_parsed):
                    return v
        except Exception:
            continue
    return None


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


def repack_indirect(name: str, version_spec: str, extra_indexes: list[str],
                    deps_index: dict, config: dict):
    """Download and repack an indirect dep wheel.  Returns (cache_whl_path, manifest_path)."""
    # Resolve to exact version via PyPI JSON API
    with tempfile.TemporaryDirectory() as td:
        # Strip extras (e.g. [cu13]) for the PyPI lookup
        pypi_name = re.sub(r"\[.*\]", "", name)
        resolved_version = _resolve_version_from_pypi(pypi_name, version_spec, extra_indexes)
        if not resolved_version:
            raise RuntimeError(
                f"Could not resolve {name}{version_spec} via PyPI JSON API"
            )

    key = f"{_normalize(pypi_name)}-{resolved_version}"

    # Already processed?
    if key in deps_index:
        cached = deps_index[key]
        cache_whl = CACHE_DIR / cached["whl"]
        manifest = CACHE_DIR / cached["manifest"]
        if cache_whl.exists() and manifest.exists():
            print(f"  (cached) {key}")
            return cache_whl, manifest

    print(f"  processing {key} ...")

    # Download original wheel
    # Download original wheel (use name stripped of extras for download)
    wheel_path = resolve_wheel(pypi_name, resolved_version, extra_indexes)

    # Read its METADATA
    meta_text, dist_info_dir = read_wheel_metadata(wheel_path)
    all_rd = parse_requires_dist(meta_text)

    # Classify & record
    removed = []
    for rd in all_rd:
        nn = _normalize(rd["name"])
        if nn in {_normalize(x) for x in config.get("strip_from_repacked", [])}:
            removed.append(rd)
            print(f"    strip {rd['raw']}")

    # Write manifest
    manifest_path = CACHE_DIR / f"{_normalize(pypi_name)}-{resolved_version}.deps-manifest.yaml"
    manifest_data = {
        "source_wheel": wheel_path.name,
        "source_sha256": sha256_file(wheel_path),
        "package": pypi_name,
        "version": resolved_version,
        "modified_at": datetime.now(timezone.utc).isoformat(),
        "all_requires_dist": [rd["raw"] for rd in all_rd],
        "removed": [rd["raw"] for rd in removed],
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # Strip & rewrite
    strip_names = {_normalize(x) for x in config.get("strip_from_repacked", [])}
    new_meta = _strip_requires_dist_lines(meta_text, strip_names)
    new_meta = _downgrade_metadata_version(new_meta)
    output_name = wheel_name_to_filename(pypi_name, resolved_version)
    output_path = CACHE_DIR / output_name
    rewrite_wheel(wheel_path, output_path, new_meta, dist_info_dir)

    # Don't keep original — was only needed for METADATA extraction
    wheel_path.unlink()

    # Register
    deps_index[key] = {
        "whl": output_path.name,
        "manifest": manifest_path.name,
    }
    save_deps_index(deps_index)

    return output_path, manifest_path


# ── main repack ────────────────────────────────────────────────────────


def repack_top_level(whl_path: Path, extra_indexes: list[str]):
    config = load_config()
    ensure_dirs()
    deps_index = load_deps_index()

    print(f"Repacking: {whl_path.name}")

    # 1. Read METADATA
    meta_text, dist_info_dir = read_wheel_metadata(whl_path)
    all_rd = parse_requires_dist(meta_text)

    # 2. Classify every Requires-Dist
    removed: dict[str, list[str]] = {"torch_chain": [], "cuda_only": [], "orphaned": []}
    repack_targets: list[dict] = []
    retained: list[str] = []

    for rd in all_rd:
        cat = classify(rd, config)
        if cat in ("torch_chain", "cuda_only", "orphaned"):
            removed[cat].append(rd["raw"])
        elif cat == "repack":
            repack_targets.append(rd)
            removed.setdefault("repack", []).append(rd["raw"])
        else:
            retained.append(rd["raw"])

    print(f"  keep:     {len(retained)}")
    for cat in ("torch_chain", "cuda_only", "orphaned", "repack"):
        if removed[cat]:
            print(f"  {cat}: {len(removed[cat])}")

    # 3. Repack indirect deps (also_repack)
    repacked_refs: list[dict] = []
    for rd in repack_targets:
        name, version_spec = _extract_name_version(rd["raw"])
        cache_whl, manifest = repack_indirect(
            name, version_spec, extra_indexes, deps_index, config
        )
        repacked_refs.append({
            "original": rd["raw"],
            "repacked": str(cache_whl.relative_to(SCRIPT_DIR)),
            "manifest": str(manifest.relative_to(SCRIPT_DIR)),
        })

    # 4. Write top-level manifest
    pkg_name = None
    pkg_version = None
    mvn = re.search(r"^Name:\s*(.+)$", meta_text, re.MULTILINE | re.IGNORECASE)
    mvv = re.search(r"^Version:\s*(.+)$", meta_text, re.MULTILINE | re.IGNORECASE)
    if mvn:
        pkg_name = mvn.group(1).strip()
    if mvv:
        pkg_version = mvv.group(1).strip()

    manifest_path = OUTPUT_DIR / f"{_normalize(pkg_name or 'unknown')}-{pkg_version or 'unknown'}.deps-manifest.yaml"
    manifest_data = {
        "source_wheel": whl_path.name,
        "source_sha256": sha256_file(whl_path),
        "package": pkg_name,
        "version": pkg_version,
        "modified_at": datetime.now(timezone.utc).isoformat(),
        "removed": {k: v for k, v in removed.items() if v},
        "repacked_deps": repacked_refs,
        "retained": retained,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # 5. Strip & rewrite top-level wheel
    names_to_remove: set[str] = set()
    for cat in ("torch_chain", "cuda_only", "orphaned", "repack"):
        for rd_raw in removed.get(cat, []):
            nm = _NAME_RE.match(rd_raw)
            if nm:
                names_to_remove.add(_normalize(nm.group(1)))

    new_meta = _strip_requires_dist_lines(meta_text, names_to_remove)
    new_meta = _downgrade_metadata_version(new_meta)
    output_name = wheel_name_to_filename(pkg_name or "package", pkg_version or "0.0.0")
    output_path = OUTPUT_DIR / output_name
    rewrite_wheel(whl_path, output_path, new_meta, dist_info_dir)

    print(f"\nDone:")
    print(f"  wheel:    {output_path}")
    print(f"  manifest: {manifest_path}")
    if repacked_refs:
        print(f"  indirect: {len(repacked_refs)} repacked → cache/")

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
    args = parser.parse_args()

    whl_path = Path(args.wheel).resolve()
    if not whl_path.exists():
        print(f"Error: {whl_path} does not exist", file=sys.stderr)
        sys.exit(1)

    repack_top_level(whl_path, args.extra_indexes)


if __name__ == "__main__":
    main()
