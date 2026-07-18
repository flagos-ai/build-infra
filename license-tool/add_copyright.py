#!/usr/bin/env python3
"""Add copyright headers to all source files in a git repository.

Two-step workflow for the audit report:

  1. Scan + add headers, dump structured data:
       python3 add_copyright.py /path/to/repo --yaml audit-report-foo.yaml

  2. Generate/append HTML section from the YAML data (no repo scan needed):
       python3 add_copyright.py --from-yaml audit-report-foo.yaml \\
           --html-report copyright-audit-report.html

  3. Combine both in one pass:
       python3 add_copyright.py /path/to/repo \\
           --yaml audit-report-foo.yaml --html-report copyright-audit-report.html
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import textwrap


# =============================================================================
#  YAML helper — writes human-readable YAML; JSON companion is the load target
# =============================================================================

def _dump_yaml(obj, indent=0):
    """Recursive helper: return YAML string for *obj*."""
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


def _yaml_key(k):
    """Quote a YAML key if needed."""
    s = str(k)
    if not s or s in ("true","false","yes","no","on","off","null","~","y","n"):
        return json.dumps(s)
    if any(c in s for c in ':{}[]#&*!|>"\'@%`,'):
        return json.dumps(s)
    if s.startswith(" ") or s.endswith(" "):
        return json.dumps(s)
    return s


def _yaml_val(v):
    """Format a scalar YAML value, quoting if needed."""
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


def dump_yaml(obj, filepath):
    with open(filepath, "w") as f:
        f.write(_dump_yaml(obj))


def load_data(yaml_path):
    """Load audit data. Uses JSON companion file (always present after dump)."""
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
#  Existing-header classification
# =============================================================================

# License detection patterns — checked in priority order, first match wins.
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


def _classify_existing_header(content, our_owner, our_license):
    """Scan the first 8KB of *content* and classify any existing copyright header.

    Returns (category, detail_dict) where category is one of:
        'none'            — no copyright found, safe to add our header
        'ours'            — same license as repo + same owner
        'other_owner'     — same license as repo but different copyright owner
        'other_license'   — copyright present with a different license
        'unlicensed'      — copyright present but no detectable license grant

    *our_license* is the repo's license_id (e.g. 'apache', 'mit', 'bsd3').
    """
    head = content[:8192]

    if not _COPYRIGHT_ANY.search(head):
        return "none", {}

    # Detect copyright owner + year
    m = _COPYRIGHT_RE.search(head)
    detected_owner = m.group(2).strip() if m else "unknown"
    detected_year = m.group(1) if m else "unknown"

    # Detect license type
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


def _extract_snippet(content):
    """Extract the first meaningful lines (max 12) from content for preview."""
    lines = content.split("\n")
    result = []
    started = False
    for line in lines:
        stripped = line.rstrip()
        if not started and stripped == "":
            continue  # skip leading blanks
        started = True
        result.append(stripped)
        if len(result) >= 12:
            break
    return "\n".join(result)


# =============================================================================
#  Copyright header definitions
# =============================================================================

HEADER_LINES = []

SKIP_PATTERNS = [
    "LICENSE",
    "go.sum",
    ".gitignore",
]

SKIP_EXTENSIONS = {
    ".json", ".png", ".jpg", ".jpeg", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot",
}

COMMENT_STYLE = {
    ".py":     '# prefix (after shebang if present)',
    ".yaml":   '# prefix',
    ".yml":    '# prefix',
    ".sh":     '# prefix (after shebang if present)',
    ".toml":   '# prefix',
    "":        '# prefix (Containerfile)',
    ".md":     '<!-- --> (after Hugo frontmatter if present)',
    ".html":   '{{/* */}} Go template comment',
    ".gotmpl": '{{/* */}} Go template comment',
    ".scss":   '/* */ block',
    ".go":     '// prefix',
    ".mod":    '// prefix',
}

# Human-readable names for each license_id.
_LICENSE_NAMES = {
    "apache": "Apache 2.0",
    "mit":    "MIT",
    "bsd3":   "BSD 3-Clause",
    "gpl":    "GPL",
    "mpl":    "MPL 2.0",
}

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


# Dispatch table — used by build_header_lines() and _detect_repo_license()
_HEADER_TEMPLATES = {
    "apache": _apache_header,
    "mit":    _mit_header,
    "bsd3":   _bsd3_header,
}


def build_header_lines(year, owner, license_id="apache"):
    """Return the list of header lines for *license_id*."""
    fn = _HEADER_TEMPLATES.get(license_id)
    if fn is None:
        print(f"  warning: unknown license '{license_id}', falling back to Apache 2.0",
              file=sys.stderr)
        fn = _apache_header
    return fn(year, owner)


def license_name(license_id):
    """Human-readable name for a license_id."""
    return _LICENSE_NAMES.get(license_id, license_id)


# === Repo-level license detection ===

_LICENSE_FILE_PATTERNS = [
    # (license_id, regex) — checked in priority order
    ("apache", re.compile(r'Apache License|Apache-2\.0', re.I)),
    ("mit",    re.compile(r'MIT License|permission is hereby granted, free of charge',
                          re.I)),
    ("gpl",    re.compile(r'GNU General Public|General Public License', re.I)),
    ("bsd3",   re.compile(r'BSD|Redistribution and use in source and binary forms', re.I)),
    ("mpl",    re.compile(r'Mozilla Public License|MPL', re.I)),
]


def _detect_repo_license(repo_root):
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

def make_comment_block(prefix, prefix_blank=""):
    lines = []
    for line in HEADER_LINES:
        if line == "":
            lines.append(prefix_blank if prefix_blank else prefix.rstrip())
        else:
            lines.append(f"{prefix}{line}")
    return "\n".join(lines) + "\n"


def block_comment(_lines, start, end):
    body = []
    for line in HEADER_LINES:
        if line == "":
            body.append("")
        else:
            body.append(f" {line}")
    return "\n".join([start] + body + [f" {end}"]) + "\n"


# =============================================================================
#  File classification
# =============================================================================

def classify_ext(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".disabled":
        return ".yaml"
    if ext and ext[1:].replace(".", "").isdigit():
        return ""
    return ext


def get_header(filepath):
    ext = classify_ext(filepath)

    if ext in {".py", ".yaml", ".yml", ".sh", ".toml"} or ext == "":
        header = make_comment_block("# ")
        if ext in {".py", ".sh"} or ext == "":
            try:
                with open(filepath, "r") as f:
                    first_line = f.readline()
                if first_line.startswith("#!"):
                    with open(filepath, "r") as f:
                        f.readline()
                        second_line = f.readline()
                    return header, 2 if second_line == "\n" else 1
            except (IOError, OSError):
                pass
        return header, 0

    if ext == ".md":
        try:
            with open(filepath, "r") as f:
                first_line = f.readline()
            if first_line.strip() == "---":
                with open(filepath, "r") as f:
                    f.readline()
                    line_count = 1
                    for line in f:
                        line_count += 1
                        if line.strip() == "---":
                            break
                return block_comment(HEADER_LINES, "<!--", "-->"), line_count
        except (IOError, OSError):
            pass
        return block_comment(HEADER_LINES, "<!--", "-->"), 0

    if ext in {".html", ".gotmpl"}:
        return block_comment(HEADER_LINES, "{{/*", "*/}}"), 0

    if ext == ".scss":
        return block_comment(HEADER_LINES, "/*", "*/"), 0

    if ext in {".go", ".mod"}:
        return make_comment_block("// "), 0

    return None, 0


def should_skip(filepath):
    basename = os.path.basename(filepath)
    ext = os.path.splitext(filepath)[1].lower()
    if basename in SKIP_PATTERNS:
        return True
    if ext in SKIP_EXTENSIONS:
        return True
    return False


def add_header_to_file(filepath, dry_run=False):
    header, insert_line = get_header(filepath)
    if header is None:
        return "unknown_type", 0

    try:
        with open(filepath, "r") as f:
            original = f.read()
    except (IOError, OSError) as e:
        return f"error: {e}", 0

    hdr_lines = header.count("\n")

    if insert_line == 0:
        new_content = header + "\n" + original
    else:
        lines = original.splitlines(keepends=True)
        new_content = "".join(
            lines[:insert_line] + ["\n", header, "\n"] + lines[insert_line:]
        )

    new_content = new_content.rstrip("\n") + "\n"

    if new_content == original:
        return "unchanged", 0

    if dry_run:
        return "would_add", hdr_lines

    with open(filepath, "w") as f:
        f.write(new_content)
    return "added", hdr_lines


# =============================================================================
#  Repo scan — returns the full audit data dict
# =============================================================================

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


def _git_info(repo_root):
    """Return (remote, commit, branch)."""
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


def _org_repo(remote, fallback_name):
    if not remote:
        return f"local/{fallback_name}"
    # Normalise SSH URLs: git@github.com:org/repo -> github.com/org/repo
    url = remote
    if "@" in url and ":" in url:
        url = url.split("@", 1)[1]          # github.com:org/repo
        url = url.replace(":", "/", 1)       # github.com/org/repo
    # Now extract the last two path segments
    parts = url.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return f"local/{fallback_name}"


def _detect_edge_cases(all_files):
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
                with open(f, "r") as fh:
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
                with open(f, "r") as fh:
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


def scan_repo(directory, year, owner, dry_run, license_id=None):
    repo_root = os.path.abspath(directory)
    if not os.path.isdir(repo_root):
        sys.exit(f"error: not a directory: {repo_root}")

    # Auto-detect repo license if not overridden
    lic_id, lic_name = (_detect_repo_license(repo_root)
                        if license_id is None
                        else (license_id, license_name(license_id)))

    global HEADER_LINES
    HEADER_LINES[:] = build_header_lines(year, owner, lic_id)

    remote, commit, branch = _git_info(repo_root)
    basename = os.path.basename(repo_root.rstrip("/"))
    org_repo = _org_repo(remote, basename)

    # git ls-files relative to repo root
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, check=True, cwd=repo_root
    )
    all_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

    stats = {"added": 0, "skipped": 0, "already_ours": 0,
             "other_owner": 0, "other_license": 0, "unlicensed": 0,
             "unknown_type": 0, "error": 0}
    skipped_files = []
    error_files = []
    other_owner_files = []    # {path, owner, year, snippet}
    other_license_files = []  # {path, license, snippet}
    unlicensed_files = []     # {path, snippet}
    file_type_counts = {}
    lines_added = 0

    for filepath in all_files:
        fullpath = os.path.join(repo_root, filepath)

        if should_skip(filepath):
            stats["skipped"] += 1
            skipped_files.append({"path": filepath, "reason": _skip_reason(filepath)})
            continue

        ext = classify_ext(fullpath)

        # Read content once for classification
        try:
            with open(fullpath, "r") as f:
                head_content = f.read(8192)
        except (IOError, OSError):
            stats["error"] += 1
            error_files.append({"path": filepath, "error": "unreadable"})
            continue

        cat, detail = _classify_existing_header(head_content, owner, lic_id)

        if cat == "ours":
            stats["already_ours"] += 1
            ft = file_type_counts.setdefault(ext, {"count": 0, "style": COMMENT_STYLE.get(ext, "—")})
            ft["count"] += 1
            continue

        if cat == "other_owner":
            stats["other_owner"] += 1
            other_owner_files.append({"path": filepath, "owner": detail.get("owner", "?"),
                                       "year": detail.get("year", "?"),
                                       "snippet": detail.get("snippet", "")})
            ft = file_type_counts.setdefault(ext, {"count": 0, "style": COMMENT_STYLE.get(ext, "—")})
            ft["count"] += 1
            continue

        if cat == "other_license":
            stats["other_license"] += 1
            other_license_files.append({"path": filepath, "license": detail.get("license", "?"),
                                         "snippet": detail.get("snippet", "")})
            ft = file_type_counts.setdefault(ext, {"count": 0, "style": COMMENT_STYLE.get(ext, "—")})
            ft["count"] += 1
            continue

        if cat == "unlicensed":
            stats["unlicensed"] += 1
            unlicensed_files.append({"path": filepath, "snippet": detail.get("snippet", "")})
            ft = file_type_counts.setdefault(ext, {"count": 0, "style": COMMENT_STYLE.get(ext, "—")})
            ft["count"] += 1
            continue

        # cat == "none" — safe to add our header
        res, hdr_lines = add_header_to_file(fullpath, dry_run=dry_run)
        if res in ("added", "would_add"):
            stats["added"] += 1
            ft = file_type_counts.setdefault(ext, {"count": 0, "style": COMMENT_STYLE.get(ext, "—")})
            ft["count"] += 1
            lines_added += hdr_lines
        elif res == "unknown_type":
            stats["unknown_type"] += 1
        elif res.startswith("error"):
            stats["error"] += 1
            error_files.append({"path": filepath, "error": res})
        else:
            stats["skipped"] += 1

    edge_cases = _detect_edge_cases(
        [os.path.join(repo_root, f) for f in all_files]
    )

    return {
        "repo": {
            "name": basename,
            "org_repo": org_repo,
            "remote": remote,
            "commit": commit,
            "branch": branch,
            "root": repo_root,
        },
        "scan": {
            "date": datetime.date.today().isoformat(),
            "dry_run": dry_run,
            "year": year,
            "owner": owner,
            "license": lic_id,
            "license_name": lic_name,
        },
        "stats": stats,
        "lines_added": lines_added,
        "file_types": file_type_counts,
        "skipped": skipped_files,
        "errors": error_files,
        "edge_cases": edge_cases,
        "other_owner": other_owner_files,
        "other_license": other_license_files,
        "unlicensed": unlicensed_files,
    }


# =============================================================================
#  HTML generator — pure function over the audit data dict
# =============================================================================

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _to_web_url(remote):
    """Convert a git remote URL to a browser-friendly web URL."""
    if "@" in remote and ":" in remote:
        host_path = remote.split("@", 1)[1]         # github.com:org/repo
        host, _, path = host_path.partition(":")     # github.com, org/repo
        return f"https://{host}/{path}"
    if remote.startswith("http"):
        return remote
    return remote


def generate_html_section(data, section_num):
    repo             = data["repo"]
    stats            = data["stats"]
    skipped          = data["skipped"]
    errors           = data["errors"]
    ftypes           = data["file_types"]
    edge             = data["edge_cases"]
    other_owner      = data.get("other_owner", [])
    other_license    = data.get("other_license", [])
    unlicensed       = data.get("unlicensed", [])
    scan             = data.get("scan", {})
    lic_id           = scan.get("license", "apache")
    lic_display      = scan.get("license_name", "Apache 2.0")

    # -- health tag -------------------------------------------------------
    tag_class, tag_label = "green", "clean"
    if stats.get("error", 0) > 0 or len(other_license) > 0:
        tag_class, tag_label = "red", "issues"
    elif stats.get("other_owner", 0) > 0 or len(unlicensed) > 0 or stats.get("unknown_type", 0) > 0:
        tag_class, tag_label = "amber", "warnings"

    conflict_n = len(other_owner) + len(other_license)
    suspicion_n = len(unlicensed)

    # -- metadata line ----------------------------------------------------
    meta_parts = []
    if repo.get("remote"):
        web = _to_web_url(repo["remote"])
        meta_parts.append(
            f'<a href="{esc(web)}">{esc(repo["remote"])}</a>'
        )
    if repo.get("commit"):
        meta_parts.append(f'commit <code>{esc(repo["commit"])}</code>')
    if repo.get("branch"):
        meta_parts.append(f'branch <code>{esc(repo["branch"])}</code>')
    meta_html = " &nbsp;·&nbsp; ".join(meta_parts)
    if meta_html:
        meta_html = "&nbsp; " + meta_html

    # -- file type rows ---------------------------------------------------
    type_rows = []
    for ext in sorted(ftypes, key=lambda e: -ftypes[e]["count"]):
        ft = ftypes[ext]
        display = ext if ext else "no-ext"
        type_rows.append(
            f'<tr><td><code>{esc(display)}</code></td>'
            f'<td>{ft["style"]}</td>'
            f'<td class="count">{ft["count"]}</td></tr>'
        )

    # -- skipped rows -----------------------------------------------------
    skipped_rows = []
    for f in skipped:
        skipped_rows.append(
            f'<li><code>{esc(f["path"])}</code> — {f.get("reason", "")}</li>'
        )

    # -- already-ours rows -------------------------------------------------
    already_n = stats.get("already_ours", 0)

    # -- other-owner rows --------------------------------------------------
    other_owner_rows = []
    for f in other_owner:
        other_owner_rows.append(
            f'<li><code>{esc(f["path"])}</code> — '
            f'owner: <strong>{esc(f.get("owner", "?"))}</strong>, '
            f'year: {esc(f.get("year", "?"))}</li>'
        )

    # -- other-license rows ------------------------------------------------
    other_license_rows = []
    for f in other_license:
        snippet_preview = ""
        if f.get("snippet"):
            first_line = f["snippet"].split("\n")[0][:100]
            snippet_preview = f' — <code>{esc(first_line)}</code>'
        other_license_rows.append(
            f'<li><code>{esc(f["path"])}</code> — '
            f'license: <strong>{esc(f.get("license", "?"))}</strong>{snippet_preview}</li>'
        )

    # -- unlicensed rows ---------------------------------------------------
    unlicensed_rows = []
    for f in unlicensed:
        snippet_preview = ""
        if f.get("snippet"):
            first_line = f["snippet"].split("\n")[0][:100]
            snippet_preview = f' — <code>{esc(first_line)}</code>'
        unlicensed_rows.append(
            f'<li><code>{esc(f["path"])}</code>{snippet_preview}</li>'
        )

    # -- edge case rows ---------------------------------------------------
    edge_rows = []
    for e in edge:
        edge_rows.append(
            f'<li><strong>{esc(e["label"])}</strong>: {e["detail"]}</li>'
        )

    # -- error rows -------------------------------------------------------
    error_rows = []
    for e in errors:
        error_rows.append(
            f'<li><code>{esc(e["path"])}</code>: {esc(e.get("error", ""))}</li>'
        )

    # -- assemble ---------------------------------------------------------
    lines = []

    lines.append(f'<h2>{section_num}. {esc(repo["org_repo"])} ({esc(lic_display)})</h2>')
    lines.append('<div class="card">')
    lines.append('')
    lines.append('  <div class="section-header">')
    lines.append('    <div>')
    lines.append(f'      <span class="project-name">{esc(repo["name"])}</span>')
    lines.append(f'      <span class="project-meta">')
    lines.append(f'        {meta_html}')
    lines.append(f'      </span>')
    lines.append('    </div>')
    lines.append(f'    <span class="tag {tag_class}">{tag_label}</span>')
    lines.append('  </div>')
    lines.append('')
    lines.append('  <div class="stat-row">')
    lines.append('    <div class="stat">')
    lines.append(f'      <span class="stat-val ok">{stats["added"]}</span>')
    lines.append(f'      <span class="stat-lbl">Headers Added</span>')
    lines.append('    </div>')
    lines.append('    <div class="stat">')
    lines.append(f'      <span class="stat-val">{stats["skipped"]}</span>')
    lines.append(f'      <span class="stat-lbl">Skipped</span>')
    lines.append('    </div>')
    lines.append('    <div class="stat">')
    lines.append(f'      <span class="stat-val ok">{already_n}</span>')
    lines.append(f'      <span class="stat-lbl">Already Compliant</span>')
    lines.append('    </div>')
    lines.append('    <div class="stat">')
    lines.append(f'      <span class="stat-val ok">{conflict_n}</span>')
    lines.append(f'      <span class="stat-lbl">Conflicts</span>')
    lines.append('    </div>')
    lines.append('    <div class="stat">')
    lines.append(f'      <span class="stat-val ok">{suspicion_n}</span>')
    lines.append(f'      <span class="stat-lbl">Unlicensed</span>')
    lines.append('    </div>')
    lines.append('    <div class="stat">')
    lines.append(f'      <span class="stat-val">{data["lines_added"]:,}</span>')
    lines.append(f'      <span class="stat-lbl">Lines Added</span>')
    lines.append('    </div>')
    lines.append('  </div>')
    lines.append('')
    lines.append('  <h3>By File Type</h3>')
    lines.append('  <table>')
    lines.append('    <thead><tr><th>Extension</th><th>Comment Style</th><th class="count">Count</th></tr></thead>')
    lines.append('    <tbody>')
    lines.extend(f'      {r}' for r in type_rows)
    lines.append('    </tbody>')
    lines.append('  </table>')
    lines.append('')
    lines.append('  <details class="subsection">')
    lines.append(f'    <summary>Skipped Files ({len(skipped)})</summary>')
    lines.append('    <ul class="skip-list">')
    lines.extend(f'      {r}' for r in skipped_rows)
    lines.append('    </ul>')
    lines.append('  </details>')

    if error_rows:
        lines.append('')
        lines.append('  <details class="subsection">')
        lines.append(f'    <summary>Errors ({len(errors)})</summary>')
        lines.append('    <ul class="issues">')
        lines.extend(f'      {r}' for r in error_rows)
        lines.append('    </ul>')
        lines.append('  </details>')

    # Already Compliant
    if already_n > 0:
        lines.append('')
        lines.append('  <details class="subsection">')
        lines.append(f'    <summary>Already Compliant ({already_n})</summary>')
        lines.append(f'    <p class="none">These files already carry our {lic_display} header — no changes needed.</p>')
        lines.append('  </details>')

    # Wrong Owner (conflict: same license but different copyright holder)
    if other_owner_rows:
        lines.append('')
        lines.append('  <details class="subsection">')
        lines.append(f'    <summary>Wrong Owner ({len(other_owner)})</summary>')
        lines.append(f'    <p>These files carry a {lic_display} header but attribute copyright to a different owner. '
                     f'Review and decide whether to replace with our header.</p>')
        lines.append('    <ul class="issues">')
        lines.extend(f'      {r}' for r in other_owner_rows)
        lines.append('    </ul>')
        lines.append('  </details>')

    # Other License (conflict: different license)
    if other_license_rows:
        lines.append('')
        lines.append('  <details class="subsection">')
        lines.append(f'    <summary>Other License ({len(other_license)})</summary>')
        lines.append(f'    <p>These files carry copyright under a <strong>non-{lic_display}</strong> license. '
                     f'They may be third-party code — do NOT blindly add our header.</p>')
        lines.append('    <ul class="issues">')
        lines.extend(f'      {r}' for r in other_license_rows)
        lines.append('    </ul>')
        lines.append('  </details>')

    # Unlicensed Copyright (suspicion: copyright found, no license grant)
    if unlicensed_rows:
        lines.append('')
        lines.append('  <details class="subsection">')
        lines.append(f'    <summary>Unlicensed Copyright ({len(unlicensed)})</summary>')
        lines.append(f'    <p>These files contain a copyright notice but no detectable license grant. '
                     f'Ambiguous — may need manual review.</p>')
        lines.append('    <ul class="issues">')
        lines.extend(f'      {r}' for r in unlicensed_rows)
        lines.append('    </ul>')
        lines.append('  </details>')

    # Conflicts summary
    conflict_body = ""
    if conflict_n == 0:
        conflict_body = (
            '<p class="none">None. Zero existing copyright or license headers '
            'found in any source file prior to this pass.</p>'
        )
    else:
        conflict_body = (
            f'<p>{conflict_n} file(s) with existing headers that may need attention — '
            f'see details above for Wrong Owner and Other License.</p>'
        )

    lines.append('')
    lines.append('  <details class="subsection">')
    lines.append(f'    <summary>Conflicts Detail ({conflict_n})</summary>')
    lines.append(f'    {conflict_body}')
    lines.append('  </details>')

    # Suspicion summary
    suspicion_body = ""
    if suspicion_n == 0:
        suspicion_body = (
            '<p class="none">None. No unlicensed copyright notices detected.</p>'
        )
    else:
        suspicion_body = (
            f'<p>{suspicion_n} file(s) with copyright notices but no detectable license grant — '
            f'see Unlicensed Copyright above.</p>'
        )

    lines.append('')
    lines.append('  <details class="subsection">')
    lines.append(f'    <summary>Discrepancies / Suspicions ({suspicion_n})</summary>')
    lines.append(f'    {suspicion_body}')
    lines.append('  </details>')

    if edge_rows:
        lines.append('')
        lines.append('  <details class="subsection">')
        lines.append(f'    <summary>Edge Cases Handled ({len(edge_rows)})</summary>')
        lines.append('    <ul class="issues">')
        lines.extend(f'      {r}' for r in edge_rows)
        lines.append('    </ul>')
        lines.append('  </details>')

    lines.append('')
    lines.append('</div>')

    return "\n".join(lines) + "\n"


def append_html_to_report(report_path, html_section):
    if os.path.exists(report_path):
        with open(report_path, "r") as f:
            report = f.read()
        marker = "</body>"
        if marker in report:
            report = report.replace(marker, html_section + "\n" + marker, 1)
        else:
            report += "\n" + html_section
        with open(report_path, "w") as f:
            f.write(report)
    else:
        today = datetime.date.today().isoformat()
        skeleton = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Copyright Header Audit Report</title>
<link rel="stylesheet" href="copyright-audit-report.html">
</head>
<body>
<h1>Copyright Header Audit <small>— &nbsp; report</small></h1>
<p class="meta">Generated {today} &nbsp;·&nbsp; Script: <code>add_copyright.py</code> &nbsp;·&nbsp; License: Apache 2.0</p>

{html_section}
</body>
</html>
"""
        with open(report_path, "w") as f:
            f.write(skeleton)


