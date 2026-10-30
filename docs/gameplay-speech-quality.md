# Gameplay speech quality corrective sprint

Engineering record; not evidence of completed live-game acceptance. Host base:
`b3b3eb70e052566942497be9eabc943037eab306`. Canonical plugin base:
`794ca29cade61738e96f168f36052e76f26a2475`. Current bundled source:
`54c9161412e9478a9ffe8de2d0b505fbf37f89db` (six plugins, 27 payload files).

## Findings and corrections

| Gameplay issue | Evidence and confidence | Correction |
| --- | --- | --- |
| A: internal decisions | Confirmed: the old screen accepted both quoted decision strings. Assistant could persist them and queue TTS. Whether the recorded incidents actually played is unknown without delivery evidence. | Narrow unsolicited-only final-output screening before UI/TTS; explicit SKIP remains silent. Direct technical questions are exempt. Host/plugin instructions request final dialogue or SKIP, never selection notes. |
| B/E: overlapping discoveries and DSS | Confirmed: Explorer and Observatory independently request speech; the generation lease is short-lived and the old sentence cache was populated before successful playback. Different wording evades it. Exact producer attribution for the session remains unverified. | Shared semantic evidence ledger, explicit system/body identity and confirmed facts; record/update/announce before generation. Only explicitly voiced facts with completed audio output are committed. |
| C: combined alternatives | Confirmed with real SDK objects: Responses `output_text` concatenates text across messages, including commentary and final answer. Chatter returns a replacement candidate, not concatenated retries. The original session response envelopes are unavailable, so attribution to this SDK shape is a strong hypothesis. | Select one completed assistant final message. Reject ambiguous multiple unlabelled/final messages; retain text-part assembly within one message and tool calls. Reject explicitly labelled alternatives before output. |
| D: routine narration | Confirmed: Observatory registered every accepted live notification as reply-worthy. Raw Scan No reaction settings do not prevent plugin events. | Positively identified personal numeric records, descriptive atmosphere/landability and discovery counters remain context without creating a model call. Explicitly evidenced exceptional science and significant discoveries remain eligible; unknown producer schemas fail open. |
| F: inconsistent recommendations | Confirmed: completion callouts omit previously announced targets while the direct ranked list includes them. This can make the first remaining item look like the overall best target. The exact A3/A2 session cause is unknown. | Shared ranked-target and highest-priority-unmapped recommendation in completion, summary and action payloads; prompts distinguish full/history lists from current mapping recommendation. No inferred body-to-body distance or payout. |
| G: provider rejection/no response | Original invalid_prompt cause unresolved: no safe status/code/size evidence from the incident is available. Confirmed privacy defect: error handling could print request headers/body and provider response. | Bounded status/code/count diagnostics, no request/response content. Direct failures get a concise error indication; automatic failures remain silent. No speculative oversized-prompt fix or provider change. |

## Pipeline and delivery contract

Journal/relay data -> EventManager history and plugin projections -> domain
eligibility (`record`, `update`, `announce`) -> existing SpeechArbiter admission
-> model/output director -> final-message selection and unsolicited-output screen
-> existing formatting -> TTS/UI -> terminal playback evidence -> covered-fact ledger.

Facts are not removed from history. Raw React / No reaction / Hidden configuration
is unchanged. Normal questions retain all available context and bypass automatic
eligibility. A direct turn has a separate priority execution lock: it can finish
while an obsolete automatic HTTP request is still blocked. The outer Chat-loop
scheduling gate uses the same priority check; its entry-point regression failed
before the gate correction and passes in both modes afterward. Automatic peers remain
serialized; stale automatic output is discarded after generation. The underlying
synchronous HTTP request cannot be forcibly cancelled by this change.

The default Speech Director mode remains **observe**. Existing off/observe/enforce
admission rollout semantics remain; domain eligibility, final-output validity and
completed-delivery identity are correctness checks in every mode. No saved mode,
reaction, personality, provider or model default is rewritten.

`TTSLine` completion alone is insufficient. A fact is recorded as delivered only
when the terminal outcome is `completed`, `output_written` is explicitly true, the
speech epoch is still current, and the final text explicitly covers that fact.
This is evidence of audio output, not proof that a person heard it. Cancelled,
failed, unknown and no-audio attempts never create a heard-fact claim. The ledger
is bounded and session-local; returning to a known system preserves that session's
delivered facts, restarting the application does not.

Explicit system/address and body/name aliases are learned only from events that
supply both; conflicts fail open. Organism identity includes species, variant and
sample/completion stage. Additional unknown structured evidence fails open rather
than being silently merged. New genera or organism variants remain independent
opportunities. Multi-body output needs explicit body labels before its facts can
be committed; an unmentioned prompt fact is never assumed spoken.

