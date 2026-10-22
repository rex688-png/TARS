# Release readiness and approval

This is the current release procedure, not a beta announcement. RC20 and the
release-infrastructure/MSI sprints are integrated into main. The authoritative
root `package.json` and its existing mirrors remain **0.0.0**, an unreleased
placeholder. An illustrative version such as `0.5.0-beta.1` is not an assignment
or approval to publish.

## What automation proves

Windows CI builds/tests the backend, frontend and Electron application, produces
MSI and portable ZIP packages, and validates a clean packaged profile and E2E.
It also inspects actual MSI identity/upgrade tables and runs a disposable real
MSI sequence: legacy 0.0.0 → beta.1 → beta.2 → stable, reinstall, rebuilt-version
replacement and downgrade rejection with a synthetic profile. The fixture payload
is inert; this is installer-mechanism evidence, not full runtime acceptance.

Sprint 2's [validated Windows run](https://github.com/rex688-png/TARS/actions/runs/39762690801)
passed these checks. Always examine the checks for the **exact future candidate
commit** as well; an older run is not evidence for a changed binary.

The [MSI policy](msi-versioning.md) preserves `com.rex688.tars`, UpgradeCode
continuity and `%APPDATA%\TARS`. Semantic version/tag validation rejects placeholder
releases, unsupported mappings and mismatched tags. Versions and architecture
are checked before release staging.

## Temporary builds versus official releases

[Actions artifacts](https://github.com/rex688-png/TARS/actions/workflows/build-executable.yml)
are temporary SHA-named build outputs, not official releases. They can expire.
An official release is an owner-reviewed, manually published entry on
[TARS Releases](https://github.com/rex688-png/TARS/releases).

Only a future explicitly approved version tag push can enter the existing draft
release job; it depends on successful packaging, E2E and real MSI acceptance.
Staging verifies the tag/source, selects exactly one MSI and portable ZIP, and
produces:

- `TARS-<version>-windows-x64.msi`
- `TARS-<version>-windows-x64-portable.zip`
- `release-provenance.json` with source, version, architecture, plugin pin and hashes
- `SHA256SUMS.txt`

A published release is refused. Existing assets are not overwritten; an existing
draft requires review of its version/channel and checksums. Do not publish or
edit a draft while the upload job is running. This is traceability, not a claim
of bit-for-bit reproducible binaries or an automatic update service.

## Owner checklist for a future release

1. Separately approve a supported semantic version and its MSI mapping; update
   root/Electron manifests and both lockfile version mirrors consistently.
2. Require green security, Windows build, actual MSI inspection/upgrade,
   packaging and E2E checks on the exact candidate source.
3. Privately back up the full profile. Test the real MSI on Windows 11, including
   upgrade from the relevant existing install and retention of personality,
   provider/plugin settings, credentials and memory. Check installation scope,
   shortcuts and duplicate application registrations.
4. Launch TARS.exe. Test real microphone/speaker devices, provider registration,
   speech and interruption, Elite journal/Status updates, Explorer, Chatter,
   Navigator, Galaxy, Expedition, memory and vision. Test Observatory if in use.
   Full-payload device/game testing remains pending; automated fixtures do not
   complete it. Prior successful owner upgrades do not prove every upgrade path.
5. Explicitly approve the exact commit and `v<version>` tag, then inspect the
   resulting draft, assets, provenance and checksums.
6. Publish manually only after separate release approval. An existing published
   release must not have its assets silently replaced.

## Documentation deployment

The TARS manual is deployed through GitHub Pages using the existing GitHub
Actions workflow. No new Pages setup is required by this manual. Historical
Sprint 1 Pages-404 diagnosis and old strict-build warnings are preserved in the
repository archive; they are not current setup instructions. A documentation PR
is reviewed before main's normal deployment. It does not assign a product version
or authorize a release.
