---
name: lotusdocs-migration
description: Status and remaining steps for the docs site migration from hugo-book to Lotus Docs (Bootstrap 5)
metadata:
  type: project
---

Migrating the build-infra docs site (`docs/`, Hugo) from the **hugo-book** theme
to **Lotus Docs** (Bootstrap 5). Work is on branch **`lotusdocs-theme`**,
committed 2026-07-17. Not merged, not pushed.

## Done (all committed on lotusdocs-theme)
- Theme via **Hugo Modules** (not submodule): `docs/go.mod` imports
  `github.com/colinwilson/lotusdocs` + `hugo-mod-bootstrap-scss/v5`. hugo-book
  submodule + `.gitmodules` removed. CI (`hugo-site.yaml`) adds Go setup + drops
  submodule checkout.
- `docs/hugo.yaml` rewritten: Book* params → `params.docs`; `menus.after` →
  `menus.main`; `cascade: type: docs` handled in content; search disabled
  (`flexsearch.enabled: false`); empty `social: {}` to silence a warning.
- Content: removed duplicate leading `# H1` from hand-written `_index.md` (theme
  renders frontmatter title as the H1); richer body headings promoted into
  frontmatter `title`. Generated `base/*.md` leaves untouched.
- **5 template/style overrides** under `docs/layouts` + `docs/assets`:
  - `layouts/docs/list.html` — keep section `_index.md` prose + catalog tables
    (theme's default list renders only child cards).
  - `layouts/partials/docs/gitinfo.html` — fix "Edit this page" URL for the
    `docs/` subdir + `content/<lang>/` split.
  - `layouts/partials/docs/breadcrumbs.html` — make the Home crumb a real link.
  - `layouts/partials/docs/sidebar.html` — GLOBAL section tree (all top-level
    sections on every page; stock theme scopes to current section only). Uses
    theme-native `<button>`/`<a>` markup (NOT `<details>` — that broke styling
    consistency). Links use `.RelPermalink`.
  - `assets/docs/scss/custom/structure/_content.scss` — 15px base font; heading
    sizes h1 2rem / h2 1.5 / h3 1.25 / h4 1.1 / h5-h6 1rem (Bootstrap's default
    made h3 > h2); heading spacing 2rem top / 0.75 bottom; page-title 2rem +
    1.25rem gap before content; `pre code { background:none }` so inline-code
    style doesn't paint white over Prism code blocks.

## KEY GOTCHA — dead code box / preview server
Symptom "you broke the code box" (no syntax colors, no copy button) is NOT a
CSS/JS/sidebar bug — it's the dev server emitting the fingerprinted JS bundle at
the **absolute production URL** (`https://flagos-ai.github.io/...`) which 404s, so
no JS loads. See [[hugo-relative-links]] for the correct `hugo server` command
(`--baseURL "http://localhost:1313/release-info/" --appendPort=false`). Always
check the bundle `src` origin first.

## Open / next session
- User to eyeball final state: sidebar consistency (Vendors/Overview vs
  Base/Runtime) + sidebar expand/collapse reliability + code box.
- Verify sidebar toggle works via theme JS (earlier reported "flaky"; needs a
  real browser check, not curl).
- If all good: this is a PR off `lotusdocs-theme`. Then the pending Harbor/website
  release tasks in the other memories.
