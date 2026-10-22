# Documentation publication inventory

Audit base: `d4955f2b6b429355b626b2cc8b734ab59540db5f` (merged Sprint 2).
This inventory is repository-only and excluded from the product website.

`documentation-inventory.csv` lists **every file under docs/**, including assets,
raw HTML/YAML, training text and this inventory, plus root/developer Markdown and
LICENSE. Each row records its primary category, publication status, reason/code
evidence and, for existing paths, the SHA-256 of its base content. Categories:

1. Current TARS user documentation.
2. Current TARS developer documentation.
3. Required attribution/licensing.
4. Historical TARS engineering documentation.
5. Inherited upstream COVAS reference.
6. Obsolete or misleading material.

## Publication policy

`mkdocs.yml` uses supported MkDocs 1.6 `exclude_docs` patterns: exclude everything,
then admit the 21 reviewed public Markdown pages and the theme's `assets/` files.
Navigation lists those exact pages in seven groups, with at most four entries per
group. Excluded Markdown, HTML, YAML, ZIP, images and prompt corpora are neither
built nor copied; excluded text is absent from search. Adding nav alone would
not provide this boundary. Review any future additions under docs/assets too.

The inherited custom template is no longer selected: its upstream analytics ID
is not reused by the TARS manual. The original template remains in the repository.
The working GitHub Pages workflow, permissions and deployment settings are unchanged.
No site deployment is performed by this sprint.

## Retention and rewrites

- Current installation, FAQ, Observatory and MSI policy are retained. Installation
  gains the precise automated-versus-physical upgrade boundary; Observatory's
  settings path is aligned with the current UI.
- Landing/overview/first steps, providers, reactions/actions, plugins, contributing,
  support, credits and release readiness are rewritten as current TARS instructions.
- Voice, personality/memory, game-awareness, troubleshooting and development guides
  fill current product-manual gaps. The public license repeats the MIT text verbatim.
- Original actions/reactions/overview/contributing/support/credits are copied
  byte-for-byte into archive/upstream before replacement. Previous provider and
  release-readiness documents (including historical audits) are copied byte-for-byte
  into archive/sprints. All archive content is excluded from the website.
- Existing TARS phase/audit/engineering reports are unchanged and excluded. Existing
  generic upstream development, EDCoPilot, voice lists, AI-server, quests, XTTS,
  screenshots, bindings and training prompts are retained but excluded.
- The old interactive troubleshooting HTML is retained but excluded. Its YAML is
  replaced with safe TARS guidance; obsolete start-script/antivirus-bypass advice
  is not retained as a recommendation. The current public guide is troubleshooting.md.
- The archived upstream data-collection policy is excluded, not represented as a
  TARS privacy policy. Root LICENSE, security policy and all third-party notices
  are retained. Upstream contributions remain explicitly attributed in public credits.

## Verification

Run `mkdocs build --strict --site-dir /tmp/tars-manual-site`, then
`python docs/check_site.py /tmp/tars-manual-site` using the MkDocs environment.
The checker inspects generated HTML, local assets and anchors, page boundaries,
search membership and the license. It never publishes or contacts external sites.
External provider/legal/attribution URLs remain explicitly external references;
this checker does not certify availability of third-party services.

Strict-build warnings previously came from excluded runtime-hardening and upstream
plugin-development links. Those historical source documents remain unchanged.
No runtime, plugin, provider, UI, MSI/version policy, user profile or Pages workflow
is changed here. Full physical Windows/audio/Elite acceptance remains pending.

Measured local results for this revision: strict build passed with no MkDocs
link/navigation warnings; 21 selected public pages plus the generated 404 page;
806 internal link/asset/anchor checks passed. Chromium previews at 1440 and 390 px
verified the seven-group navigation, mobile menu interaction, guide navigation,
no horizontal overflow and no JavaScript errors. Seven sampled excluded legacy
URLs returned HTTP 404 from the local generated-site server. All eight snapshots
and existing historical/reference files matched the exact base bytes. The theme
prints an upstream future-MkDocs-version advisory, which does not fail strict mode.
