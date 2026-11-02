# Combat critical-alert decision diagnostics

This extends SpeechTrace/Black Box, not Combat policy. Host baseline is Draft #31
`59859fce2a1751e352bc317c80705fc08a91dfa4`. Its pinned Combat baseline is
`83caceaca39712d1c84e4337a09b020b087125ae`; the instrumented canonical dependency
is Draft [TARS-Plugins #30](https://github.com/rex688-png/TARS-Plugins/pull/30),
`7450db03a7b3bed7920994f3632634dde111566d`. All 32 vendored files must match
the updated provenance manifest. Previous corrective, Combat, Black Box and
reliability branches remain untouched; the prompt experiment is excluded.

## Correlation and meaning

Follow the source `event_id`/`journal_id` through telemetry decisions, then
`alert_id` through dispatch, speech and TTS. `source_event_id` preserves the
creation event across later clock ticks or queries. Plugin-dispatch event IDs
identify the queued alert event; they are not the original journal event.
`delivery_id` identifies one TTS line; `attempt_id` distinguishes playback retries.

| Observation | What it establishes |
| --- | --- |
| `combat_telemetry_accepted` | The existing tracker freshness/order/dedup gates accepted this critical candidate. It does not promise an alert. |
| `combat_telemetry_rejected` | A specific existing early-return gate rejected it. |
| `combat_alert_not_created` | A specific state, identity, context or cooldown branch prevented creation. |
| `combat_alert_created` | The alert exists in tracker state, with its unchanged five-second source-time expiry. |
| `combat_alert_removed` | Expiry, context/condition change or scope reset removed it. `dispatched: false` means no completed dispatch call is known; `true` means a dispatch returned. Absence of that field means the bounded correlation context is unavailable. |
| `combat_alert_dispatch_requested` | The plugin is about to call the existing helper. |
| `plugin_dispatched`, `combat_alert_dispatched` | The existing helper dispatch/queue operation was observed and returned. This is not speech or delivery. |
| `combat_alert_dispatch_rejected` | Dispatch is disabled or the alert was already dispatched. |
| `combat_alert_dispatch_failed` | The dispatch call raised; only its exception class is recorded. Partial side effects cannot be inferred from an arbitrary failing helper. |
| `combat_alert_scheduling_deferred` | An actually evaluated host gate was closed: reply gate, STT capture or audio busy. No additional gate evaluation is performed for diagnostics. |
| `combat_alert_revalidation` | Provider validity/settings result, recorded only when it changes. `alert_unavailable` does not invent the reason an absent alert disappeared. Join to any prior removal record. |
| `combat_alert_speech_selected`, `combat_alert_speech_validation` | The deterministic alert route was selected and the actual provider/pending-direct-turn check was evaluated. |
| `combat_alert_speech_rejected` | Direct/tool turn priority, selection of the last pending alert, or rejection of the containing arbitration batch. A batch rejection is not misrepresented as an individual arbiter verdict on the alert. |
| `combat_alert_tts_submitted` | The existing TTS call returned a line token. |
| `combat_alert_audio_rejected` | Submission raised before a line was returned. |
| Existing synthesis/playback/attempt/`line_completed` records | Actual audio lifecycle and terminal evidence, now correlated to the alert. |
| `combat_alert_delivery_observed` | The host observed the existing immutable terminal line outcome and available byte/drain evidence. |
| `combat_alert_evidence_unavailable` | The host received a critical candidate but no Combat provider was registered. It does not guess why the provider is missing. |

`source_time` is the source UTC epoch time, when the existing path parsed it.
`source_age_ms` is signed; negative means future evidence. Invalid or unparsed
timestamps are not invented. `combat_enabled`, `alerts_enabled`, `focus_enabled`
are the actual effective plugin values at the observation; only real booleans
survive Standard metadata filtering. `fighter_identity_known` means non-null,
not that an identity was independently verified. No raw fighter ID is recorded.

## Existing reasons, without new decisions

Telemetry: `historic`, `invalid_timestamp`, `future_telemetry`, `stale_telemetry`,
`before_scope`, `out_of_order`, `duplicate_telemetry`. The existing accepted range
is from two seconds future through thirty seconds old, inclusively.

Fighter state: `missing_fighter_identity`, `invalid_fighter_identity`,
`missing_combat_context`, `unchanged_fighter_state`, `prior_loss_unconfirmed`,
`cooldown`. Identity policy is unchanged: non-null hashable values retain their
legacy behavior; unhashable values still cause the original error. Observing that
error does not introduce new validation or silently discard it.

Other existing safety gates: `danger_or_damage_unconfirmed`,
`mothership_context_unconfirmed`, `unchanged_shield_state`, `invalid_hull_telemetry`,
`threshold_already_crossed`, `hull_not_decreasing`, `critical_hull_unconfirmed`.
Heat non-creation diagnostics report changes of the observed condition, not ticks.

Plugin lifecycle/settings: `combat_disabled`, `alerts_disabled`,
`already_dispatched`. Removal: `expired`, `condition_changed`,
`combat_context_lost`, `scope_reset`. In particular, an accepted loss six seconds
old can create an alert which immediately expires **before dispatch**. Its
creation/removal chain, with `dispatched: false`, makes that observable.

Host speech: `reply_gate_closed`, `stt_capture_active`, `audio_busy`,
`direct_turn_priority`, `last_pending_alert_selected`, `batch_admission_rejected`,
`provider_unavailable`, `direct_user_pending`, `provider_revalidation_failed`,
`audio_submission_failed`. These are observations of the existing host path, not
new policies. Tool/direct-user priority and all action permissions remain intact.

## Privacy, bounded volume and failure isolation

Standard emits fixed codes, safe flags, source age/time and session-salted alert
correlation only. No commander/pilot identity, raw journal, fighter ID, full text,
prompt, credentials or hidden model reasoning is added. The existing strict public
metadata allowlist and separate private export boundaries remain in use.

No new logger, model call or disk writer is introduced. The optional canonical
`record_combat_diagnostic` observer is exception-isolated and older hosts can omit
it. Black Box remains bounded/best effort. Clocks log actual alert removal once,
not repeated invalidity checks. Revalidation and scheduling report changed results;
cooldown repeats are reported once per preceding alert. Duplicate incoming records
are observed once each, never once per pending-event rescan. Diagnostic state is
bounded to 512 plugin states and 256 host alert-source/gate entries per map.
If source context is absent/evicted, `evidence: source_context_unavailable`
explicitly limits correlation. There is no lossless-session guarantee: drops,
rotation, crashes, a missing plugin/observer or failed storage can still remove
evidence. Absence of a reason alone is not proof of intentional silence.

## Validation and the October 30 incident

The original journal/settings remain unavailable. The October 30 cause is still
unconfirmed; a synthetic test aligned to `2026-10-30T20:25:59Z` assumes a valid
fighter ID and enabled alerts to prove the complete instrumented path. It does
not claim those missing historical facts were recovered. Use the existing
[original-evidence checklist](fighter-destroyed-evidence-request.md) for diagnosis.

Tests cover tracker gates and exact boundary times, late expiry before dispatch,
disabled settings, invalid identities, rapid repeats, cooldown, changed
revalidation/scheduling results, direct/tool priority and batch arbitration,
callback failures, Standard privacy and real playback code with fake audio
failure/cancellation/synthesis/output outcomes. A golden replay digest captured
from original canonical `83caceaca…` compares every policy snapshot, alert,
watermark and acceptance result with observers absent, enabled or throwing.
No warning text, thresholds, clock reads used for decisions, gameplay actions,
permission checks or model behavior are changed. Extra observation work is not
a claim of zero overhead or real-time acceptance.

A completed write loop and positive byte count are software output evidence;
**audibility remains unknown**. Physical Windows audio/device recovery and live
Elite acceptance remain necessary. Current test results and Windows CI are in the
coordinated Draft PR descriptions. The existing automatic MSI build may run as
authorized; findings must be reported before any new installer is shared.