## Deterministic before/after evidence

These are synthetic sequences, not new observations from Elite Dangerous.

| Sequence | Corrected result in observe and enforce |
| --- | --- |
| Explorer terraformable water world, then equivalent Observatory fact after the old lease expires | One model call / one completed response; differently worded repeat is an update. |
| Two sources report the same mapping | One completed mapping announcement; repeated mapping spends no second call. If valuable-body facts were already voiced, mapping alone is a silent update. |
| Mapping followed by confirmed new genus, species or variant | New biology remains eligible; completed organism identities do not collide. |
| Routine personal temperature record or ordinary mapped body | Zero generation calls; facts remain queryable. Explicit significant scientific evidence remains eligible. |
| Several ordinary scans configured No reaction | No raw scan reply; plugins still receive the journal data. A meaningful plugin discovery can still respond. |
| Internal decision, labelled alternatives, exact SKIP, empty model response | One attempted generation, zero speech/UI assistant bubbles. No private response text in diagnostics. |
| Chatter without a grounded opportunity | Zero candidate calls; existing silence/anchor checks remain. |
| Output-director rejects first candidate | Existing creative retry returns only the replacement; rejected draft is not quoted into the retry instruction. |
| Question arrives during blocked automatic generation | Two already-started requests may exist; direct answer completes first and stale optional output is not delivered. |
| Failed/cancelled/no-audio TTS | No delivered claim; a subsequent equivalent opportunity remains eligible. |
| System change / expired event during generation | Old automatic output is discarded, not presented as current. |

An opportunity that is admitted but model-selected SKIP still costs its generation
call. This sprint adds no classification calls. Repetition/quality retries remain
available when genuinely grounded; it does not impose a canned style or global
plugin mute.

## Changed implementation surfaces

- Host `ExplorationSpeech`: eligibility, semantic identities, delivery coverage.
- `SpeechArbiter`: candidate selection, freshness and terminal confirmation.
- `Chat` scheduling / `Assistant.can_start_reply`, `should_reply` and `reply_thread`: pre-generation eligibility, direct
  priority, stale-output rejection, final screening and delivery confirmation.
- `Models` Responses adapter: one final message; both LLM adapters: safe errors.
  Existing raw audio-provider error-body logging is also removed without changing
  provider execution.
- `ResponsePresentation`: narrow unsolicited-output validation; Assistant no
  longer uses its old current-location/sentence cache for cross-turn suppression.
- `PluginHelper` / `SpeechPolicy`: optional host hooks and final-output contract.
- Canonical Explorer: evidence payloads, genus/organism milestones and shared
  ranking; Observatory Bridge: meaningful reply check while retaining relay
  storage; Chatter: final screen and safer retry instruction.
- Pin verifier, provenance and two current installation/plugin pin references.
  No application version, installer identity, plugin manifests or saved profiles
  are changed.

## Validation and limitations

Local host suite: **716 passed**, six existing/test-environment warnings
(journal test thread termination and Pydantic serialization). Canonical plugin
suite: **116 passed**. The host suite includes real plugin/helper/event-manager
paths with controlled clocks, fake models and explicit fake TTS terminal results,
SDK message objects, all compatible bridge producer names, both rollout modes,
direct questions, departure warnings and existing six-plugin regressions.
Windows build/acceptance status belongs to the PR's exact source check, not these
Linux results. See the PR for current CI results.

Privacy-safe traces report event/source metadata, decision/reason, fact count,
generation attempts, screening outcome and terminal delivery outcome. They do not
record response text, private prompts, memory, API headers or hidden reasoning.

Remaining limitations: unknown producer schemas and ambiguous identities can
still create extra speech; conservative text coverage can miss a legitimately
spoken fact, especially localization or unlabelled multi-body prose. The narrow
unsolicited screen can reject a rare legitimate automatic technical sentence,
and cannot reliably identify two unlabelled alternatives in one final string.
No claim of universal semantic understanding is made. Known SDK multi-message
concatenation is prevented at assembly rather than patched with punctuation.
Other providers must satisfy the single-final contract. The in-memory ledger is
not durable across restarts. Duplicate notifications after a failed delivery can
retry deliberately. Existing general admission cooldowns are unchanged.

Required live acceptance: replay the original overlapping Observatory/Explorer
session with actual producer payload schemas, verify rare science/biology and
early-departure warnings, responsiveness during slow provider calls, subjective
humor/repetition quality, installed Observatory feeds, Windows microphone/speaker
playback, and real Elite Dangerous context. No physical Windows, audio or
111-minute gameplay rerun was performed in this environment.

