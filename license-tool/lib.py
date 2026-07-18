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

"""Shared library for the license-tool suite.

Import this module from scan_headers, add_headers, and gen_report.
No file-system side effects except for the YAML/JSON dump/load helpers.
"""

import json
import os
import re

# =============================================================================
#  YAML helpers — writes human-readable YAML; JSON is the canonical load format
# =============================================================================

def _yaml_key(k):
    s = str(k)
    if not s or s in ("true","false","yes","no","on","off","null","~","y","n"):
        return json.dumps(s)
    if any(c in s for c in ':{}[]#&*!|>"\'@%`,'):
        return json.dumps(s)
    if s.startswith(" ") or s.endswith(" "):
        return json.dumps(s)
    return s


def _yaml_val(v):
    if isinstance(v, str):
        if not v or v in ("true","false","yes","no","on","off","null","~","y","n"):
            return json.dumps(v)
        if any(c in v for c in ':{}[]#&*!|>"\'@%`,'):
            return json.dumps(v)
        if v.startswith(" ") or v.endswith(" "):
            return json.dumps(v)
        return v
    elif isinstance(v, bool):
        return "true" if v else "false"
    elif v is None:
        return "~"
    elif isinstance(v, (int, float)):
        return str(v)
    return json.dumps(v)


def _dump_yaml(obj, indent=0):
    sp = "  " * indent
    if isinstance(obj, dict):
        out = []
        for k, v in obj.items():
            ky = _yaml_key(k)
            if isinstance(v, dict):
                out.append(f"{sp}{ky}:")
                out.append(_dump_yaml(v, indent + 1))
            elif isinstance(v, list):
                if not v:
                    out.append(f"{sp}{ky}: []")
                else:
                    out.append(f"{sp}{ky}:")
                    for item in v:
                        if isinstance(item, dict):
                            out.append(f"{sp}  -")
                            out.append(_dump_yaml(item, indent + 2))
                        else:
                            out.append(f"{sp}  - {_yaml_val(item)}")
            elif v is None:
                out.append(f"{sp}{ky}: ~")
            elif isinstance(v, bool):
                out.append(f"{sp}{ky}: {'true' if v else 'false'}")
            elif isinstance(v, str) and "\n" in v:
                out.append(f"{sp}{ky}: |")
                for line in v.rstrip("\n").split("\n"):
                    out.append(f"{sp}  {line}")
            else:
                out.append(f"{sp}{ky}: {_yaml_val(v)}")
        return "\n".join(out) + "\n"
    elif isinstance(obj, list):
        if not obj:
            return f"{sp}[]\n"
        out = []
        for item in obj:
            if isinstance(item, dict):
                out.append(f"{sp}-")
                out.append(_dump_yaml(item, indent + 1).rstrip("\n"))
            else:
                out.append(f"{sp}- {_yaml_val(item)}")
        return "\n".join(out) + "\n"
    else:
        return f"{sp}{_yaml_val(obj)}\n"


def dump_yaml(obj, filepath):
    with open(filepath, "w") as f:
        f.write(_dump_yaml(obj))


def load_data(yaml_path):
    """Load audit data from the JSON companion file (always present after dump)."""
    json_path = yaml_path.rsplit(".", 1)[0] + ".json"
    with open(json_path, "r") as f:
        return json.load(f)


def dump_data(data, yaml_path):
    """Dump audit data to YAML (human) and JSON (canonical)."""
    dump_yaml(data, yaml_path)
    json_path = yaml_path.rsplit(".", 1)[0] + ".json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# =============================================================================
#  File-skip rules
# =============================================================================

SKIP_PATTERNS = ["LICENSE", "go.sum", ".gitignore", "README.md",
                 "changelog",  # Debian changelog: strict format, dpkg-buildpackage parsing
                 ]

# Path prefixes to skip (directories with strict-format files).
SKIP_PATH_PREFIXES = [
    "packaging/",     # Debian/RPM packaging: strict format (control, rules, spec, etc.)
    "third_party/",   # Forked upstream code — not ours to relicense; headers shift line numbers
]

