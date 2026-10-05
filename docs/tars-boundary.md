# TARS baseline and dependency boundary

| Item | Baseline value |
|---|---|
| TARS | `rex688-png/TARS`, branch `main`, `f0153840016e33c498eafd5ea197963bcf776987` |
| TARS-Plugins | `rex688-png/TARS-Plugins`, branch `main`, `685e16a19d5a5cd83f16297b90ee4c58ba8e11b5` |
| Baseline date | 2026-10-05 |
| Harness topology | Separate, read-only TARS-Plugins checkout. The harness prepends its `plugins` directory to `sys.path` and imports each real manifest entrypoint as a dotted package module. Plugin data is redirected to a temporary directory. |

Both repositories were inspected directly at the commits above. TARS was writable; TARS-Plugins was read-only for this task and was not modified. This is boundary evidence, not a removal recommendation. Runtime traces mean only “reached under these scenarios”; static inspection remains necessary for lazy and conditional paths.

## Host wiring and lifecycle

`PluginManager` makes the current working directory significant: it adds `./plugins` to `sys.path`, creates it if absent, reads each subdirectory's manifest, imports `<directory>.<entrypoint stem>`, and stores the discovered `PluginBase` subclass (`src/lib/PluginManager.py:38-45,89-135`). Built-ins load first. External discovery uses unsorted `os.listdir()` (`PluginManager.py:99`), so external plugin registration order is filesystem-dependent. The checkout observed `TARSExplorer`, `TARSChatter`, `TARSGalaxy`, `TARSNavigator`, `TARSExpedition`; the evidence JSON is stable-sorted and must not be interpreted as the runtime order.

At startup, `Chat` unconditionally constructs the controller manager, action manager, journal reader, main/agent models, TTS and STT wrappers, system/quest/model-usage databases, key sender, status parser, prompt generator, event manager, assistant, and quest catalog manager (`src/Chat.py:134-370`). Vision, embedding, and provider-backed STT/TTS models are configuration-conditional, but their wrappers are still constructed. `run()` starts the configured listening mode before hydration, registers projections, processes queued historical/status events, conditionally registers native actions when `tools_var` is true, then calls plugin `on_chat_start` (`Chat.py:741-842`). This ordering is an important host assumption.

The harness uses real manifests, entrypoint modules, `PluginBase`, event types, projections, and `PromptGenerator`. It substitutes a recording `PluginHelper` and fake model/assistant/managers at dangerous leaves. Full `Chat` construction was deliberately not emulated: it would instantiate audio/input and database infrastructure unrelated to this evidence and is blocked here by PortAudio/PyAudio. Therefore the harness cross-checks registration against `PluginManager`, `PluginHelper`, `ActionManager`, and `Chat` statically rather than claiming full-startup equivalence.

## Explorer dependencies

| Host module/symbol | Access type | Host reference | Plugin reference | Purpose |
|---|---|---|---|---|
| `PluginBase`, `PluginManifest` | direct import/inheritance | `src/lib/PluginBase.py:28,69` | `TARSExplorer/TARSExplorer.py:11,216` | Manifest identity and lifecycle |
| `PluginHelper`, `PluginEvent` | direct import and retained helper | `src/lib/PluginHelper.py:34,63-156` | `TARSExplorer/TARSExplorer.py:12,255-335` | Side effect, event, and six action registrations |
| `Logger.log` | direct import | `src/lib/Logger.py:202-220` | `TARSExplorer/TARSExplorer.py:13` | Diagnostics |
| `EventManager.get_current_state` via `_event_manager` | private helper attribute | `src/lib/PluginHelper.py:41`; `src/lib/EventManager.py:353` | `TARSExplorer/TARSExplorer.py:1088` | Reconstruct current exploration state |
| Prompt/assistant event registration | indirect helper behavior | `src/lib/PluginHelper.py:116-146` | `TARSExplorer/TARSExplorer.py:257-261` | Reply decision and generated plugin prompt |

Explorer keeps its reconstructed body/system state in memory. No Explorer-owned persistent file was found. It assumes journal event dictionaries, projection-state names/shapes, helper dispatch semantics, and that host side effects receive both the event and current projections.