Merge canonical plugins first, preserving the pinned commit in history; merge
the coordinated host PR only after its bundle provenance and Windows checks pass.
Both PRs remain Draft; no release or merge is authorized by this sprint.

## Resumed corrective sprint (2026-10-30)

Verified GitHub draft #24 at host `3a2a6a2c523a8a7c4f8742572f24e9003012724e`
and canonical draft #27 at `a302b33b742d787df27cc8089f3a716fac54e5cd`.
Both matched clean local checkouts; `main` remained at the bases recorded above.
No disconnected corrective edits were assumed. The original 27-file bundle was
verified against its exact canonical pin before editing.

The follow-up host branch is stacked on #24. Canonical follow-up draft
[TARS-Plugins #28](https://github.com/rex688-png/TARS-Plugins/pull/28) is stacked on
#27. The host now pins canonical commit
`54c9161412e9478a9ffe8de2d0b505fbf37f89db`; all 27 payload hashes match its Git
objects, including unchanged Navigator, Galaxy, Expedition and Observatory files.
Earlier validation numbers above describe the earlier PR heads.

Confirmed fixes:

- `system_complete` has a system-scoped semantic identity in admission and the
  delivery ledger, independent of body identity. Canonical milestones explicitly
  carry the known system address. Completion, authoritative body count, confirmed
  composition and significant summary counts are evidence with their actual
  values. Equivalent Explorer/Observatory findings are updates after completed
  output; revised counts or genuinely new facts remain announcements. No body ID
  is synthesized from the current location.
- An empty unresponded-event list returns before prompt construction or model
  invocation on every reply-worker entry. Deferred events are restored before
  this check; retries with retained events, direct questions and tool results
  still run. One older DSS fixture took an event directly from the incoming queue
  without emulating EventStore's unresponded row; it now does so explicitly.
- Whole-output `Silence.`, `No response.`, `SKIP` and explicit equivalents are
  intentional non-delivery before TTS, assistant-speaking/overlay notifications
  or conversation persistence. Exact matching tolerates quotes, marker brackets,
  case and terminal punctuation; longer sentences discussing silence survive.
  Tool actions returned alongside a marker are still executed.
- Chatter recognizes intentional abstention before candidate quality rejection,
  Director regeneration and retry fallback. This also works on legacy hosts.
  Candidate attempts and real Director integration are tested, including user
  discussions of silence. Existing personality, novelty gates and natural
  creative retries for actual weak dialogue remain in place.
- Opt-in `TARS_SPEECH_TRACE=1` adds opaque `generation_id` and `delivery_id` fields.
  `generation_id` groups a host model request and its concrete `attempt_id` values;
  `delivery_id` is the existing TTS line identity. A new generation gets a new
  generation ID; a new queued line gets a new delivery ID. Device retries keep
  both IDs and get distinct playback attempt IDs. TTS lines capture the generation
  context across worker threads. Existing salted event IDs tie reply events to
  their trace; no journal payload, response text, body/system names, prompt or
  credential is added to these diagnostic records. IDs do not prove audibility.

Validation on the final code:

- Full backend with tracing enabled: **814 passed**, six dependency/serialization
  warnings, no skips or errors. The preceding default-tracing run passed all
  **811** tests then present; three additional direct-Chatter discussion cases
  also pass in the final traced run.
- Canonical plugins: **119 unittest cases passed**.
- Frontend: **34 passed** using `node test/frontend/run-tests.mjs`.
- Electron: **16 passed** using Node's `--test-isolation=none` runner.
- `pip check`, both `git diff --check` runs and exact canonical bundle
  verification passed. Docs strict-build result is recorded with the PR.

The new regression module is `test/lib/test_speech_corrective.py`. Its fake
models/TTS reproduce cross-source completion repeats, changed censuses, new
biology, failed-output retry, empty-history polling, retained deferred work,
Director abstention, user discussion and playback-attempt identity. Existing
exploration, warning, Chatter, settings and historical snapshot tests also pass.

Remaining uncertainty: actual incident payloads and physical audio are still
unavailable. Unknown producer schemas, unrecognized scientific details,
nonempty target recommendations and incomplete lexical coverage deliberately
fail open and can permit extra speech. Summary completion does not acknowledge
an unspoken target discovery. The ledger remains bounded and session-local;
restart replay is not permanently suppressed. Windows/live-game acceptance and
subjective Chatter quality require real playback. Prior Windows results on #24
are not results for this new head.

All No reaction journal settings, stored user profiles, event ingestion and
Combat development remain unchanged. Only draft PRs are created; no merge,
tag or release is performed.