SKIP_EXTENSIONS = {
    ".json", ".png", ".jpg", ".jpeg", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".pyc", ".zip",
    ".tar", ".gz", ".bz2", ".xz", ".deb", ".rpm",
    ".bc", ".pdf", ".pptx", ".docx",
    ".bin", ".a", ".map", ".csv", ".bk", ".o", ".so", ".dylib",
}

COMMENT_STYLE = {
    # Shell-style #
    ".py":     '# prefix (after shebang if present)',
    ".yaml":   '# prefix',
    ".yml":    '# prefix',
    ".sh":     '# prefix (after shebang if present)',
    ".bash":   '# prefix (after shebang if present)',
    ".toml":   '# prefix',
    "":        '# prefix (Containerfile)',
    ".cfg":    '# prefix',
    ".ini":    '# prefix',
    ".cmake":  '# prefix',
    ".txt":    '# prefix',
    ".in":     '# prefix',
    ".install": '# prefix',
    ".spec":   '# prefix',
    ".service": '# prefix',
    ".conf":   '# prefix',
    ".dockerfile": '# prefix',
    ".pypirc": '# prefix',
    # C/C++ style //
    ".cpp":    '// prefix',
    ".c":      '// prefix',
    ".h":      '// prefix',
    ".hpp":    '// prefix',
    ".cu":     '// prefix',
    ".cuh":    '// prefix',
    ".cc":     '// prefix',
    ".cxx":    '// prefix',
    ".hxx":    '// prefix',
    # MLIR / TableGen / Go
    ".mlir":   '// prefix',
    ".td":     '// prefix',
    ".md":     '<!-- --> (after Hugo frontmatter if present)',
    # LLVM IR
    ".ll":     "; prefix",
    ".html":   '<!-- -->',
    ".rst":    '.. SQL comment style',
    ".css":    '/* */ block',
    ".scss":   '/* */ block',
    ".gotmpl": '{{/* */}} Go template comment',
    ".go":     '// prefix',
    ".mod":    '// prefix',
}


def _skip_reason(filepath):
    basename = os.path.basename(filepath)
    ext = os.path.splitext(filepath)[1].lower()
    if basename == "go.sum":
        return "auto-generated checksums"
    if basename in (".gitignore",):
        return "git config, no comment syntax"
    if basename == "LICENSE":
        return "license text itself"
    if ext in SKIP_EXTENSIONS:
        return "binary / generated"
    return "excluded by rule"


def should_skip(filepath):
    basename = os.path.basename(filepath)
    ext = os.path.splitext(filepath)[1].lower()
    if basename in SKIP_PATTERNS:
        return True
    if ext in SKIP_EXTENSIONS:
        return True
    for prefix in SKIP_PATH_PREFIXES:
        if filepath.startswith(prefix):
            return True
    return False


# =============================================================================
#  File extension classification
# =============================================================================

