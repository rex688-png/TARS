# Speech Director admission gate — Phase 2 / PR 2

Stacked on PR #15 (`feature/speech-lifecycle-tracing` at
`b4d0bb90dc9facdf5695d37ed0d5d8a605e25fd0`). That base contains PR #14/#13
and the six-plugin bundle from TARS-Plugins #22 at
`8c4223a8764db12f841fe3de3acf6836a63073e2`. No existing PR or plugin file is
changed by this PR.

## Rollout and configuration

`speech_director_mode` is an ordinary persisted configuration field:

| Mode | Behavior |
|---|---|
| `off` | No admission calculation or enforcement; existing speech decisions apply. |
| `observe` (default) | Calculate proposed admission and shadow attempt leases, then execute the existing reply path unchanged. |
| `enforce` | Stop an unsolicited turn before prompt construction/model generation when every candidate is stale, busy or a covered recent attempt. |

Use **Advanced settings → AI model → Spontaneous speech filtering**, then restart
the assistant, or use the existing `change_config`/configuration import path with
`{"speech_director_mode":"enforce"}`. Invalid updates are rejected. Old profiles
default to `observe`. There is no environment-variable override for the mode.
PR #15's `TARS_SPEECH_TRACE=1` remains the opt-in diagnostic switch. Decisions use
its existing structured `speech_admission` records with fixed reasons and counts;
payloads, domain identifiers, prompt text and conversations are not logged.

## Integration and safety

`EventManager.process` retains its original persistence, projections, side effects
and memory handling. Its existing call to `Assistant.on_event` informs the arbiter
of location epochs and user activity. `Assistant.reply_thread` reads the same event
history, then reserves admission before building the prompt or invoking a model.
The reservation is released in `finally`, including empty responses and failures.

Direct user messages and tool-result responses bypass unsolicited admission,
including stale-event and competing-turn restrictions. Suppressed events stay in
the event store and remain unresponded; the gate never calls `replied_before`,
deletes events or alters their payloads. They remain available as context to a
later direct question and to memory/projection updates. Existing successful-turn
bookkeeping is unchanged. Unclassified triggering paths fail open.

Source/priority metadata identifies user/tool (100), native gameplay (80),
Explorer/Observatory (60), Navigator (40) and optional Chatter (10). A mixed batch
is evaluated in that priority order and retains all original facts in the same
existing prompt. It makes one reply, rather than selecting a fixed announcement
template. This gate does not preempt a running reply or remove low-priority facts
from context. A lock protects reservations: competing unsolicited turns are
deferred with `reply_pending`, preserving distinct discoveries for retry. User
and tool replies do not acquire that unsolicited reservation.

## Conservative semantic identity

Explorer/Observatory identity includes explicit system address (or explicit system
name), body ID (or exact normalized body name), recognized finding type,
organism and progression stage. IDs take precedence. Missing/ambiguous identity
passes through; the current location is never substituted to invent an identity.
An ID-only event and a name-only event can therefore remain separate unless their
explicit identifiers agree. No fuzzy text matching or LLM classification is used.

Explorer's existing `scan_value` plus a recognized `planet_class` maps to the
corresponding finding. Observatory's explicit `finding_type` or a recognized
`notification:<finding type>` can match it. **`notification:BioInsights` and
`notification:Evaluator` name providers, not discoveries**; their generic records
are not sufficient for cross-source deduplication. Real Explorer payloads without
body IDs use the exact body-name fallback. This conservative boundary leaves
false negatives rather than silently losing valuable information.

All non-routing fields participate in fact coverage. A changed value or additional
field causes admission; a new valuable finding has a different key. Complementary
events in one batch contribute their union to the attempt record and both original
payloads to the existing prompt, preserving source-specific information. Late
complementary facts get another generation instead of being silently discarded.
DSS completion differs from discovery; organic samples 1/2/3 and different
organisms have separate identities. Incomplete organism/sample metadata passes
through. Generic Observatory notifications are never equated with generic biology.

Freshness checks use plugin guards or actual payload/journal timestamps, with a
60-second horizon and five-second future tolerance. A location epoch change clears
recent state and rejects events from before the change or an explicitly different
system. Different body identities never share suppression. There is no attempt
to withdraw speech already generating/playing when the ship changes location.

