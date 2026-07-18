#!/usr/bin/env python3
"""Generate an HTML audit report from copyright scan data.

Reads a YAML (or JSON) audit data file produced by scan_headers.py and
appends a formatted HTML section to a report file, or prints it to stdout.

Usage:
    python3 gen_report.py audit.yaml --html-report report.html
    python3 gen_report.py audit.yaml --html-stdout
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


# =============================================================================
#  HTML helpers
# =============================================================================

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _to_web_url(remote):
    if "@" in remote and ":" in remote:
        host_path = remote.split("@", 1)[1]
        host, _, path = host_path.partition(":")
        return f"https://{host}/{path}"
    if remote.startswith("http"):
        return remote
    return remote


# =============================================================================
#  Section generator
# =============================================================================

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

    if already_n > 0:
        lines.append('')
        lines.append('  <details class="subsection">')
        lines.append(f'    <summary>Already Compliant ({already_n})</summary>')
        lines.append(f'    <p class="none">These files already carry our {lic_display} header — no changes needed.</p>')
        lines.append('  </details>')

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


# =============================================================================
#  Report-file writer
# =============================================================================

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
<p class="meta">Generated {today} &nbsp;·&nbsp; Script: <code>gen_report.py</code> &nbsp;·&nbsp; Report: License Audit</p>

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
        description="Generate HTML audit report from scan data."
    )
    parser.add_argument("yaml_file", help="Audit data file (YAML or JSON companion)")
    parser.add_argument("--html-report", metavar="REPORT.html",
                        help="Append HTML section to the report file")
    parser.add_argument("--html-stdout", action="store_true",
                        help="Print HTML section to stdout")
    parser.add_argument("--section-num", type=int, default=None,
                        help="Section number (auto-detected from existing report)")

    args = parser.parse_args()

    data = lib.load_data(args.yaml_file)

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
        print(f"HTML section → {args.html_report}")


if __name__ == "__main__":
    main()
