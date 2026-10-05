# TARS packaged runtime

The Windows installer and portable package are self-contained. They install the
PyInstaller backend under `resources/Chat` and the immutable Task 3 payload
under `resources/tars-plugins`. The latter contains the five behavior plugins,
their manifests and helper modules, and the canonical TARS prompt copied from
`TARS-Plugins@685e16a19d5a5cd83f16297b90ee4c58ba8e11b5`.

`vendor/tars-plugins/provenance.json` records a SHA-256 digest for every payload
file. `python tools/verify_tars_bundle.py` verifies the vendored copy without an
external checkout. Supplying `--source PATH` additionally proves it matches a
checkout at the pinned revision. Packaged files can be checked with
`--bundle PATH`.

At runtime Electron passes the installed resource location to the backend.
Plugin code is imported in place and is never copied into user storage. TARS
loads the five behavior plugins in its fixed order and separately enables the
explicit Mistral model-provider integration. EDCoPilot and arbitrary plugin
folders are not loaded in the TARS profile.

On the first launch only, the canonical bundled prompt seeds a character named
TARS. If `%APPDATA%\TARS\config.json` already exists it is loaded through the
normal migration path and is not overwritten by this seeding step.

All mutable state remains below `%APPDATA%\TARS`, including configuration,
database, logs, Electron session data, and plugin persistence. No COVAS profile
is imported, moved, deleted, or reused.

The installer includes application code, the five TARS plugins, the Mistral
provider integration already frozen into the backend, the prompt, and existing
runtime libraries handled by PyInstaller. Optional provider models are not
bundled; providers retain their existing on-demand/API behavior. No personal
configuration, credentials, journals, databases, logs, or optional model
binaries are included.
