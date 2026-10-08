# Windows baseline and compatibility inventory

This is a source-level audit of the current Windows TARS package. It does not
replace a physical MSI upgrade or live Elite/audio test.

## Package and mutable data

`package.json` identifies the Electron product as `TARS` (`com.rex688.tars`).
The Windows build creates an unpacked application, MSI, and portable ZIP. The
package carries Angular UI files, `resources/Chat`, and the verified six-plugin
bundle in `resources/tars-plugins`. The MSI install directory is not explicitly
pinned in this repository; record it from the installed build on Windows.

Electron sets `userData` to `%APPDATA%\TARS` before backend startup. The backend
uses this as its working directory, so `config.json`, `covas.db`, `plugin_data`,
and other relative runtime data stay in that profile. Electron logs are under
`%APPDATA%\TARS\logs` and session data under `%APPDATA%\TARS\session`.
`TARS_PROVIDER_ROOT` points to `%APPDATA%\TARS\providers`; approved provider
packages are installed there, separate from the app resources. Provider-specific
values are in `config.json` → `plugin_settings`, keyed by plugin GUID, not in the
replaceable provider directory.

An MSI upgrade should replace the packaged application and resources while
leaving the separate TARS profile and downloaded providers in place. Current
config update logic merges provider field edits and retains inactive providers'
settings. Migration tests cover preservation of explicit model, API, prompt,
audio, reactions and plugin choices. Provider reinstall/update changes the
verified provider package, not user config. A real Windows upgrade must still
confirm install destination, saved settings, and installed provider behavior.
The old `%APPDATA%\com.covas-next.ui` profile is not automatically imported.

## COVAS residue classification

| Category | Findings | Decision |
| --- | --- | --- |
| Safe user-facing cleanup | Old Linux support/Flatpak claims, COVAS plugin install instructions, upstream FAQ/first-step text, and a missing-character fallback name | Replaced with current TARS Windows and controlled-provider guidance. |
| Technical compatibility | `covas.db`, Angular output folder `covas-next-ui`, backend chat role `covas`, font-scale storage/event keys, remote-session cookie, overlay native name, and inherited CSS/class identifiers | Retained. Renaming can affect persisted data, packaging, protocol consumers or overlays. |
| Upstream attribution | COVAS:NEXT name in README, licenses, credits and historical Task 1–5 evidence | Retained with attribution and provenance. |

The normal shell uses production TARS branding; the packaged window title and
icon are TARS. Legacy stock images and old COVAS styling identifiers remain in
source. No canonical avatar bytes or existing branding assets were changed.
Some advanced upstream guides, screenshots and the inherited upstream data
policy remain historical reference material. They need separate product/legal
review before being treated as TARS installation or privacy instructions.

## Old GUI destinations

Angular routes are the main shell, overlay and generated UI. Ship, Tasks,
Logbook, Search and Actions are not primary routes. Manual Actions and logbook
remain reachable in Diagnostics; the Navigation component remains embedded in
Exploration, and detailed storage components remain embedded in Storage.
`SearchResultsComponent` and `TasksContainerComponent` have no current shell
reference in the inspected source, but are retained pending physical testing
and component-level dependency review. Legacy `showUI` commands are translated
by `tars-shell-navigation.ts` for compatibility. Shared services and projections
are not deletion candidates in this pass.

## Validation boundary

Windows CI checks code, frontend, Electron, backend, verified bundle and package
layout. **REQUIRES LOCAL PC VALIDATION:** MSI in-place upgrade, persisted
credentials/provider tuning after provider reinstall, microphone and speakers,
live journal/Status freshness, Elite keybind execution, Observatory feed, and
portable-vs-MSI profile continuity. Saved journal state alone does not establish
live telemetry.
