# Runtime fixture, failure and build audit

This audit supports the Windows TARS product; it does not change the proven
Elite/audio/provider/plugin startup path. Fixture records are synthetic. See
[`test/fixtures/elite/README.md`](../test/fixtures/elite/README.md) and
[runtime contracts](runtime-contracts.md).

## Failure semantics and present test evidence

| Condition | Current observable behavior / test boundary | Classification |
| --- | --- | --- |
| Backend disconnect/crash; required main model cannot initialize | Coordinator/facade error and model startup paths; real process failure needs packaged testing | TARS failure |
| Invalid/missing API credential; unregistered selected provider | Configuration/registration checks and model initialization message; no credential value in general facade | TARS failure if required for conversation |
| STT/TTS/memory unavailable or TTS generation throws | `runtime_components`, existing STT/TTS exception reporting; native recovery needs physical Windows | Component unavailable/error; conversation may still work in text |
| Optional remote lookup, one action, missing Elite keybind | Tool error/diagnostic result or keybind warning; raw call stays in Diagnostics | Warning/degraded |
| Missing Observatory feed; no live Elite journal; no route/biology/fuel reading | Missing optional feed is nonfatal; historical journal events are not live; unknown data stays unknown | Not a TARS failure |
| Malformed journal/Status line | Journal skips invalid JSON; Status reader retries and returns no new status after repeated invalid input | Warning/degraded data |
| Corrupt config JSON | Loader returns in-memory defaults, retaining broken file on disk; explicit test added | Recovery gap: normal identity may appear but saved settings are not loaded |
| Missing official behavior-plugin file | Fixed bundle loader raises startup error by design | Packaging/runtime failure |
| Failed optional provider import or incomplete install | Recorded or ignored while other providers load; checksum/manifest/atomic-install tests exist | Component unavailable/error |

An official plugin is currently **required for the bundle to load** even when
its external input, such as Observatory's feed, is optional. Do not confuse
those failure boundaries. This pass tests several cases but does not assert
that all listed failures have end-to-end Windows coverage.

| Requested failure case | Evidence now / remaining gap |
| --- | --- |
| Missing AI provider; cannot initialize; bad API key | UI shows unregistered selections; `runtime_components.models` reports observed initialization. Credential rejection and model-constructor failure still need a controlled provider harness. |
| STT unavailable; TTS unavailable | Facade readiness/unavailable test and existing device-error tests; physical audio required. |
| TTS generation crash | Backend exception path exists; deterministic provider-throw test remains to add. |
| Embedding unavailable | Facade's observed memory flag; real memory-provider fault remains to test. |
| Backend disconnect; IPC/WebSocket loss | New backend-error facade test; socket reconnection still needs integration coverage. |
| Journal directory missing; no current journal; malformed line | New production-reader fixtures cover each. |
| Corrupt config; partial config | New fallback and partial-merge tests. Corrupt-file user recovery remains a product gap. |
| Behavior plugin raises; optional plugin unavailable | New start/stop hook-isolation test and existing missing-bundle test. Missing Observatory **feed** is optional; missing official plugin **file** is fatal. |
| Observatory feed unavailable | Existing Bridge cursor/watch tests; physical writer validation remains. |
| Search/tool failure | New inline failed-search test; native search network failure needs a targeted harness. |
| Action missing keybind | Existing keybind diagnostics; live Elite action execution remains physical. |
| Incomplete provider install | Existing atomic/marker/checksum tests. |

## Startup observations

The cloud source-tree microbench used 21 synthetic journal events and a fresh
temporary TARS profile, 30 repeated reads, warm Python process. Median
`EDJournal.load_history`: **0.09 ms**; first `load_config`: **0.74 ms**;
existing `load_config`: **0.95 ms**. These small fixtures cannot predict a
large real journal, disk contention or a packaged Windows cold start.
The Angular development build completed in roughly **10 s** in this cloud
workspace. The production build is blocked by Google Fonts HTTP 403 here.

Startup order in `src/Chat.py` is config load → plugin imports/registration →
models and audio → journal/Status history and projections → native actions →
plugin start hooks → runtime ready. Electron owns Python process launch and
renderer connections. The current code has stage log messages but no common
per-stage duration telemetry. Config load, official plugin import, model
construction and initial historical state processing are synchronous on the
backend startup path. The journal tail, Observatory watcher and provider
downloads use separate threads; the Angular coordinator awaits backend launch
and start commands. No duplicate initialization was proven by this source-tree
profile; repeated `merge_config_data` messages are nested-log noise.
Model/STT/TTS/embedding initialization may block;
Angular and Electron launch, provider import, native DLL/model load, and first
audio response need measured timestamps on a physical Windows installation.
No performance change is justified by the small fixture numbers.

