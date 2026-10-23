# TARS packaged runtime

Windows is the only supported platform. The Windows MSI and portable package are
self-contained. They install the
PyInstaller backend under `resources/Chat` and the verified behavior payload
under `resources/tars-plugins`. The latter contains the six official TARS plugins,
their manifests and helper modules, and the canonical TARS prompt copied from
`TARS-Plugins@a302b33b742d787df27cc8089f3a716fac54e5cd`.

`vendor/tars-plugins/provenance.json` records a SHA-256 digest for every payload
file. `python tools/verify_tars_bundle.py` verifies the vendored copy without an
external checkout. Supplying `--source PATH` additionally proves it matches Git
objects at the pinned revision without changing the reference checkout's HEAD.
Packaged files can be checked with
`--bundle PATH`.

At runtime Electron passes the installed resource location to the backend.
Plugin code is imported in place and is never copied into user storage. TARS
loads the six official plugins in its fixed order and separately enables the
explicit Mistral model-provider integration and Task 4 provider registry.
EDCoPilot and arbitrary plugin folders are not loaded in the TARS profile.

On the first launch only, the canonical bundled prompt seeds a character named
TARS. If `%APPDATA%\TARS\config.json` already exists it is loaded through the
normal migration path and is not overwritten by this seeding step.

All mutable state remains below `%APPDATA%\TARS`, including `config.json`,
database, logs, Electron session data, and plugin persistence. Provider-specific
settings share the `plugin_settings` map in `config.json`, keyed by plugin GUID;
they remain saved when another provider is selected. No COVAS profile is
imported, moved, deleted, or reused.

The installer includes application code, the six TARS plugins, the Mistral
provider integration already frozen into the backend, the prompt, and existing
runtime libraries handled by PyInstaller. Optional local providers and model
weights are not bundled; the Provider Setup page installs pinned official
releases on demand under `%APPDATA%\TARS\providers`. No personal
configuration, credentials, journals, databases, logs, or optional model
binaries are included.

## Install and upgrade boundaries

The build identifies the Windows app as `TARS` with app ID `com.rex688.tars`.
The MSI and portable archive carry the same Electron application and bundled
resources. The repository does not pin a custom MSI installation directory; the
actual destination depends on the installer and user choice. Check the chosen
location on the physical Windows machine.

An MSI upgrade replaces application files and bundled resources, including the
backend executable and verified behavior plugins. The TARS user profile is
outside that package, so an ordinary upgrade is expected to retain its config,
credentials, prompt, reactions, audio devices, provider selections, provider
settings, databases, logs and separately installed providers. Provider package
installation replaces files only under `%APPDATA%\TARS\providers` and does not
write `config.json`. Configuration updates merge partial provider settings;
provider defaults do not replace previously saved values. Back up the private
profile before upgrading or reinstalling. Confirm preservation with a real MSI
upgrade test; source inspection and CI cannot prove every Windows installer path.

The old COVAS user-data directory is separate and is not automatically migrated.
An existing upstream COVAS installation should not be used as a TARS installer
or update source.

## Download and verify a build

An official release is an owner-reviewed, manually published entry on
[TARS Releases](https://github.com/rex688-png/TARS/releases), with versioned MSI,
portable ZIP, provenance and checksums. If no release is published, use only an
explicitly reviewed test build from
[Actions](https://github.com/rex688-png/TARS/actions/workflows/build-executable.yml).
Actions downloads expire and are not beta approval. The current package version
is 0.0.0; the proposed beta version is still pending approval.

For future release assets, run PowerShell `Get-FileHash .\<downloaded-file> -Algorithm SHA256`
and compare with `SHA256SUMS.txt`; also verify the repository, tag and full source
SHA in `release-provenance.json`. Checksums confirm bytes, not who approved them;
obtain the checksum/provenance files from the same reviewed release. Temporary CI
builds may have only workflow/artifact metadata rather than release checksums.

## MSI or portable installation

Close TARS before installing an MSI. Make a private copy of the entire
`%APPDATA%\TARS` folder, then run the reviewed MSI and follow Windows prompts.
For an upgrade, retain the existing installation identity and profile; do not
uninstall/delete user data as a routine troubleshooting step. The owner reports
successful upgrades of previous builds, but confirm your settings and providers
after each upgrade. Disposable Windows MSI tests now cover ordered beta/stable upgrades, reinstalls,
downgrade rejection and synthetic profile preservation. Full application upgrades
on a physical Windows PC still require acceptance; no beta is assigned.

For portable use, extract the complete ZIP to a writable application folder.
The archive currently contains `files\TARS.exe` and a `TARS.lnk`; launch the
executable if the shortcut is unsuitable. Keep all resources beside it. Portable
means no MSI installation; it still uses `%APPDATA%\TARS`, not a separate profile
inside the ZIP. Avoid running MSI and portable copies simultaneously against the
same profile. Extract a new portable version into a fresh application directory
rather than mixing resources from two builds.

## Profile, build identity and startup checks

The profile contains private credentials, personality edits, memory/database,
provider data and logs. Keep whole-folder backups private. Configuration backups
are `config.backup.json` (previous valid save) and, when requested through the
backup controls, `config.manual-backup.json`; these do not replace a full database
and provider backup. Do not delete or upload the profile to diagnose a startup issue.

Use Diagnostics to record **TARS package** and **Frontend build**. The current UI
labels the package as an unreleased build and does not report a separate backend
version; that UI behavior is unchanged. Compare the frontend SHA with the reviewed
workflow/provenance (a PR's test-merge SHA can differ from its source SHA).

If startup fails, confirm extraction/installation is complete, that the backend
and `resources/tars-plugins` exist, and inspect `%APPDATA%\TARS\logs` or a sanitized
Diagnostics export. Check provider installation and restart status, API credentials,
microphone permissions, selected devices and volume as relevant. Do not disable
security software merely because it reports a warning. Local provider models are
[separate opt-in downloads](tars-alpha-provider-setup.md), not missing MSI files.

Windows 11 MSI installation/upgrade, real microphone/speaker operation and live
Elite testing of Explorer, Chatter, memory, vision and TTS remain manual acceptance
items for the future beta. See the [release approval checklist](release-readiness.md).