## Navigator dependencies

| Host module/symbol | Access type | Host reference | Plugin reference | Purpose |
|---|---|---|---|---|
| `PluginBase`, `PluginManifest` | direct import/inheritance | `src/lib/PluginBase.py:28,69` | `TARSNavigator/TARSNavigator.py:13,39` | Lifecycle |
| `PluginHelper`, `PluginEvent` | direct import | `src/lib/PluginHelper.py:34,63-156` | `TARSNavigator/TARSNavigator.py:14,88-126` | Data path, side effect, event, actions, status |
| `Logger.log` | direct import | `src/lib/Logger.py:202-220` | `TARSNavigator/TARSNavigator.py:15` | Diagnostics |
| `PluginHelper.get_plugin_data_path` | public helper call | `src/lib/PluginHelper.py:63-68` | `TARSNavigator/TARSNavigator.py:88-90` | Resolves `navigator.json` |
| `PluginHelper.register_action` | callback-contract mismatch | `src/lib/PluginHelper.py:72-85` | `TARSNavigator/TARSNavigator.py:101-124` | Registers two bound callbacks with one positional argument; host wrapper currently invokes `(model, context)` |
| Prompt status generator | indirect prompt integration | `src/lib/PluginHelper.py:148-156` | `TARSNavigator/TARSNavigator.py:126` | Journey context in main prompt |

Navigator atomically replaces `plugin_data/<guid>/navigator.json` through a temporary sibling (`TARSNavigator.py:169-187`). It assumes ordered live journal events and specific route/location projection shapes. The two signature differences are captured as baseline facts; Task 1 does not alter the production helper.

## Galaxy dependencies

| Host module/symbol | Access type | Host reference | Plugin reference | Purpose |
|---|---|---|---|---|
| `PluginBase`, `PluginManifest` | direct import/inheritance | `src/lib/PluginBase.py:28,69` | `TARSGalaxy/TARSGalaxy.py:10,151` | Lifecycle |
| `PluginHelper` | direct import and retained helper | `src/lib/PluginHelper.py:34,72-156` | `TARSGalaxy/TARSGalaxy.py:11,195-280` | Side effect, status, five actions |
| `Logger.log` | direct import | `src/lib/Logger.py:202-220` | `TARSGalaxy/TARSGalaxy.py:12` | Diagnostics |
| `EventManager.get_current_state` via `_event_manager` | private helper attribute | `src/lib/PluginHelper.py:41`; `src/lib/EventManager.py:353` | `TARSGalaxy/TARSGalaxy.py:500,1653` | Current system/history fallback |
| `requests` and external service schemas | direct external dependency | n/a | `TARSGalaxy/TARSGalaxy.py:7,642,1564` | Ardent/EDData/EDSM fallback and verification |

Galaxy has no discovered owned persistence file. It assumes network availability, third-party response schemas, current-state access through a private helper field, and native COVAS finders as the preferred path. Network actions were not invoked by the offline harness.

## Chatter dependencies

| Host module/symbol | Access type | Host reference | Plugin reference | Purpose |
|---|---|---|---|---|
| `PluginBase`, `PluginManifest` | direct import/inheritance | `src/lib/PluginBase.py:28,69` | `TARSChatter/TARSChatter.py:10,19` | Lifecycle/settings |
| `PluginHelper`, `PluginEvent` | direct import and extensive duck typing | `src/lib/PluginHelper.py:34-61,116-156` | `TARSChatter/TARSChatter.py:11,491-538,551-567` | Host services, events and compatibility probing |
| Plugin setting definitions | direct import | `src/lib/PluginSettingDefinitions.py:1-90` | `TARSChatter/TARSChatter.py:12-14,34-410` | UI configuration schema |
| `ModelUsageStats`, `PromptUsageStats`, `log_llm_usage` | direct usage contract | `src/lib/Logger.py:104-199` | `TARSChatter/TARSChatter.py:15,640-758,2068-2083` | Preserve/report synchronous model usage |
| Main `LLMModel.generate` | private helper/assistant lookup and monkey-patch | `src/lib/PluginHelper.py:39-47`; `src/lib/Models.py:85` | `TARSChatter/TARSChatter.py:496-501,623-777` | Installs/restores Director guard around normal responses |
| `Assistant` busy/reply state | private helper lookup | `src/lib/PluginHelper.py:37,60` | `TARSChatter/TARSChatter.py:491-494,1807,2332` | Avoid speech while host is busy |
| `EventManager` memory/state | private helper lookup | `src/lib/PluginHelper.py:41`; `src/lib/EventManager.py:300-307` | `TARSChatter/TARSChatter.py:503-520,1370-1424` | Recent/semantic context |
| `ActionManager.actions`, `allowed_actions` | private helper lookup | `src/lib/PluginHelper.py:42`; `src/lib/ActionManager.py:19-67` | `TARSChatter/TARSChatter.py:506-538,886-894,2220-2224` | Locate and permission-check `getVisuals` |
| Prompt messages/system role | wrapper/interception | `src/lib/PromptGenerator.py:3060-3490` | `TARSChatter/TARSChatter.py:640-758,1180-1430` | Director continuity and semantic memory injection |
| Plugin data path | public helper call | `src/lib/PluginHelper.py:63-68` | `TARSChatter/TARSChatter.py:551-552,2393-2444` | Persistent recent lines/topics |

