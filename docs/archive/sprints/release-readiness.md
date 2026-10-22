# Beta release approval and infrastructure

This is a release procedure, not a published beta announcement. No beta version,
tag or release has been approved by this document. RC20 is integrated into main;
automated Windows builds passed. Physical acceptance of a future beta remains
pending. The owner reports successful upgrades of earlier installations, which
is useful practical evidence but does not prove every MSI upgrade path.

## Version authority and MSI policy

The authoritative release version is the root `package.json` `version`.
`electron/package.json`, the root lockfile's top-level version and
`packages[""].version` are mirrors that CI now checks. No new version/config file
is introduced. They currently remain **0.0.0**, an unreleased placeholder.

Proposed convention: `MAJOR.MINOR.PATCH-beta.N`, starting with an owner-approved
candidate such as **0.5.0-beta.1**. This is an example, not a version assignment.
The corresponding future tag must be exactly `v<version>`. CI rejects mismatched
tags and placeholder `v0.0.0`. A future version-adoption PR must update the four
existing manifest/lock fields together; do not change `com.rex688.tars`, the
product name, executable name, user-data directory or MSI UpgradeCode derivation.

The [MSI policy and acceptance procedure](msi-versioning.md) maps semantic patch
and beta/stable rank into the third Windows Installer version field. The existing
0.0.0 installer identity/version is preserved. Beta adoption still requires review
of actual Windows MSI metadata and the disposable install/upgrade report, plus
physical acceptance; no package version is assigned here. The policy rejects
out-of-range or unsupported versions instead of allowing collisions.

## Existing pipeline and exact provenance

The existing workflow builds the backend, runs backend/bundle checks, builds the
UI/Electron app and MSI, validates the unpacked clean profile, runs E2E on a fresh
Windows VM and produces a portable ZIP. These steps and the packaging config are
retained. Temporary Actions artifacts remain SHA-named and expire after seven
days. A PR build SHA can be GitHub's synthetic merge commit; check its workflow
source/parents and tree rather than treating it as an unrelated source build.

Only a **future approved tag push** may enter the existing draft-release job;
a workflow dispatch on a tag cannot create a draft release. That job still
requires successful Electron packaging, E2E and real MSI upgrade acceptance. It checks out the tagged source,
checks matching package/tag versions and verifies that HEAD and the peeled tag
commit equal the workflow SHA. Both producer and release staging require x64.
Downloaded MSI/ZIP selection must yield exactly one of each.

Official staged asset names are:

- `TARS-<version>-windows-x64.msi`
- `TARS-<version>-windows-x64-portable.zip`
- `release-provenance.json` (version, mapped MSI ProductVersion/UpgradeCode, tag,
  full source commit, workflow URL, architecture, exact plugin pin and asset hashes)
- `SHA256SUMS.txt` (MSI, ZIP and provenance file digests)

This is source traceability and artifact verification, not a claim of bit-for-bit
reproducible binaries: hosted runner images, `node-version: lts/*`, dependency
installation and build tools still have mutable inputs. No dependencies or build
tool versions are changed in this sprint. Artifact names do not alter MSI metadata.

The GitHub token is read-only outside the existing release job, where contents
write is required. Creation uses `--verify-tag --draft`; beta tags additionally
set the prerelease flag. A published release is refused. An existing draft may
receive missing assets, but existing assets are never overwritten (`--clobber`
is removed); a duplicate-name retry fails for manual review. Do not delete/retry
assets automatically. The draft state is rechecked immediately before upload.
Do not publish or otherwise edit the draft while the job is running: GitHub's
separate state-check/upload calls are not an atomic publication lock. Existing
draft version/channel and checksums must be reviewed before any manual publication.

## Owner approval checklist (future action only)

1. Approve the semantic version and Windows MSI upgrade strategy in a separate
   review; inspect ProductVersion/UpgradeCode and test old-to-new installation.
2. Merge reviewed release infrastructure/version changes; require green Windows,
   security, packaging and E2E checks on the exact candidate source.
3. Back up the private TARS profile. Complete Windows 11 install, launch, audio,
   providers, Elite, Explorer/Chatter, memory, vision and TTS acceptance. Record
   outcomes; mocked tests and the owner's previous upgrades are not substitutes.
4. Explicitly approve the exact commit and `v<version>` tag. An authorized owner
   may then push that tag; this sprint creates no tags, draft releases or assets.
5. Wait for the tag workflow, inspect the draft, source/provenance, architecture,
   release notes and checksums. Do not equate an uploaded Actions artifact with
   an approved release. If a published release already exists, stop; do not replace it.
6. Publish manually only after a separate explicit release approval. Retain the
   checked files/checksums and acceptance notes. No updater is added.

## GitHub Pages diagnosis and manual configuration

For failed run 39739980184, `mkdocs build` succeeded and `configure-pages@v5`
failed to retrieve the Pages site with HTTP 404. In this audit the public repository
API reports **has_pages: false**, `/repos/rex688-png/TARS/pages` returns 404, and
an existing `github-pages` Actions environment has no protection rules. The actor
can read repository administration metadata. This supports Pages not being
enabled, rather than an invalid MkDocs build or a demonstrated permission failure.
An environment named github-pages does not itself enable the site.

If the owner wants the documentation site: open **Repository Settings → Pages →
Build and deployment → Source → GitHub Actions**, enable/save the site as offered
by GitHub, and review environment deployment restrictions for main. Then explicitly
approve a later documentation workflow run and verify its deployment. No Pages
setting is changed here. The workflow already has `pages: write`, `id-token: write`,
a github-pages environment and configure/upload/deploy actions in the right order.
There is no evidence requiring an Actions-only workaround. MkDocs link warnings
are separate from the Pages-site 404 and are reported by local validation.

## Remote Sprint 1 verification scope

Offline tests use synthetic files and a fake `gh` executable, never real release
creation, tag pushes, asset uploads or deployment. Existing package mirrors are
consistent at 0.0.0; no package/lock/installer version was changed. The six-plugin
27-file bundle remains pinned to 6f85f5b8dee4f8ea399df4e86d7cb0a5df03bcc2.
Full production MSI metadata and disposable fixture upgrades are checked in
Windows CI; physical Windows 11 full-installer acceptance remains pending.

Local strict MkDocs validation fails with the same two warnings on both base
9c545a700409ba6e991b0c583b5e25c254cff73f and this sprint: the historical
runtime-hardening-audit.md link to ../test/fixtures/elite/README.md and the upstream
plugins/Development.md link to ./CONTRIBUTING.md. Ordinary `mkdocs build` succeeds.
These pre-existing historical/upstream links are left unchanged; no new warnings
were introduced. This is independent of the GitHub Pages site not being enabled.
