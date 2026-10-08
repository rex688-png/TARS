# TARS packaged runtime

Windows is the only supported platform. The Windows MSI and portable package are
self-contained. They install the
PyInstaller backend under `resources/Chat` and the verified behavior payload
under `resources/tars-plugins`. The latter contains the six official TARS plugins,
their manifests and helper modules, and the canonical TARS prompt copied from
`TARS-Plugins@67b1a1cab5a67d675372477dbcde061697e80bf5`.

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
