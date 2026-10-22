# Task 6A frontend foundation

Task 6A separates renderer lifecycle coordination from the current visual shell and
adds a typed, secret-free state boundary for a future TARS frontend. It does not
replace the existing UI or change the Python runtime protocol.

## Ownership after Task 6A

`TarsApplicationCoordinator` owns renderer-side orchestration:

- start the backend once for the renderer application;
- respond to the existing `starting`, `configuring`, `running`, and `error` states;
- perform configured autostart once;
- preserve overlay creation before session clearing and the backend start command;
- clear the current renderer transcript and logs when starting a new session;
- destroy overlays before restarting the backend into configuration mode.

Electron's `BackendService` still owns the Python process. `TauriService` still
owns IPC/WebSocket transport, unexpected-process-exit handling, the close
confirmation handshake, and the active-provider-installation shutdown guard.

The existing `MainViewComponent` initializes and consumes the coordinator. Its
buttons delegate to the coordinator, so the Task 5 UI keeps the same lifecycle
without being the lifecycle implementation.

## New frontend boundary

`TarsRuntimeFacade` composes the existing Angular services and exposes:

- application state: stopped, starting, configuring, running, restarting, error;
- interaction phase: idle, listening, thinking, speaking, acting, with inferred
  thinking explicitly marked as derived;
- normalized current-session conversation entries for commander, TARS, activity,
  system, warning, and error messages;
- a secret-free provider/model/configuration summary;
- a small source-neutral Elite context rather than the complete projection graph;
- provider installation progress and restart requirement;
- warnings/errors already emitted by the runtime;
- conservative component health whose evidence is `observed`, `configured`, or
  `not-exposed`;
- an empty, typed external-integration collection reserved for real recovered
  adapters. Task 6A does not claim or synthesize Observatory state.

The facade intentionally does not expose the existing raw `Config`, API keys, or
other credential values. Existing settings continue to use `ConfigService`, so
the legacy full-config renderer exposure remains until a separately scoped
credential-storage migration is possible.

## Attaching a parallel shell later

A future main-window route should inject `TarsRuntimeFacade` and call
`initializeApplication()`. Initialization is idempotent, so another component in
the same renderer cannot create a second backend. A secondary Electron or remote
renderer must instead call `attachToExistingApplication()`. That method sends the
existing `init_overlay` snapshot request and never invokes Electron's process-start
operation. Attached renderers do not perform autostart and cannot invoke the
coordinator's backend restart flow.

Either kind of shell can subscribe to the facade's application, interaction,
conversation, health, provider installation, alerts, configuration-summary, and
Elite-context streams. Configuration screens may continue using the existing
`ConfigService` command methods until narrower write interfaces are introduced.
Secondary renderers still do not receive persisted conversation history.

## Deferred transcript rehydration

The narrow follow-up is a read-only backend command such as
`get_conversation_history`, returning a bounded page of already-persisted
conversation/tool events from `EventManager`. A corresponding typed response can
seed `ChatService` or a facade-owned history store before live events are
appended. It needs stable event IDs, ordering, pagination, and duplicate handling.

Task 6A does not add that command because it would touch persistence and live
event ordering. It does not create another chat database or change memory
semantics.

## Observatory recovery compatibility

External integrations are not modeled as Journal or `Status.json` projections.
The typed external-integration contract can later carry status from a recovered
backend adapter without requiring a visual subsystem or changing the frozen TARS
behavior plugins. No event schema, JSONL reader, or Observatory replacement is
implemented here.
