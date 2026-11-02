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

"""Check the agent knowledge layer's indexes against the tree.

The repo states four index rules; nothing enforced them, and each rots
silently — a new workflow missing from CLAUDE.md, a skill pointing at a moved
file, a document no one can reach from any index, a vendor with no page.
Each rule is checked as its reader would apply it, not as a file linter would:

1. CLAUDE.md's workflow table names every workflow file and no deleted one.
   Only the table's file column counts; prose cells mention other workflow
   names for context.
2. .claude/skills/ and CLAUDE.md's skill table name the same set, every
   frontmatter name equals its directory, and every repo path a skill
   backticks exists.
3. Every tracked document is mentioned somewhere. Generated trees are out:
   gen_descriptions.py owns them, and its provenance marker already guards
   hand-written pages in the same directories. A document counts as mentioned
   by its full path, by a markdown link that resolves to it, by its basename
   when that basename is unique among documents, or — for the per-directory
   files (README/index/decisions/playbook/workbook/DESIGN) — by its directory.
4. docs/vendors/ holds exactly one page per configs.yaml vendor, and
   docs/vendors/README.md links every one of them.

Usage: python3 scripts/docs/check_knowledge.py
Exit status 1 with one line per problem when any rule fails.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

# Files whose content gen_descriptions.py or the Hugo site owns. docs/README.md
# scopes the site's rules out of the knowledge layer's reach.
GENERATED = re.compile(
    r"^(docs/(content|public|resources|assets|layouts|i18n|archetypes)/"
    r"|base/[^/]+\.md$|runtime/[^/]+\.md$|app/[^/]+/[^/]+\.md$"
    r"|\.claude/skills/[^/]+/SKILL\.md$)"
)

# Repeated once per directory, so they are addressed by directory rather than
# by an ambiguous basename.
PER_DIRECTORY = {
    "README.md",
    "index.md",
    "decisions.md",
    "playbook.md",
    "workbook.md",
    "DESIGN.md",
}

TEXT_SUFFIXES = {".md", ".py", ".sh", ".yml", ".yaml", ".txt", ".toml", ".cfg"}

REPO_TOPS = {
    "docs", "packaging", "scripts", "app", "base", "runtime",
    "configs.yaml", "CLAUDE.md", ".github", ".claude",
}


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode()
    return [p for p in out.split("\0") if p]


def read(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(errors="ignore")
    except OSError:
        return ""


def claude_table(start: str, end: str) -> list[str]:
    """Rows of the markdown table between two CLAUDE.md headings."""
    text = read("CLAUDE.md")
    if start not in text:
        return []
    body = text.split(start, 1)[1]
    if end in body:
        body = body.split(end, 1)[0]
    return [line for line in body.splitlines() if line.startswith("| `")]


def check_workflow_table() -> list[str]:
    listed: set[str] = set()
    for row in claude_table("### CI workflows", "### Runners"):
        listed |= set(re.findall(r"`([\w.-]+\.ya?ml)`", row.split("|")[1]))
    on_disk = {
        p.name
        for p in (ROOT / ".github" / "workflows").iterdir()
        if p.suffix in (".yml", ".yaml")
    }
    return [
        f"CLAUDE.md workflow table: {n} is missing"
        for n in sorted(on_disk - listed)
    ] + [
        f"CLAUDE.md workflow table: {n} no longer exists"
        for n in sorted(listed - on_disk)
    ]


def check_skills() -> list[str]:
    problems: list[str] = []
    skills = sorted(p.name for p in (ROOT / ".claude" / "skills").iterdir() if p.is_dir())

    listed: set[str] = set()
    for row in claude_table("| Skill | Trigger | Docs entry |", "Loading discipline"):
        listed |= set(re.findall(r"`([a-z0-9-]+)`", row.split("|")[1]))
    problems += [f"CLAUDE.md skill table: {s} is missing" for s in skills if s not in listed]
    problems += [
        f"CLAUDE.md skill table: {s} has no directory"
        for s in sorted(listed)
        if s not in skills
    ]

    for skill in skills:
        rel = f".claude/skills/{skill}/SKILL.md"
        text = read(rel)
        front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not front:
            problems.append(f"{rel}: no frontmatter")
            continue
        name = re.search(r"^name:\s*(\S+)\s*$", front.group(1), re.M)
        if not name or name.group(1) != skill:
            got = name.group(1) if name else "missing"
            problems.append(f"{rel}: frontmatter name {got} != directory {skill}")

        # A backticked token whose first segment is a repo top-level is a path
        # claim. Templates (<vendor>, {a,b}), options and device paths are not.
        for token in re.findall(r"`([^`\n]+)`", text):
            base = token.split()[0] if token.split() else ""
            if not base or base.startswith(("-", "/", "~")):
                continue
            if any(c in base for c in "<>{}*$"):
                continue
            if base.split("/")[0] not in REPO_TOPS:
                continue
            if not (ROOT / base).exists():
                problems.append(f"{rel}: path {base} does not exist")
    return problems


def normalized_links(doc: str, body: str) -> set[str]:
    """Repo-relative targets of a document's markdown links, clamped at root."""
    out: set[str] = set()
    parent = Path(doc).parent
    for target in re.findall(r"\]\(([^)\s]+)\)", body):
        target = target.split("#", 1)[0]
        if not target or target.startswith(("http", "mailto")):
            continue
        parts: list[str] = []
        for seg in (parent / target).parts:
            if seg == "..":
                if parts:
                    parts.pop()
            elif seg not in (".", ""):
                parts.append(seg)
        out.add("/".join(parts))
    return out


def check_orphan_docs(tracked: list[str]) -> list[str]:
    docs = [t for t in tracked if t.endswith(".md") and not GENERATED.match(t)]
    corpus = {t: read(t) for t in tracked if Path(t).suffix in TEXT_SUFFIXES}
    links = {t: normalized_links(t, b) for t, b in corpus.items() if t.endswith(".md")}
    basenames = Counter(Path(t).name for t in docs)

    problems = []
    for doc in docs:
        path = Path(doc)
        referenced = False
        for other, body in corpus.items():
            if other == doc:
                continue
            if (
                doc in body
                or doc in links.get(other, ())
                or (basenames[path.name] == 1 and path.name in body)
                or (path.name in PER_DIRECTORY and f"{path.parent.as_posix()}/" in body)
            ):
                referenced = True
                break
        if not referenced:
            problems.append(
                f"{doc}: unreachable — no document mentions it or its directory "
                f"(link it from its directory's index)"
            )
    return problems


def check_vendor_pages() -> list[str]:
    vendors = set(yaml.safe_load(read("configs.yaml"))["vendors"])
    pages = {p.stem for p in (ROOT / "docs" / "vendors").glob("*.md")} - {"README"}
    readme = read("docs/vendors/README.md")
    return (
        [f"docs/vendors/{v}.md: missing" for v in sorted(vendors - pages)]
        + [f"docs/vendors/{v}.md: no such vendor in configs.yaml" for v in sorted(pages - vendors)]
        + [
            f"docs/vendors/{v}.md: not linked from docs/vendors/README.md"
            for v in sorted(pages)
            if f"{v}.md" not in readme
        ]
    )


def main() -> None:
    tracked = tracked_files()
    problems = (
        check_workflow_table()
        + check_skills()
        + check_orphan_docs(tracked)
        + check_vendor_pages()
    )
    for problem in problems:
        print(problem)
    if problems:
        sys.exit(f"\n{len(problems)} knowledge index problem(s)")
    print("knowledge index OK")


if __name__ == "__main__":
    main()