Chatter persists `plugin_data/<guid>/tars_ultimate_memory.json`, using a `.tmp` sibling for replacement. It installs a system-level wrapper on the shared main model's synchronous `generate`, may regenerate once for repetition, directly calls the saved original for spontaneous chatter, and restores only if its own wrapper is still installed. The fake-model contract test confirms the current three-tuple `(text, actions, ModelUsageStats)` shape. Wrapper ordering with another model-mutating plugin remains fragile.

## Expedition dependencies

| Host module/symbol | Access type | Host reference | Plugin reference | Purpose |
|---|---|---|---|---|
| `PluginBase`, `PluginManifest` | direct import/inheritance | `src/lib/PluginBase.py:28,69` | `TARSExpedition/TARSExpedition.py:13,58` | Lifecycle |
| `PluginHelper` | direct import | `src/lib/PluginHelper.py:34,63-156` | `TARSExpedition/TARSExpedition.py:14,110-180` | Data path, side effect, four actions, status |
| `Logger.log` | direct import | `src/lib/Logger.py:202-220` | `TARSExpedition/TARSExpedition.py:15` | Diagnostics |
| `PluginHelper.register_action` | callback-contract mismatch | `src/lib/PluginHelper.py:72-85` | `TARSExpedition/TARSExpedition.py:125-178` | Four bound callbacks accept one positional argument while host supplies two |
| Windows Saved Games / `Path.home` / `USERPROFILE` | direct filesystem discovery | `src/lib/Config.py:984-1000` (host analogue) | `TARSExpedition/TARSExpedition.py:283-319` | Locate Elite journals without host journal service |
| `Journal.*.log` parser | direct enumeration/read | `src/lib/EDJournal.py:68-113` (host analogue) | `TARSExpedition/TARSExpedition.py:319-369` | Sorted reconstruction of cross-session expedition history |

Expedition persists `plugin_data/<guid>/expeditions.json` by temporary sibling replacement (`TARSExpedition.py:263-280`). Its rebuild does not use the host `EDJournal` instance: it probes the conventional home/`USERPROFILE` path and Windows Saved Games known folder, sorts files by filename, then reads lines in file order. Redirected/localized folders rely on the Windows known-folder call. This is an independent filesystem and ordering assumption.

## Native host tools required by effective TARS

The five modules add 17 actions (Explorer 6, Navigator 2, Galaxy 5, Expedition 4, Chatter 0), but effective TARS also relies on host actions. `register_actions` supplies ship/SRV/on-foot controls and conditionally `getVisuals`; `register_web_actions` supplies `web_search_agent` and conditionally `remember_memories` (`src/lib/actions/Actions.py:1456`; `src/lib/actions/actions_web.py:2692`). The nested web agent exposes `system_finder`, `station_finder`, `body_finder`, `engineer_finder`, `blueprint_finder`, `material_finder`, stored ships/modules/carriers, commander data, and Galnet news (`actions_web.py:126-490`). TARS prompt routing explicitly prefers the native finder family over Galaxy for ordinary lookups.

