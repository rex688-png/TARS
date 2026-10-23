# Gameplay speech quality corrective sprint

Engineering record; not evidence of completed live-game acceptance. Host base:
`b3b3eb70e052566942497be9eabc943037eab306`. Canonical plugin base:
`794ca29cade61738e96f168f36052e76f26a2475`. New bundled source:
`a302b33b742d787df27cc8089f3a716fac54e5cd` (six plugins, 27 payload files).

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
