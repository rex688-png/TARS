# Real-PC refinement: runtime and Settings

This stacked change starts at `hardening/runtime-fixtures-contracts@5cb42dc7e684c835a2ffa4462b5118005c6e5ef7`.
It keeps the working shell, provider abstraction, journal/projection pipeline and official behavior bundle.

## Settings and status

The five categories remain General, AI & Voice, Personality, Plugins and Diagnostics.
General retains readiness, Commander, Elite/overlay setup and keybind navigation; autostart is now there.
AI & Voice presents compact system cards with Configure / Advanced controls. Overlays, remote access,
accessibility, backup and developer controls remain behind Advanced application controls.
Personality owns the sole prompt editor, with Save, Reload saved, Reset and inline failure feedback.
Reactions remain accessible. Diagnostics retains raw actions/logs/usage and adds a read-only reported-state self-check.

Steel/charcoal card surfaces and cyan selection replace saturated orange Settings surfaces.
Activity and Elite freshness indicators change actual text/dot color, alongside their readable state labels.
The side panel reuses the global Elite freshness label and no longer adds an unexplained Journal UNKNOWN row.

The central frontend provider registry supplies human-readable names. Internal IDs remain configuration keys.
Registered, unselected/offline providers are **Installed**; startup is **Starting**. **Ready** requires the selected
component's observed initialization report. Failed loading uses the existing error settings signal.
No device or feed health is inferred from a saved selection. Unreported checks say **Not verified**.

The self-check reports the existing health snapshot, keybind counts and official plugin settings registrations.
It does not initialize models, test a microphone, send an Elite action, or claim that an Observatory feed is live.
Its build details read the actual package metadata, frontend commit and vendored provenance.
No separate backend version/branch is invented when none is reported.

## Provider persistence and saving

`ProviderSettings.migrate_provider_settings` retains every saved provider field across package schema initialization,
including values equal to older defaults. Absent fields can acquire package defaults; settings-version metadata advances.
Behavior-plugin migrations retain their existing semantics. The real module-loader regression exercises migration and reload.

Pocket-TTS's package, implementation, installation path and fresh two-thread default are unchanged.
The generic preservation layer prevents its old migration from clamping an explicitly saved token/thread value.
Users can keep their chosen tuning; aggressive values may still produce poor audio and need local testing.

The existing GUID-keyed config patch layer continues preserving unrelated provider settings on switching and partial edits.
MSI does not own these settings, but **physical MSI upgrade/reinstall verification is still required**.

`config_save_result` is an additive, request-ID-correlated acknowledgement after the existing config write succeeds.
Both offline and running command paths use it. A failed write returns the old config and a sanitized error.
Settings show Saving, Saved, or Error saving / unsaved changes; transport delivery alone is not a save.
The prompt continues using its existing dedicated persistence acknowledgement.
Legacy full settings still need credentials to operate; the general runtime facade remains secret-free.

## Action intent and confirmation

`ActionPolicy` gates the model-visible tool list and execution of consequential actions:

| Category | Behavior |
| --- | --- |
| Lights/gear/HUD and ordinary controls | Existing immediate behavior retained |
| Elite chat (`textMessage`) | Explicit send/post/type/chat intent; ordinary conversation is excluded |
| Weapons | Explicit fire/shoot/stop-firing intent |
| Cargo disposal | Explicit eject/dump/jettison/drop/purge cargo/materials intent |

The gate is deliberately conservative English command recognition, not an LLM classifier.
Questions, speculation, negated requests and “tell me a joke” cannot authorize chat input.
Direct messages require a recipient named in the request and reject the current commander/self.
Channels must be explicit and match the request. Empty, multiline and slash-command messages are rejected before game focus/input.

The existing `send_message` action retains its keystroke mechanism. Each chunk requires a new, non-historic,
matching `SendText` journal record with `Sent=true`, the exact message and destination.
No confirmation within three seconds returns **transmission not confirmed**, stops further chunks and does not claim success.
A timeout cannot establish whether Elite delivered the message: do not blindly retry it.
Real Windows validation must confirm the journal destination/message format, timing and multi-chunk behavior.
Other working action confirmation paths were not rewritten.

## Speech, discovery overlap and data precedence

Tool narration uses short generic cues (Searching / Checking). Raw queries/descriptions remain in diagnostic tool events,
and search-agent instructions prohibit narrating internal queries/arguments/reasoning.
The model-facing policy uses TARS/commander data wording; physical database names and upstream attribution remain unchanged.

Both Explorer and Observatory still deliver their complete facts. Prompt instructions ask for one combined callout,
retaining unique findings. For unsolicited exploration responses, assembly suppresses exact repeated sentences within
12 seconds in the same system/body context. Different numbers, body names and unique sentences remain.
Explicit user questions are not suppressed. Fully suppressed callouts are marked responded and complete their activity state.
This is deliberately not fuzzy semantic matching: differently worded equivalent findings still require live acceptance testing.

A shared preferred-facts block selects direct CurrentStatus balance/fuel/cargo, ShipInfo identity/model, Location and NavInfo.
Zero values remain valid. Ship/journal state supplies fallbacks where direct status is absent; route counts require a real route.
The model is instructed to prefer these latest projections over historical conversation/logbook values.
The snapshot does not itself prove live telemetry; fallback/current-cache freshness is explicitly unverified/last-known.
No journal/state processing or credit accounting is rewritten.

## Privacy and regression evidence

Normal startup logs report prompt length instead of its contents. Memory-update logs report length, not private memory text.
Repeated config-merge prints are removed. Existing diagnostics retain raw tool activity without adding credential logging.

The current golden snapshots intentionally change for the chat-tool/recipient descriptions and preferred-facts/response policy.
Other schema content is unchanged; native source-location offsets shift. Historical baseline provenance is retained.
Two dumps are byte-identical. Neither canonical prompt bytes nor the 27 bundled payload files change.
The bundle still verifies at `TARS-Plugins@67b1a1cab5a67d675372477dbcde061697e80bf5`.

## Validation

Local validation uses practical dependency subsets and hardware seams in host-neutral tests, not a packaged Windows runtime.
Focused tests cover real provider module loading/reload, config disk acknowledgement/failure, chat validation/confirmation,
generic spoken activity with retained raw diagnostics, exact discovery sentence suppression, source precedence and private log summaries.
Frontend tests cover provider states/names, save acknowledgement, prompt draft/failure handling, cards/status colors and existing shell/lifecycle regressions.

- Focused Python suite: **180 passed**; includes Task 1 snapshots/callbacks, Task 3–5 guards, GPT-6, providers,
  Observatory, journal/Status, actions, speech and refinement tests.
- Frontend: **31 passed**. Electron: **16 passed**. TypeScript and Angular development build passed.
- Full desktop-dependent PluginHelper tests: blocked locally by missing `pynput`; no desktop-input environment reconstruction attempted.
- Production Angular build: Google Fonts HTTP 403 during font inlining; no network workaround attempted.
- Windows CI: requested via the stacked PR; no polling or success claim.

**REQUIRES LOCAL PC VALIDATION:** MSI upgrade/provider reinstall and saved tuning; playback quality; real Elite chat
confirmation/timeouts; live Explorer/Observatory paraphrase overlaps; credit queries with fresh versus saved snapshots;
Settings contrast/layout and live provider transitions. No Alpha acceptance or merge is implied.