Tool visibility varies in `ActionManager.getToolsList` (`src/lib/ActionManager.py:36-67`) by active game mode/action type, `tools_var`/`uses_actions`, web/UI flags, per-action permission, and in-station state. Registration itself varies with vision model (`getVisuals`), embedding model (`remember_memories`), and overlay HUD (`generate_ui`). Provider choice therefore affects vision and memory tools indirectly. These conditions are recorded in the schema snapshot instead of multiplying a large state matrix.

## Chatter host dependency boundary

| Boundary | Current dependency |
|---|---|
| Model | Shared synchronous main-model `generate(messages, tools, tool_choice)`; wrapper mutates the model object and expects a three-tuple return |
| Memory | Event manager short/long-term memory and assistant access, reached through private helper members; semantic recall is cached briefly |
| Vision | Private vision model plus `ActionManager.actions['getVisuals']` and explicit `allowed_actions` permission |
| Assistant | Busy/reply/activity state and should-reply registration; private object shape is assumed |
| Prompt | Injects Director text into system-role messages and consumes host status/conversation context |
| Actions | Reads action registry and results; may invoke `getVisuals` through the registered host action |
| Usage stats | Preserves `ModelUsageStats`, combines/records prompt usage, and returns the host's synchronous tuple shape |

## Historical hydration vs live dispatch

`Chat.run` queues `EDJournal.historic_events`, queues the current status, registers projections, and calls `EventManager.process` before action registration and plugin startup (`src/Chat.py:781-842`). `add_historic_game_events` labels `GameEvent(historic=True)` and queues only IDs newer than stored history; older IDs are inserted directly into processed history (`src/lib/EventManager.py:173-187`). During `process`, every event is stored and updates projections before the historic check. Historic game events then `continue` and do not trigger event or projected-event side effects (`EventManager.py:309-331`). Live events traverse those side effects, which include `Chat.on_event`, `Assistant.on_event`, and plugin side effects registered after hydration.

Thus the host clearly separates projection/database reconstruction from live side effects. Ambiguities remain: the status event in the same batch is live, timer projections can later emit side effects, and Expedition independently rereads journals when its explicit rebuild path is used. A full hydration safety test was deferred because constructing the real manager also starts persistence and a timer thread; proving audio/model/input silence end-to-end would require a broader host fixture.

## Persistence and filesystem boundary

The production Electron launcher sets the packaged Python backend working directory to Electron `userData` on Windows (`electron/index.js:114-123`). `get_cn_appdata_path()` simply returns `os.getcwd()` (`src/lib/Config.py:981-982`), while config and plugin paths are also relative to the working directory. Consequently the known Windows installation places the main writable set under:

`C:\Users\rex68\AppData\Roaming\com.covas-next.ui`