def classify_ext(filepath):
    """Return a normalized extension, handling version-number suffixes and
    .disabled YAML files."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".disabled":
        return ".yaml"
    if ext and ext[1:].replace(".", "").isdigit():
        return ""
    return ext


# =============================================================================
#  License definitions
# =============================================================================

_LICENSE_NAMES = {
    "apache": "Apache 2.0",
    "mit":    "MIT",
    "bsd3":   "BSD 3-Clause",
    "gpl":    "GPL",
    "mpl":    "MPL 2.0",
}


def license_name(license_id):
    return _LICENSE_NAMES.get(license_id, license_id)


# === License detection patterns (for existing headers) ===

# Checked in priority order — first match wins.
_LICENSE_PATTERNS = [
    ("apache",      re.compile(r'Apache License|Apache-2\.0|SPDX.*Apache-2\.0', re.I)),
    ("mit",         re.compile(r'MIT License|SPDX-License-Identifier:\s*MIT\b|'
                               r'Permission is hereby granted, free of charge', re.I)),
    ("gpl",         re.compile(r'GNU General Public|GPL|SPDX.*GPL|'
                               r'This program is free software', re.I)),
    ("bsd3",        re.compile(r'BSD\s|BSD-|SPDX.*BSD|'
                               r'Redistribution and use in source and binary forms', re.I)),
    ("mpl",         re.compile(r'Mozilla Public|MPL|SPDX.*MPL', re.I)),
    ("proprietary", re.compile(r'All rights reserved|Proprietary', re.I)),
    ("spdx_other",  re.compile(r'SPDX-License-Identifier:\s*(\S+)', re.I)),
]

_COPYRIGHT_RE = re.compile(r'Copyright\s+(\d{4}(?:-\d{4})?)\s+(.+?)(?:\n|$)', re.I)
_COPYRIGHT_ANY = re.compile(r'Copyright', re.I)


def _extract_snippet(content):
    """Extract the first meaningful lines (max 12) from content for preview."""
    lines = content.split("\n")
    result = []
    started = False
    for line in lines:
        stripped = line.rstrip()
        if not started and stripped == "":
            continue
        started = True
        result.append(stripped)
        if len(result) >= 12:
            break
    return "\n".join(result)


def classify_existing_header(content, our_owner, our_license):
    """Scan the first 8KB of *content* and classify any existing copyright header.

    Returns (category, detail_dict) where category is one of:
        'none'            — no copyright found, safe to add our header
        'ours'            — same license as repo + same owner
        'other_owner'     — same license as repo but different copyright owner
        'other_license'   — copyright present with a different license
        'unlicensed'      — copyright present but no detectable license grant
    """
    head = content[:8192]

    if not _COPYRIGHT_ANY.search(head):
        return "none", {}

    m = _COPYRIGHT_RE.search(head)
    detected_owner = m.group(2).strip() if m else "unknown"
    detected_year = m.group(1) if m else "unknown"

    detected_license = None
    for lic_id, pat in _LICENSE_PATTERNS:
        if pat.search(head):
            detected_license = lic_id
            break

    snippet = _extract_snippet(head)

    detail = {
        "owner": detected_owner,
        "year": detected_year,
        "license": detected_license or "unknown",
        "snippet": snippet,
    }

    if detected_license == our_license:
        if detected_owner == our_owner:
            return "ours", detail
        else:
            return "other_owner", detail
    elif detected_license is not None:
        return "other_license", detail
    else:
        return "unlicensed", detail


# === License-specific header templates ===

def _apache_header(year, owner):
    return [
        f"Copyright {year} {owner}",
        "",
        'Licensed under the Apache License, Version 2.0 (the "License");',
        "you may not use this file except in compliance with the License.",
        "You may obtain a copy of the License at",
        "",
        "    http://www.apache.org/licenses/LICENSE-2.0",
        "",
        "Unless required by applicable law or agreed to in writing, software",
        "distributed under the License is distributed on an \"AS IS\" BASIS,",
        "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.",
        "See the License for the specific language governing permissions and",
        "limitations under the License.",
    ]


def _mit_header(year, owner):
    return [
        f"Copyright {year} {owner}",
        "",
        "Permission is hereby granted, free of charge, to any person obtaining a copy",
        "of this software and associated documentation files (the \"Software\"), to deal",
        "in the Software without restriction, including without limitation the rights",
        "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell",
        "copies of the Software, and to permit persons to whom the Software is",
        "furnished to do so, subject to the following conditions:",
        "",
        "The above copyright notice and this permission notice shall be included in all",
        "copies or substantial portions of the Software.",
        "",
        "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR",
        "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,",
        "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE",
        "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER",
        "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,",
        "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE",
        "SOFTWARE.",
    ]


def _bsd3_header(year, owner):
    return [
        f"Copyright {year} {owner}",
        "",
        "Redistribution and use in source and binary forms, with or without",
        "modification, are permitted provided that the following conditions are met:",
        "",
        "1. Redistributions of source code must retain the above copyright notice,",
        "   this list of conditions and the following disclaimer.",
        "",
        "2. Redistributions in binary form must reproduce the above copyright notice,",
        "   this list of conditions and the following disclaimer in the documentation",
        "   and/or other materials provided with the distribution.",
        "",
        "3. Neither the name of the copyright holder nor the names of its",
        "   contributors may be used to endorse or promote products derived from",
        "   this software without specific prior written permission.",
        "",
        "THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS \"AS IS\"",
        "AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE",
        "IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE",
        "ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE",
        "LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR",
        "CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF",
        "SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS",
        "INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN",
        "CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)",
        "ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE",
        "POSSIBILITY OF SUCH DAMAGE.",
    ]


_HEADER_TEMPLATES = {
    "apache": _apache_header,
    "mit":    _mit_header,
    "bsd3":   _bsd3_header,
}


def build_header_lines(year, owner, license_id="apache"):
    """Return the list of header lines for *license_id*."""
    fn = _HEADER_TEMPLATES.get(license_id, _apache_header)
    return fn(year, owner)


# === Repo-level license detection ===

_LICENSE_FILE_PATTERNS = [
    ("apache", re.compile(r'Apache License|Apache-2\.0', re.I)),
    ("mit",    re.compile(r'MIT License|permission is hereby granted, free of charge',
                          re.I)),
    ("gpl",    re.compile(r'GNU General Public|General Public License', re.I)),
    ("bsd3",   re.compile(r'BSD|Redistribution and use in source and binary forms', re.I)),
    ("mpl",    re.compile(r'Mozilla Public License|MPL', re.I)),
]


def detect_repo_license(repo_root):
    """Inspect the repo's LICENSE file and return (license_id, human_name).

    Falls back to ("apache", "Apache 2.0") when no LICENSE file is found or
    the file content does not match any known license.
    """
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md"):
        path = os.path.join(repo_root, name)
        if os.path.isfile(path):
            try:
                with open(path, "r", errors="replace") as f:
                    content = f.read(8192)
                for lic_id, pat in _LICENSE_FILE_PATTERNS:
                    if pat.search(content):
                        return lic_id, _LICENSE_NAMES[lic_id]
            except (IOError, OSError):
                pass
    return "apache", _LICENSE_NAMES["apache"]


# =============================================================================
#  Comment-block builders
# =============================================================================

def make_comment_block(header_lines, prefix, prefix_blank=""):
    """Build a line-prefixed comment block (e.g. ``# `` for Python)."""
    lines = []
    for line in header_lines:
        if line == "":
            lines.append(prefix_blank if prefix_blank else prefix.rstrip())
        else:
            lines.append(f"{prefix}{line}")
    return "\n".join(lines) + "\n"


def block_comment(header_lines, start, end):
    """Build a delimited block comment (e.g. ``<!--`` / ``-->`` for HTML)."""
    body = []
    for line in header_lines:
        if line == "":
            body.append("")
        else:
            body.append(f" {line}")
    return "\n".join([start] + body + [f" {end}"]) + "\n"


# =============================================================================
#  Header placement logic (file-type aware)
# =============================================================================

# Extensions that get # prefix
_HASH_EXTS = {".py", ".yaml", ".yml", ".sh", ".bash", ".toml",
              ".cfg", ".ini", ".cmake", ".txt", ".in", ".install",
              ".spec", ".service", ".conf", ".dockerfile", ".pypirc",
              ".pyi"}
# Extensions where we check for shebang
_SHEBANG_EXTS = {".py", ".sh", ".bash"}
# Extensions that get // prefix
_CPP_EXTS = {".cpp", ".c", ".h", ".hpp", ".cu", ".cuh",
             ".cc", ".cxx", ".hxx", ".go", ".mod",
             ".mlir", ".td"}

# LLVM IR uses ; comments
_SEMI_EXTS = {".ll"}
# Extensions that get /* */ block
_BLOCK_EXTS = {".scss", ".css"}
# Extensions that get <!-- --> HTML comment
_HTML_EXTS = {".md", ".html", ".rst"}
# Extensions that get Go template comment
_GOTMPL_EXTS = {".gotmpl"}

# HASH_EXTS: "# EXTS"


def get_header(filepath, header_lines):
    """Return (header_text, insertion_line) for *filepath*."""
    ext = classify_ext(filepath)

    if ext in _HASH_EXTS or ext == "":
        header = make_comment_block(header_lines, "# ")
        if ext in _SHEBANG_EXTS or ext == "":
            try:
                with open(filepath, "r", errors="replace") as f:
                    first_line = f.readline()
                if first_line.startswith("#!"):
                    with open(filepath, "r", errors="replace") as f:
                        f.readline()
                        second_line = f.readline()
                    return header, 2 if second_line == "\n" else 1
            except (IOError, OSError, UnicodeDecodeError):
                pass
        return header, 0

    if ext == ".md":
        try:
            with open(filepath, "r", errors="replace") as f:
                first_line = f.readline()
            if first_line.strip() == "---":
                with open(filepath, "r", errors="replace") as f:
                    f.readline()
                    line_count = 1
                    for line in f:
                        line_count += 1
                        if line.strip() == "---":
                            break
                return block_comment(header_lines, "<!--", "-->"), line_count
        except (IOError, OSError, UnicodeDecodeError):
            pass
        return block_comment(header_lines, "<!--", "-->"), 0

    if ext in _GOTMPL_EXTS:
        return block_comment(header_lines, "{{/*", "*/}}"), 0

    if ext in _BLOCK_EXTS:
        return block_comment(header_lines, "/*", "*/"), 0

    if ext in _CPP_EXTS:
        return make_comment_block(header_lines, "// "), 0

    if ext in _SEMI_EXTS:
        return make_comment_block(header_lines, "; "), 0

    if ext in _HTML_EXTS - {".md"}:
        return block_comment(header_lines, "<!--", "-->"), 0

    return None, 0


# =============================================================================
#  Git helpers
# =============================================================================

def git_info(repo_root):
    """Return (remote, commit, branch)."""
    import subprocess
    remote = commit = branch = ""
    try:
        r = subprocess.run(["git", "remote", "get-url", "origin"],
                           capture_output=True, text=True, cwd=repo_root)
        raw = r.stdout.strip()
        if raw.endswith(".git"):
            raw = raw[:-4]
        remote = raw
    except Exception:
        pass
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"],
                           capture_output=True, text=True, cwd=repo_root)
        commit = r.stdout.strip()[:8]
    except Exception:
        pass
    try:
        r = subprocess.run(["git", "branch", "--show-current"],
                           capture_output=True, text=True, cwd=repo_root)
        branch = r.stdout.strip()
    except Exception:
        pass
    return remote, commit, branch


