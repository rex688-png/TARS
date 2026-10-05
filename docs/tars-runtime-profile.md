# TARS runtime profile

Task 2 introduces a narrow internal product profile on top of the existing COVAS-derived backend. It does not remove native tools, providers, memory, vision, STT/TTS, Chatter interception, or the default development/test startup path.

## Activation and application data

Packaged Electron startup enables the profile by passing `TARS_RUNTIME_PROFILE=1` to the Python backend. Development/direct backend startup does not enable it unless the variable is explicitly set, preserving the prior loader for baseline comparison.

Before logger or path consumers initialize, packaged startup sets:

- product name: `TARS`
- application ID: `com.rex688.tars`
- Electron `userData`: `<Electron appData>/TARS`
- Electron `sessionData`: `<Electron appData>/TARS/session`
- logs: `<Electron appData>/TARS/logs/tars.log`
- backend working directory: the TARS `userData` directory

On Windows, Electron `appData` is `%APPDATA%`, so the effective writable root is `%APPDATA%\TARS`. Existing relative `config.json`, `covas.db`, `plugin_data`, and runtime files consequently live below that root. Packaged TARS neither reads as its writable root nor deletes `%APPDATA%\com.covas-next.ui`; no migration or copy is performed.

## Deterministic plugin selection

When `TARS_RUNTIME_PROFILE=1`, `PluginManager` skips built-in EDCoPilot/Mistral registration and arbitrary directory discovery. It requires and loads only these external folders, in order:

1. `TARSExplorer`
2. `TARSNavigator`
3. `TARSGalaxy`
4. `TARSChatter`
5. `TARSExpedition`

The folders remain external and must be physically available below the backend's `plugins` directory. Missing manifests or entrypoints, or an import failure, produce a deterministic startup error identifying the plugin. TARS-Plugins is not vendored or modified.

## Plugin action callback compatibility

`PluginHelper.register_action` inspects a callback once at registration. One-positional-argument callbacks receive the validated Pydantic model; two-argument and varargs callbacks receive the model and projected-state context. Unsupported signatures fail registration clearly. Runtime invocation never catches `TypeError` to retry with another shape, so mutating callbacks execute at most once. Existing plugin action exceptions still become the same `Error executing action ...` result.

## Status.json resilience

`StatusParser` now makes three bounded read attempts with short backoff for empty, malformed, partially written, temporarily missing, or invalid-root `Status.json` content. If all attempts fail, it logs one concise warning and keeps the previous valid state. Startup uses the existing safe empty/default parsed status when no valid document is available. The watch loop continues and accepts the next valid update without emitting false transitions from the malformed read.

## Manual Windows smoke test

1. Record timestamps/hashes for the existing `%APPDATA%\com.covas-next.ui` files.
2. Launch the packaged TARS application.
3. Confirm `%APPDATA%\TARS` is created and contains TARS config/database/plugin state as those features initialize.
4. Confirm `%APPDATA%\TARS\logs\tars.log` is used and the recorded COVAS files remain untouched.
5. Place/confirm the five authoritative plugin directories under `%APPDATA%\TARS\plugins` and verify startup reports them in the required order with no EDCoPilot or Mistral built-ins.
6. Launch Elite while TARS is already running; verify normal status changes arrive.
7. Launch TARS while Elite is already running; verify initialization survives any transient Status.json rewrite.
8. During an Elite status update, confirm a transient empty/truncated Status.json warning does not terminate TARS and the next valid status is accepted.
9. Run one Navigator status/control action and one Expedition status/history action.
10. Run one Galaxy fallback query and one native finder query.
11. Confirm Chatter can still generate a response through the synchronous three-tuple model contract.
12. Exit and confirm no new write occurred below `%APPDATA%\com.covas-next.ui`.

## Intentionally deferred

- Importing or migrating existing COVAS settings/database/plugin state
- Vendoring or packaging TARS-Plugins into this repository
- Renaming the isolated `covas.db` filename
- Broad UI/overlay string rebranding
- Changes to Chatter, native finder/search, memory, vision, speech, provider, journal hydration, or plugin persistence architecture