## Temporary attempt leases, not spoken acknowledgements

Admission alone does not seed recent suppression. A reservation covers only the
active unsolicited turn. After the existing TTS line finishes, a private evidence
field can distinguish `output_written`, `failed`, `cancelled`, `dropped`, `no_audio`
and `unknown`. This field is set at the existing write loop/exception paths. The
existing queue, callbacks, waits, retries and speech lifecycle trace meanings are
unchanged. Synthesis errors that the legacy generator catches still produce
failure evidence. An abort revision invalidates leases even if Stop speaking was
pressed after the write loop completed.

Only `output_written` may seed an **eight-second generation-attempt lease** for
identical/subset facts (bounded to 128 entries). Its reason is `recent_attempt`.
It is a temporary cost-control decision: accepted PCM writes do not prove device
drain, successful audibility or that every supplied fact was said. No event is
marked "announced" or "successfully spoken". After expiry the same finding may
generate again. User activity, cancellation, location/mode changes invalidate
state; unknown/drop/failure/interruption do not seed a lease. Nothing is persisted.

The existing post-generation `ResponsePresentation` sentence deduper and plugins'
dispatch-time callout bookkeeping remain in place. This PR does not upgrade those
legacy mechanisms to reliable playback acknowledgements. A full TTS result/drain
contract and per-fact acknowledgement remain future work.

## Chatter and model compatibility

`PluginHelper.preview_optional_speech()` is a small advisory seam for checking
host availability before preparing Chatter. It respects the configured mode and
uses existing diagnostics. It does not acquire a long-lived reservation. Chatter
has not been migrated to call it: its timer, topic choice, humor, silence, cooldowns,
three-candidate loop, output Director and transient direct-question retry remain
unchanged. Host admission after dispatch **does not save Chatter's preparation
calls**. PR 3 should integrate a cancellable pre-generation reservation and verify
personality/retry parity before migrating that path.

PR #15's `LLMModel.__init_subclass__` was reviewed against the supported OpenAI chat,
Responses, inherited Mistral implementation and Chatter's saved-bound-method
monkey-patch. A genuine descriptor issue is fixed on this branch: static/class
`generate` implementations retain their descriptor type. Inheritance, abstractness,
signature reflection and saved-original calls have regression coverage. There is
no second model output wrapper. A metadata-key collision in `SpeechTrace` is also
fixed so admission source overrides produce records instead of being silently lost.

## Deterministic generation comparison

With fake time, original host methods, fake LLM/TTS and a recognized canonical
Explorer/Observatory duplicate pair:

| Replay | off | observe | enforce |
|---|---:|---:|---:|
| Duplicate pair within the attempt window after output writes | 2 | 2 | 1 |

The automated tests assert the duplicate counts, fact/context retention, distinct
progression stages, location/freshness boundaries, mode transitions, atomic
concurrency, retry after busy admission, generation failures, cancellation and
actual fake-device write-loop evidence. PR #15's real Chatter candidate/guard
tests and all existing provider/STT/TTS/vision/action tests remain applicable.
These are controlled replay counts, not a measured reduction in live API traffic.

## Validation

| Check | Result |
|---|---|
| Full backend suite, tracing disabled | 395 passed; 9 pre-existing legacy fixture errors |
| Full backend suite, tracing enabled | 395 passed; same 9 pre-existing legacy fixture errors |
| New admission/compatibility regression cases | 44 passed (included above) |
| Current six-plugin suite at PR #22 | 89 passed |
| Electron suite | 16 passed |
| Bundle provenance | 27 files verified; bundle unchanged |
| Production UI build | Passed, including the new persisted-mode control |
| Dependency consistency and patch whitespace | `pip check` and `git diff --check` passed |

The nine errors are the existing `test/tars_baseline` fixtures demanding the exact
old five-plugin revision `685e16a19d5a5cd83f16297b90ee4c58ba8e11b5`, instead of the
current six-plugin PR #22 revision. Full-suite exit status remains nonzero. No
test was skipped, disabled or rewritten to hide those errors, and the external
plugin checkout was not downgraded. There were no new test failures or environment
blockers for this implementation. Live provider traffic, the running game and
physical audio/device drain were not tested.