## Build reproducibility and size

Deterministic inputs: pinned TARS behavior bundle with per-file SHA-256,
allowlisted provider archive hashes, npm lockfiles, pinned Python requirements,
and stable fixture/baseline dumps. `Chat.spec` controls the PyInstaller file
set. Windows CI injects the Git commit SHA into `environment.prod.ts`, so a
different commit intentionally produces different UI bytes. Node uses
`lts/*` in CI and PyInstaller uses a pinned upstream Git revision; toolchain
version/platform details still affect output. Python bytecode/archives,
Angular chunks, Electron/Chromium packaging, ZIP/MSI timestamps and MSI metadata
may also vary. No bit-for-bit MSI claim is made. Later normalization should
start by fixing complete toolchain versions and comparing two Windows builds'
file manifests before changing packaging internals.

Source-workspace sizes observed here: generated Angular development bundle
**30 MB**, UI source assets **9.2 MB**, Electron source/assets **2.2 MB**,
Python `src` **4.0 MB**, verified behavior bundle **576 KB**. Local development
dependencies total roughly **382 MB** at root plus **599 MB** under `ui`, but
`node_modules` is not an Electron package input. The four optional local
provider archives are hundreds of MiB each and are **not** bundled. No MSI,
portable ZIP or PyInstaller bundle from this branch is present in this cloud
workspace, so their exact sizes and Electron/Chromium versus Python contribution
cannot be measured here. Use the Windows CI artifacts for a file-level size
inventory; do not strip assets based on source-tree sizes.

## Logging/event observations

Backend logging uses `debug/info/warning/error`; frontend logs map to
`debug/info/warn/error/event`. A future adapter could normalize `warning` vs
`warn` at the display boundary. `merge_config_data` prints its label repeatedly
on each load (roughly 20 times for this fixture), which adds low-value noise.
`Chat.py` logs startup stage names but also logs the full current backstory;
diagnostics exports must treat logs as private user data. A missing NavRoute
companion JSON caused an ERROR log during a synthetic read even though the
journal line survived; fixture setup now provides the matching sidecar. Existing
timestamps appear in both event content and logger envelopes. No logging
framework or level changes were made in this pass.

## Critical-path coverage map

| Path | Current coverage | Main gap |
| --- | --- | --- |
| Startup/IPC/shutdown | Partial: coordinator, Electron and packaged-profile tests | Cold packaged Windows timing, crash recovery |
| Config load/save/migration | Good for factory, prompt, provider patches and model choices; corrupt-file fallback test added | User-facing recovery from corrupt profile |
| Provider registry/switch/install | Good for allowlist, hashes, atomic install, switching/persistence; focused restart import test exists | Physical DLL/model load and provider reinstall |
| Provider failure | Partial: invalid install/import handling and UI observed health | Real AI/STT/TTS/embedding failure combinations |
| Plugin loading/callbacks/failure | Partial: fixed order, signature/error contracts | Six-plugin packaged startup under faults |
| Journal parsing/freshness | Partial before; synthetic history/tail/session/malformed suite added | Real large or rotated live journals |
| Ship/location/route/exobiology state | Partial: projections plus synthetic journey assertions | Live Status timing and rare event orders |
| Actions/keybinds/search | Partial: action schema, keybind checks, native search and Chat card tests | Live Elite key presses, network/service failure matrix |
| Memory | Partial: provider/config and existing memory tests | Physical Gemma/model data lifecycle |
| STT/TTS/speech normalization | Partial: existing tests plus expanded quantities/identifiers | Microphone, output, TTS crash/recovery |
| Chat/diagnostics | Good for inline chronology, action classification and retained raw logs | Full renderer interaction and accessibility |
| MSI upgrade boundary | Little automated coverage | **Requires physical Windows test** |
| Observatory | Partial: bundled contract, cursor/rotation tests | Live Observatory writer and external plugin data |

No cloud fixture can prove microphone, speaker, live Elite, Observatory writer,
Windows keybind execution or MSI in-place upgrade. Saved journal state is not
live telemetry.
