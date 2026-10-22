# TTS terminal outcome contract — Speech Director PR 4

Base: TARS #17 `feature/chatter-host-admission`, compatible with TARS-Plugins #23.
No existing pull requests or plugin branches are modified.

## Contract

`src/lib/TTSOutcome.py` contains immutable `TTSAttempt` and `TTSResult`.
Each queued text line has a unique `line_id`. Each dequeued/retried playback
has its own `attempt_id`. `TTSLine.wait_for_result(timeout=None)` returns the
terminal result (or `None` on timeout) while `wait_for_completion()` and
`mark_completed()` remain available for legacy callers. `result` is a
read-only property, initially `None`.

Terminal outcomes:

- `completed`: output write loop returned with no observed error and accepted
  non-empty PCM. `output_written` is true only here; not proof of audibility.
- `cancelled_before_start`: queued item cancelled before it starts playback.
- `interrupted`: aborted during synthesis or after playback begins.
- `dropped`: `drop_if` declined the queued request.
- `synthesis_failed`: synthesizer returned a failure indicator.
- `output_failed`: output/device error after the bounded retry budget.
- `no_audio`: line returned without any audio bytes.
- `unknown`: deliberately conservative fallback when legacy code manually
  signals completion with no playback evidence.

`output_drained` remains `None`: PyAudio `stream.write` success is not
an output-device drain acknowledgement. Neither it nor completion proves
the commander actually heard a word.

Audio-file requests also have internal `TTSLine` lifecycles without changing
the legacy `play_audio_file()` return type. Missing files may be retried; an
empty path finishes as `no_audio`.

## Callbacks, cancellation and retries

Callbacks now attach to line terminal settlement and run **at most once**.
Intermediate output failures get attempt records and requeue without firing the
completion callback. A third failed attempt settles the line `output_failed`
instead of retrying without bound. `on_start` is not replayed on retries.

`abort()` sets its cancellation flag and revision before draining the queue,
then settles every drained line `cancelled_before_start` and invokes its callback.
An active line observes the abort revision and finishes as `interrupted` even if
some PCM writes returned. Terminal settlement is guarded by a lock, so a repeated
abort/callback cannot complete the same line twice.

The existing `_playback_evidence` string is retained solely for compatibility
with legacy/fake callers. Production Assistant uses `TTSLine.result` to seed
the existing SpeechArbiter's eight-second **generation-attempt** lease only
after a `completed` result with accepted PCM bytes. Unknown/failure/cancelled
outcomes do not become spoken acknowledgements.

## Privacy and limitations

SpeechTrace emits fixed outcome codes, opaque IDs and numeric byte counts;
no conversation, prompt, generated speech or exception text is emitted.
The trace remains opt-in. No OpenAI requests are added.

The current runtime worker remains open-ended for a permanently unavailable
audio device before the queue can be consumed; startup/device-opening failure
recovery is outside this scoped change. OS/device buffer drain and human
audibility remain unknown. End-to-end real hardware and game testing remain
necessary before deployment.

## Validation

Deterministic tests: `test/lib/test_tts_terminal_outcomes.py` plus existing
`test_speech_trace.py`, `test_speech_arbiter.py`,
`test_chatter_admission.py`, and source-isolation boundaries.

GitHub Actions will run on the draft PR. Historical audit fixtures require
a detached legacy plugin revision; report that mismatch separately from
new failures. No existing tests should be skipped or weakened.
