# TARS runtime contracts at the Windows product boundary

This describes the code packaged in this repository. The six behavior plugins
are vendored from the verified TARS-Plugins revision recorded in
`vendor/tars-plugins/provenance.json`; their source is unchanged by this audit.

## Behavior plugin lifecycle

`PluginManager.load_tars_plugins` checks the fixed six-folder order and each
manifest/entrypoint before importing. A missing or unimportable official plugin
raises a startup error. It also loads only the controlled provider registry;
arbitrary folders are not scanned. `PluginBase` supplies `on_chat_start`,
`on_chat_stop`, optional `settings_config` and `model_providers`.
`PluginHelper` registers side effects, events, status generators and actions.
Action callbacks may take a validated Pydantic argument alone or that argument
plus context. An action exception becomes an action error result; manager
start/stop hook exceptions are logged per plugin so later hooks can run. Plugin
load failure is distinct from a failed optional tool call.

| Plugin | Inputs and state | Exposed contract | Optional dependencies and lifecycle |
| --- | --- | --- | --- |
| Explorer | Journal scans, FSS/DSS, biology, current-system history; session body state | `TARSExplorerTarget`; system summary, priority targets, body, biology, progress and diagnostics actions | Primes saved history at chat start; cancels delayed FSS work at stop. A missing scan yields incomplete/unknown facts, not invented findings. |
| Navigator | Journal location/jumps/NavRoute and saved `navigator.json` | `TARSNavigatorTarget`; status/control actions and status context | Restores journey on start, saves on stop. A route count is authoritative only when NavRoute exists; fallback is marked stale. |
| Galaxy | Native location projections/history; station/system services and optional external EDSM data | Nearest-station/service fallback, EDSM inventory/status and diagnostics actions; routing status context | Native finder tools remain first choice. EDSM credentials and network are optional; failed remote lookup is a tool failure, not an Elite journal failure. |
| Chatter | Live game/conversation events, cooldowns, optional vision | Spontaneous and event-driven screened `PluginEvent` remarks | Start/stop own scheduling; vision is opt-in. No gameplay data should be inferred from silence. |
| Expedition | Journal events and persisted trip state; historical journal rebuild | Status, history, explicit rebuild/control actions; status context | Loads saved trip and may rebuild from local journals; saves on stop. Missing journals limit history rather than inventing payouts. |
| Observatory Bridge | External Observatory JSONL feed and persisted cursor/recent IDs | `TARSObservatoryFact` and `tars_observatory_diagnostics` | Starts a watcher on chat start and joins it on stop. Missing feed is non-fatal; historical records are not replayed. The external writer is separate from Journal and Status.json. |

The table describes internal sources feeding **one TARS**. These plugins are
not separate user-facing assistants. Their per-tool failures should remain
diagnosable without being promoted to a global TARS failure. A missing official
bundle file, however, is a packaging/runtime failure by current design.

## Replaceable provider contract

`PluginManager` registers built-in/cloud providers and only the four approved
local provider packages from `TarsProviderRegistry.py`. Local packages are
explicit downloads with pinned length/hash/manifest, safe extraction, an atomic
install, and an installation marker. Provider entrypoints are loaded from an
allowlisted path under a synthetic Python package; a hyphenated filename is
valid. A partial or invalid directory is ignored. Per-provider import failure
is recorded in `failed_plugins` and does not abort loading other providers.

| Kind | Interface from `Models.py` | Selection and failure boundary |
| --- | --- | --- |
| LLM / agent / vision | `LLMModel.generate(messages, tools, tool_choice)` returns response, tool calls and usage | Provider and model fields in config select an implementation. Required main-model initialization failure prevents normal conversation; vision is optional. GPT-6 behavior remains in `Models.py`. |
| STT | `STTModel` converts captured audio to transcription | `stt_provider` may be `none`; microphone/PTT and native audio health need Windows validation. |
| TTS | `TTSModel` generates speech, using shared `SpeechText` normalization before provider output | `tts_provider` may be `none`; a synthesis exception is reported, not silently treated as spoken output. |
| Embedding / memory | `EmbeddingModel.create_embedding(text)` returns input plus vector | `embedding_provider` may be `none`; memory availability must reflect actual initialization. |

Plugin providers declare `model_providers` definitions (`kind`, `id`, label,
settings schema) and implement `create_model(provider_id, settings)`.
`plugin_settings[manifest GUID]` holds saved values and plugin-local schema
version; partial UI edits merge by field. Provider package defaults fill absent
values but must not replace saved ones. A selection such as
`plugin:<guid>:<provider-id>` remains in config across restart and switches.
Package reinstall/update changes verified files under `%APPDATA%\TARS\providers`,
not the user's `config.json`. Backend restart reloads installed providers; do
not infer readiness from a selected value alone. The existing `runtime_components`
message reports observed model/STT/TTS/memory initialization to Angular.

## Configuration/version boundary

`Config.py` has an explicit `config_version` (currently **20**) for inherited
schema migrations and `tars_profile_version` (currently **1**) for the TARS
factory-profile migration. No new version field is needed here. Top-level
groups include identity/characters, event reactions and allowed actions,
LLM/agent/vision/STT/TTS/embedding provider+model+endpoint+API-key fields,
audio devices/PTT/volume, Elite journal and app-data paths, overlays/VR,
remote tracing, and `plugin_settings`. The TARS prompt and voice/speed are in
the active TARS character. API credentials are stored in private `config.json`;
the general UI facade exposes configured status, not raw key values.

`load_config` merges saved data with defaults, runs versioned migrations and
preserves explicit TARS selections. UI edits are patches; full config imports
are replacements. A corrupt JSON document currently falls back to factory
defaults in memory and leaves the broken file untouched. The application needs
a clearer recovery/backup UX later, but a speculative migration or silent
overwrite would risk user settings.

## Tool and action presentation

The backend event/log stream remains the diagnostic source. The small
`chat-presentation.ts` classifier maps a completed `search_result` to a
**user-visible result**, a synthetic action with short progress text to a
**transient activity**, and raw `action` entries such as `showUI` to
**diagnostic-only**. Error/warning chat roles remain visible messages; backend
logs retain raw tool details in Diagnostics. Search results remain chronological
inside Chat. This classification is presentation-only and does not change tool
execution or the journal/action pipeline.
