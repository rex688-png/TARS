# TARS RC #20 — Phase 1: speech reliability and presentation

Base: PR #19, `feature/quiet-first-discovery-tallies`, verified at
`8c3511c1e68fbf048c0fc621ed04c5e8db4e2e07`. This branch targets that parent,
not main. No integration, merge, retargeting or later RC phases are included.
The six-plugin bundle stays at TARS-Plugins #23,
`fef38e9f11350555d7b06dbcc88d13d52ddcfa8e` (27 verified files).

## Host silence boundary

After the existing model/output wrappers return, Assistant discards a complete
`SKIP` marker before presentation, TTS or assistant conversation insertion.
Whitespace, case, simple/curly quotation marks, backticks and a single trailing
period/exclamation mark are accepted. Sentences containing “skip” are ordinary
responses. User input is never filtered by this guard. Real tool actions still
execute when accompanying sentinel text.

The no-action path uses the existing empty-turn bookkeeping: mark only the
processed snapshot handled, emit one assistant-completed event and release host
ownership in `finally`. No TTSLine or successful speech evidence is manufactured.
A new question arriving during generation remains pending and is answered on the
next turn. The guard applies in all three admission modes; their priority and
reservation mechanisms are unchanged.

## Body display versus speech

The existing host response policy requests compact short body labels. The new
`BodyPresentation` helper applies only to the returned assistant text, never to
journal events, projections, tool arguments, navigation targets or stored settings.

Explicit “body/planet/moon/world” references can become `A5`, `A2`, `B3`, `AB4`.
Bare labels and sentence subjects additionally require an actual body-name field
from Location or the current events. The TTS copy uses “A five” while the chat
and assistant conversation retain `A5`. It does not infer a label from BodyID or
system names. Ambiguous phrases, full procedural names, satellite suffixes,
leading-zero identifiers and unsupported labels remain unchanged. Supported short
labels have uppercase A–D star components and planet indices 1–99. This is a
conservative fallback for model formatting, not a general name canonicalizer.

## Actual numeric gaps

Before changes, the existing SpeechText normalizer already correctly spoke
multi-million/billion amounts, decimal distances and percentages. Those paths
and their tests are preserved. The observed gaps were:

- `-0.3 ly` became `-0.three light-years`: the regex matched only a decimal tail.
  Explicit signs and numeric-token boundaries now preserve the complete value.
- Standard journal sale text `credits (base: ..., bonus: ...)` left the base and
  bonus as digits. Only that unambiguous credit-breakdown form is now expanded.
- Explicit `gravity: 0.3 g`, spaced `atm`/`Pa`, atmospheres and pascals had no
  normalization. Gravity requires its label, avoiding an assumption about grams;
  attached `12PA`/`2ATM` designations stay unchanged.

Visible amounts remain numeric. Pronunciation still runs through the existing
`TTS._playback_one -> normalize_spoken_quantities -> synthesize` path; the TTS
engine, voices, volume, speed, device settings and PR #18 terminal contract are
unchanged. No dependencies or OpenAI calls were added.

## Executed validation

Two implementation/test cycles, both passing: first 284 tests, then **288 passed,
zero failed/skipped** after tightening leading-zero/body and unit-abbreviation
ambiguities. The final run included 71 new parameterized cases plus all 33 existing
SpeechText cases and focused speech/admission/TTS/Observatory regressions:

```bash
source /workspace/.setup/runtime.sh
python -m pytest -q \
  test/lib/test_rc20_presentation.py test/lib/test_speech_text.py \
  test/lib/test_speech_trace.py test/lib/test_speech_arbiter.py \
  test/lib/test_chatter_admission.py test/lib/test_tts_terminal_outcomes.py \
  test/lib/test_release_candidate_boundaries.py test/lib/test_speech_policy.py \
  test/lib/test_TARSObservatoryBridge.py
python tools/verify_tars_bundle.py --source /workspace/TARS-Plugins
```

Coverage includes all admission modes, no TTS/chat/conversation insertion for
sentinels, action preservation, a deferred busy retry followed by silence and a
new user question, exact display-versus-speech separation, malformed numbers,
procedural names, ship/module labels and a real TTS worker with fake synthesis
and PCM output. The latter asserts spoken Vista base/bonus amounts and distance,
numeric chat, output-write completion and unmodified source state.

The saved configuration hash was identical before and after final validation.
No plugin repository or bundle changes were made. Logs are saved locally as
`/workspace/.setup/rc20-cycle1.log` and `rc20-cycle2.log`; no Commander logs or
private configuration are committed.

## Remaining validation and scope

These are deterministic fake-provider/stream tests, not real-device or live-game
validation. Provider pronunciation and human audibility still require real testing.
Ambiguous/unsupported body expressions and units are deliberately left unchanged.
A full Python suite, production/installer build, full six-plugin runtime validation
and release integration were not run during this bounded Phase 1 task. Existing
bundle integrity and host/plugin compatibility paths were checked as above.
Later Explorer, Chatter, accuracy/payout and main integration phases remain deferred.