| Current path | Owner / class | Purpose | Unsafe to share? | Future isolation requirement |
|---|---|---|---|---|
| `<backend cwd>/config.json` | Host / application config | Providers, keys, character, tool permissions, plugin settings (`Config.py:1542-1585`) | Yes | TARS-specific application-data root; optional one-time import only |
| `<backend cwd>/covas.db` plus SQLite WAL/SHM | Host / database and memory | Events, projections, semantic memory, quests, usage, action cache, system events (`Database.py:14-37`) | Yes | Separate TARS database |
| `<backend cwd>/plugin_data/<guid>/navigator.json` and `.tmp` | Navigator / persistent TARS state | Current journey leg | Yes | TARS plugin-data root |
| `<backend cwd>/plugin_data/<guid>/expeditions.json` and `.tmp` | Expedition / persistent TARS state | Expedition history | Yes | TARS plugin-data root |
| `<backend cwd>/plugin_data/<guid>/tars_ultimate_memory.json` and `.tmp` | Chatter / persistent TARS state | Director recent lines/topics | Yes | TARS plugin-data root |
| `<backend cwd>/plugins` and optional `deps` | Host / installed code, generated directory | External plugin discovery (`PluginManager.py:38-45,95-99`) | Yes for mutation/versioning | TARS-owned install/plugin root |
| Electron `app.getPath('logs')/com.covas-next.ui.log` | Launcher / logs | Rotating launcher/backend bridge log (`electron/index.js:69-78`) | Yes (identity and concurrent rotation) | TARS log namespace/name |
| `%LOCALAPPDATA%/com.covas-next.ui/logs` | Old launcher / logs | Deleted at each Windows startup (`electron/index.js:91-94`) | Yes; deletion collision | Never target the COVAS directory from TARS |
| Electron `userData/userAssets/*` | UI / persistent generated assets | User images and UI-managed assets (`electron/index.js:430-487,1458-1471`) | Yes | TARS user-assets root |
| `src/data/quests.yaml` or packaged equivalent, and sibling `audio/*` | Host/UI / application config and copied generated assets | Editable quest catalog and imported audio (`QuestCatalogManager.py:38,460`; `electron/index.js:1435-1451`) | Yes; may also be unwritable when packaged | Move to a future TARS data root, retaining bundled defaults separately |
| Electron `sessionData` and Chromium `Cache`, GPU/cache storage | Electron / cache and UI state | Framework-managed session/cache under app identity | Yes | TARS Electron application identity and userData/sessionData |
| OS temp `*.png` | Screenshot / temporary | macOS screenshot bridge, removed after load (`Screenshot.py:118-138`) | No persistent collision expected | Continue OS-temp isolation and cleanup |
| Elite Saved Games `.../Frontier Developments/Elite Dangerous/Journal.*.log`, `Status.json`, route/market/cargo files | Elite / external data (read-only here) | Host state and Expedition reconstruction (`Config.py:984-1000`; `EDJournal.py:36-113`) | Intended shared read source | Remain external/read-only; never migrate or modify |
| `%LOCALAPPDATA%/Frontier Developments/Elite Dangerous` | Elite / external data | Bindings/theme/HUD reads (`Config.py:1003-1012`) | Intended shared read source | Remain external/read-only |
| Python stdout | Host / logs | Structured runtime log stream (`Logger.py:28-49`) | Launcher decides persistence | Route to TARS log identity |

Explorer and Galaxy have no discovered persistent files. Plugin settings are not separate files: they live under `plugin_settings` inside `config.json`. UI preference persistence beyond Electron/Chromium-managed state was not found as a separate application file.

Original COVAS and future TARS must not share the backend working directory, Electron `userData`, config, SQLite database, plugin data, logs, or assets. Task 1 intentionally does not choose or implement the future path.

## Harness scenarios and evidence limits

- Scenario A loads each real manifest entrypoint and captures lifecycle registrations using isolated helper/model/filesystem leaves.
- Scenario B sends a synthetic exploration event, route event, fake-safe Chatter generation, and Expedition session event/action. Galaxy registration/current-state routing is reached, but its network query leaf is deliberately not invoked. Native finder schemas are extracted from the real registration literals; no network finder was called.
- Real projections and prompt generation produce normal-ship, active-route, memory-context, and Chatter-directed snapshots using only `TEST_CMDR`, `TEST_SYSTEM`, and `TEST_DESTINATION`.
- Absolute/temp paths and wall-clock display fields are normalized. Two fresh dumps were byte-identical.

## Could not determine statically

- The exact external plugin order on every target filesystem; current code does not sort discovery.
- Every Chromium/Electron cache filename and UI-state database created by a particular Electron version.
- Which third-party Galaxy endpoint branches are exercised in real gameplay, or their future response compatibility; the baseline made no network calls.
- Whether another plugin wraps the shared model before/after Chatter in a production install; wrapper composition depends on discovery order.
- Complete lazy-import reachability. Trace entries are only “reached under these scenarios.”
- End-to-end historical hydration silence with real audio/input/database objects. Static control flow shows historic game side effects are skipped, but the higher-cost emulation was deferred.
- Fully packaged Linux backend path behavior when `XDG_DATA_HOME` is unset: `path.join(process.env.XDG_DATA_HOME, ...) || ...` evaluates `path.join` first (`electron/index.js:121`) and may throw rather than use the apparent fallback.
- Full real-startup parity in this cloud host because PyAudio/PortAudio and Electron binaries are unavailable. No production behavior or persistence path was changed to work around that limitation.