def org_repo(remote, fallback_name):
    if not remote:
        return f"local/{fallback_name}"
    url = remote
    if "@" in url and ":" in url:
        url = url.split("@", 1)[1]
        url = url.replace(":", "/", 1)
    parts = url.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return f"local/{fallback_name}"


# =============================================================================
#  Edge-case detection
# =============================================================================

def detect_edge_cases(all_files):
    """Return a list of {label, detail} dicts describing edge cases found."""
    edge = []

    vs = [f for f in all_files
          if os.path.splitext(f)[1].lower() and
          os.path.splitext(f)[1].lower()[1:].replace(".", "").isdigit()]
    if vs:
        edge.append({
            "label": "Version-suffix filenames",
            "detail": (f"{len(vs)} files with version-number extensions "
                       f"(e.g. `{os.path.basename(vs[0])}`) — detected and treated as no-extension.")
        })

    disabled = [f for f in all_files if f.endswith(".disabled")]
    if disabled:
        edge.append({
            "label": ".disabled suffix",
            "detail": (f"{len(disabled)} YAML file(s) with .disabled extension — "
                       f"`classify_ext()` normalizes to `.yaml`.")
        })

    shebangs = [f for f in all_files if classify_ext(f) in {".py", ".sh"}]
    if shebangs:
        has_shebang = False
        for f in shebangs[:30]:
            try:
                with open(f, "r", errors="replace") as fh:
                    if fh.readline().startswith("#!"):
                        has_shebang = True
                        break
            except Exception:
                pass
        if has_shebang:
            edge.append({
                "label": "Shebang lines",
                "detail": (f"{len(shebangs)} Python/shell files — "
                           "header inserted after shebang line, preserving it as line 1.")
            })

    hugo_md = [f for f in all_files if f.endswith(".md")]
    if hugo_md:
        has_fm = False
        for f in hugo_md[:50]:
            try:
                with open(f, "r", errors="replace") as fh:
                    if fh.readline().strip() == "---":
                        has_fm = True
                        break
            except Exception:
                pass
        if has_fm:
            edge.append({
                "label": "Hugo frontmatter",
                "detail": ("Markdown files with `---` delimited YAML frontmatter — "
                           "header inserted after closing `---`, keeping frontmatter intact.")
            })

    return edge


