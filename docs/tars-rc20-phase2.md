# TARS RC20 Phase 2 — Explorer timing and DSS quality

Continuation of host `feature/tars-rc20` after Phase 1 commit
`0001fdf487e35bb9e7cdb96a813dc8271a95e2f4`. The PR still targets #19;
main and Phase 3 are untouched. Canonical Explorer source is in companion
[TARS-Plugins #24](https://github.com/rex688-png/TARS-Plugins/pull/24), stacked
on #23. New pinned source:
`f68fa83b1d2a83d5553623e5860e6feb3b8b64e7` (Explorer 1.4.10).

## Verified trigger and routing

The selected trigger is the rising conjunction in a **raw StatusEvent**:
`flags.FsdCharging && flags2.FsdHyperdriveCharging && !flags.FsdJump`.
It is not assumed to be a journal GameEvent. The actual source chain is:

1. StatusParser reads Status.json, parsing FsdCharging from Flags bit 131072,
   FsdHyperdriveCharging from Flags2 bit 524288, and FsdJump from Flags bit
   1073741824. Its file worker polls once per second.
2. `_process_status_update` queues raw `Status` **before** derived delta events
   such as `FsdCharging`.
3. Chat drains status_queue into `EventManager.add_status_event`; EventManager
   persists/projects each event and invokes all registered sideeffects.
4. PluginHelper's existing sideeffect wrapper exposes the StatusEvent to the real
   Explorer Session entrypoint. Explorer previously accepted only game events.
5. A newly confirmed hyperdrive charge dispatches a guarded unfinished-target
   opportunity. `StartJump` no longer creates a reminder; it invalidates one.

FSDTarget can be selected without departing, so is not used as intent evidence.
Generic FsdCharging also includes non-hyperspace activity. Missing Flags2 fails
quietly rather than guessing that a jump is imminent. No STT/status parser,
provider or journal routing was changed.

## Warning eligibility and stale handling

Targets use Explorer's existing priority scoring and actual unfinished work.
Known valuable worlds and confirmed unsampled genera are included; unknown value
is never estimated. One short line identifies the top body's unfinished mapping
or sampling. The full payload retains up to three ranked targets.

A snapshot signature is attempted once per system visit, even across cancelled
or repeated charging attempts; intentionally skipped unchanged work does not nag.
Material target changes allow another warning. Cancellation, target completion,
StartJump, FsdJump status, system change, session change or a three-second expiry
invalidate queued warnings. A departure latch rejects late charging statuses
following StartJump; the first regression run demonstrated this race and the
second run verifies its correction.

When this is the only eligible response, Assistant bypasses **both prompt
construction and LLM generation**. This avoids spending the charging window on
model commentary. A direct question, tool result or competing enabled safety/event
response keeps its normal path and priority. Existing SpeechArbiter ownership and
busy retry behavior remain in effect; no new suppression modes are introduced.
The actual plugin predicate is checked again through TTS `drop_if`. A warning
dropped before speaking is not inserted as an assistant reply, and completion
bookkeeping still runs. Invalid warning-only turns finish without model calls.

This makes an earlier cancellation opportunity possible when speech is idle and
synthesis responds promptly. It is **not a live-game timing guarantee**: up to
one Status polling interval, the Chat poll, an active reply/output queue and TTS
latency remain. The change does not interrupt active higher-priority speech.
Already playing/submitted PCM can finish; the guard prevents starting stale queued
warnings, not unsaying audio already delivered. No jump is cancelled or prevented.

## DSS behavior

`SAAScanComplete` still records `dss_mapped` and actual efficiency before any
speech decision. Ordinary low-value mapping remains silent. Meaningful mapping,
terraformability and biology retain existing milestone selection and same-body
cooldowns. Successful automatic DSS payloads omit routine efficiency/probe fields;
a failed target on a worthwhile body includes the actual probes and target.
Explorer's DSS prompt and the host response policy discourage successful-bonus
recitals and repeating discovery prose. Explicit efficiency questions still have
actual journal/Explorer summary data available. Saved event preferences are not
changed, including the native SAAScanComplete reaction (default off).

Existing Explorer/Observatory assembly and conservative deduplication remain;
this does not claim semantic equivalence detection for every possible generated
phrase. Chatter source/admission/retries and the other five plugins are unchanged.

## Executed tests and bundle assembly

- First cycle: plugin suite 99 passing / one failing regression (late charging
  after StartJump); new real-host integration file 10 passing.
- Second/final cycle: **100 canonical plugin tests passed**, and **298 focused
  host tests passed**, zero failures/skips. The host set includes all Phase 1,
  #19 policy, speech admission, Chatter, typed TTS outcomes and Observatory tests.
- New tests cover actual StatusParser queue order -> EventManager -> real Session
  Explorer -> registered host predicate -> fake TTS; warning-only turns have zero
  model calls in off/observe/enforce. Direct/safety competition follows the normal
  response path. Cancellation, expiry, departure, next system, repeated attempts,
  material biology changes, quiet ordinary DSS, meaningful mapping and failed
  efficiency are covered. Real TTS worker/drop testing verifies no output writes
  or chat insertion for a warning invalidated before playback.
- Saved config hash was identical before and after final host tests.
- Canonical source was committed first. The two changed Explorer payload files
  were copied into the host bundle, PINNED_SHA advanced, and provenance regenerated
  using `python tools/verify_tars_bundle.py --write --source /workspace/TARS-Plugins`.
  All **27 files across the six plugins/prompt** matched the exact pinned Git
  objects. No Chatter or other plugin file was edited.

Commands (after sourcing `/workspace/.setup/runtime.sh`):

```bash
python -m unittest discover -s /workspace/TARS-Plugins/tests -v
python -m pytest -q test/lib/test_explorer_departure.py \
  test/lib/test_rc20_presentation.py test/lib/test_speech_text.py \
  test/lib/test_speech_trace.py test/lib/test_speech_arbiter.py \
  test/lib/test_chatter_admission.py test/lib/test_tts_terminal_outcomes.py \
  test/lib/test_release_candidate_boundaries.py test/lib/test_speech_policy.py \
  test/lib/test_TARSObservatoryBridge.py
```

Logs: `/workspace/.setup/rc20-phase2-*-final.log`. Tests use synthetic events,
controlled clocks and fake audio/model providers. No real-device or live-game
result is claimed. Full release builds/integration remain a later phase.