# =============================================================================
#  main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Add copyright headers to all source files in a git repo."
    )
    parser.add_argument(
        "directory", nargs="?", default=None,
        help="Path to the git repository"
    )
    parser.add_argument("--year", default="2026")
    parser.add_argument("--owner", default="FlagOS Contributors")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--license", dest="license_id", default=None,
                        choices=["apache", "mit", "bsd3", "gpl", "mpl"],
                        help="License to use (default: auto-detect from LICENSE file)")
    # data IO
    parser.add_argument("--from-yaml", metavar="FILE",
                        help="Load audit data from a prior YAML dump (skip repo scan)")
    parser.add_argument("--yaml", metavar="FILE",
                        help="Dump structured audit data to YAML (+ .json companion)")
    # HTML
    parser.add_argument("--html-report", metavar="REPORT.html",
                        help="Append HTML section to the audit report file")
    parser.add_argument("--html-stdout", action="store_true",
                        help="Print HTML section to stdout")
    parser.add_argument("--section-num", type=int, default=None,
                        help="Section number (auto-detected from existing report)")

    args = parser.parse_args()

    data = None

    # --- load or scan ----------------------------------------------------
    if args.from_yaml:
        data = load_data(args.from_yaml)
    elif args.directory:
        data = scan_repo(args.directory, args.year, args.owner, args.dry_run, args.license_id)
        if args.yaml:
            dump_data(data, args.yaml)
            print(f"Audit data → {args.yaml} (+ .json)")
    else:
        parser.error("specify a directory to scan, or --from-yaml to load existing data")

    if data is None:
        return

    # --- console summary (scan mode only) --------------------------------
    if not args.from_yaml:
        s = data["stats"]
        scan = data.get("scan", {})
        lic_display = scan.get("license_name", "Apache 2.0")
        print(f"\n=== {data['repo']['root']} ({lic_display}) ===\n")
        print(f"--- Summary {'(DRY RUN)' if args.dry_run else ''} ---")
        print(f"  Added:          {s['added']}")
        print(f"  Skipped:        {s['skipped']}")
        print(f"  Already ours:   {s.get('already_ours', 0)}")
        if s.get("other_owner"):
            print(f"  Wrong owner:    {s['other_owner']}")
        if s.get("other_license"):
            print(f"  Other license:  {s['other_license']}")
        if s.get("unlicensed"):
            print(f"  Unlicensed:     {s['unlicensed']}")
        if s.get("unknown_type"):
            print(f"  Unknown type:   {s['unknown_type']}")
        if s.get("error"):
            print(f"  Errors:         {s['error']}")
        if data["errors"]:
            print("\nErrors:")
            for e in data["errors"]:
                print(f"  {e['path']}: {e['error']}")

    # --- HTML output -----------------------------------------------------
    if args.html_report or args.html_stdout:
        if args.section_num:
            sec = args.section_num
        elif args.html_report and os.path.exists(args.html_report):
            with open(args.html_report) as f:
                sec = f.read().count("<h2>") + 1
        else:
            sec = 1

        html = generate_html_section(data, sec)

        if args.html_stdout:
            print(html)

        if args.html_report:
            append_html_to_report(args.html_report, html)
            print(f"\nHTML section → {args.html_report}")


if __name__ == "__main__":
    main()