# =============================================================================
#  Repo classification (read-only — never writes to files)
# =============================================================================

def classify_files(repo_root, year, owner, license_id=None):
    """Scan a repo and return the full audit data dict.

    This is a PURE read-only function: no files are modified on disk.
    The returned dict has the same shape expected by scan_headers, add_headers,
    and gen_report.
    """
    import datetime
    import subprocess as sp

    lic_id, lic_name = resolve_license(repo_root, license_id)

    remote, commit, branch = git_info(repo_root)
    basename = os.path.basename(repo_root.rstrip("/"))
    orr = org_repo(remote, basename)

    result = sp.run(
        ["git", "ls-files"],
        capture_output=True, text=True, cwd=repo_root
    )
    if result.returncode != 0:
        raise SystemExit(f"error: git ls-files failed in {repo_root}")
    all_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

    stats = {"added": 0, "skipped": 0, "already_ours": 0,
             "other_owner": 0, "other_license": 0, "unlicensed": 0,
             "unknown_type": 0, "error": 0}
    skipped_files = []
    error_files = []
    other_owner_files = []
    other_license_files = []
    unlicensed_files = []
    needs_header_files = []  # files classified as "none" — safe to add headers
    file_type_counts = {}

    for filepath in all_files:
        fullpath = os.path.join(repo_root, filepath)

        if should_skip(filepath):
            stats["skipped"] += 1
            skipped_files.append({"path": filepath, "reason": _skip_reason(filepath)})
            continue

        ext = classify_ext(fullpath)

        try:
            with open(fullpath, "r", errors="replace") as f:
                head_content = f.read(8192)
        except (IOError, OSError, UnicodeDecodeError):
            stats["error"] += 1
            error_files.append({"path": filepath, "error": "unreadable or binary"})
            continue

        cat, detail = classify_existing_header(head_content, owner, lic_id)
        ft = file_type_counts.setdefault(ext, {"count": 0, "style": COMMENT_STYLE.get(ext, "—")})

        if cat == "ours":
            stats["already_ours"] += 1
            ft["count"] += 1
        elif cat == "other_owner":
            stats["other_owner"] += 1
            other_owner_files.append({"path": filepath, "owner": detail.get("owner", "?"),
                                       "year": detail.get("year", "?"),
                                       "snippet": detail.get("snippet", "")})
            ft["count"] += 1
        elif cat == "other_license":
            stats["other_license"] += 1
            other_license_files.append({"path": filepath, "license": detail.get("license", "?"),
                                         "snippet": detail.get("snippet", "")})
            ft["count"] += 1
        elif cat == "unlicensed":
            stats["unlicensed"] += 1
            unlicensed_files.append({"path": filepath, "snippet": detail.get("snippet", "")})
            ft["count"] += 1
        elif cat == "none":
            stats["added"] += 1
            needs_header_files.append(filepath)
            ft["count"] += 1
        else:
            stats["skipped"] += 1

    edge_cases = detect_edge_cases(
        [os.path.join(repo_root, f) for f in all_files]
    )

    return {
        "repo": {
            "name": basename,
            "org_repo": orr,
            "remote": remote,
            "commit": commit,
            "branch": branch,
            "root": repo_root,
        },
        "scan": {
            "date": datetime.date.today().isoformat(),
            "year": year,
            "owner": owner,
            "license": lic_id,
            "license_name": lic_name,
        },
        "stats": stats,
        "lines_added": 0,  # classify only — counting lines is the applier's job
        "file_types": file_type_counts,
        "skipped": skipped_files,
        "errors": error_files,
        "edge_cases": edge_cases,
        "other_owner": other_owner_files,
        "other_license": other_license_files,
        "unlicensed": unlicensed_files,
        "needs_header": needs_header_files,
    }


# =============================================================================
#  Shared CLI helpers
# =============================================================================

def add_common_args(parser):
    """Add --year, --owner, --license to an ArgumentParser."""
    parser.add_argument("--year", default="2026")
    parser.add_argument("--owner", default="FlagOS Contributors")
    parser.add_argument("--license", dest="license_id", default=None,
                        choices=["apache", "mit", "bsd3", "gpl", "mpl"],
                        help="License to use (default: auto-detect from LICENSE file)")


def resolve_license(repo_root, license_id_override):
    """Return (license_id, license_name) for *repo_root*."""
    if license_id_override is not None:
        return license_id_override, license_name(license_id_override)
    return detect_repo_license(repo_root)
