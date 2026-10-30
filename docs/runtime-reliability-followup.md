# Runtime reliability follow-up — Black Box baseline

This is a focused follow-up to the [PR #27 audit](https://github.com/rex688-png/TARS/blob/fix/integration-reliability-audit/docs/integration-reliability-audit.md),
not a repeat of its completed journal, queue-isolation, stream-close and shutdown
fixes. Baseline is unchanged Draft #29 at
`88dce2630d19faccc6a4047da0e3b3e6a3d6b9f4`, directly above #27
`98499ec4ab9ad59d42f05c47e586ac0a507bb884`. The prompt experiment is excluded.
Remote heads and ancestry were checked before editing. The new branch is
`fix/runtime-reliability-followup`; existing branches and the #29 test MSI remain
untouched. Canonical payload remains the exact 32-file `83caceaca39712d1c84e4337a09b020b087125ae`
pin. No plugin, prompt, Combat, permissions or packaging changes are required.

## Confirmed defects

Priorities describe possible impact, not observed gameplay incidence. Reproductions
execute production methods with deterministic fake processes/devices; none execute
game controls or make model calls.

| Priority | Mechanism and affected path | Reproduction and correction |
| --- | --- | --- |
| P1 | `electron/index.js`, `BackendService.startProcess`: signals the current child and immediately spawns another. Concurrent starts create further children before any old `close`; they can contend for the same database, audio devices and plugin state. `sendJsonLine` also forgets a live child after a pipe exception. | On unchanged #29, two starts after initial startup produce **three children before the first closes**. The pipe-error regression independently reproduces premature replacement. Coalesce concurrent starts, await old `close`, retain ownership after pipe/process errors, and fail the restart after ten seconds without force-killing or spawning a competing process. Window close cancels pending replacement. Tests cover timeout cleanup and retry. Actual database corruption was not reproduced. |
| P2 | `BackendService.startProcess` appends the same window and a new window-close closure on every start. Each closure retains its old child. Notifications multiply and listeners accumulate for the lifetime of the window. | After 16 starts, unchanged #29 retains **16 close listeners** and duplicate window recipients. Deduplicate window attachment, install one close hook per window, and release child output handlers at process close. Regression verifies one notification and one close listener after 16 starts. This is a frontend notification path; it does not establish duplicate TTS playback. |
| P2 | `src/lib/STT.py`, `_get_microphone`: creates a PyAudio owner per capture but only closes its stream. Enumeration failure and failure of both opens also abandon the owner. The installed PyAudio class has no destructor. Repeated PTT or recovery can retain native PortAudio resources. | Four baseline cases fail: normal close, enumeration failure, both opens failing, and stream-close failure. An owned microphone wrapper forwards reads, closes once and terminates its owner even when stream close raises; failed construction terminates immediately. Device selection/fallback and transcription policy are preserved. Fake-owner tests prove balanced ownership, **not a measured Windows handle leak rate**. |

Before fixes, all three original restart/window regressions and all four ownership
cases fail. The broken-pipe regression was also run failing before its correction.
The final suite additionally covers the process-error/close ordering, successful
fallback ownership and existing audio-worker failures.

## Checks that did not establish additional defects

- **Concurrent processing:** four callers process 2,000 queued synthetic events
  through the real `EventManager.process`. Callback order and exact-once delivery
  are preserved and only one persistence commit occurs. This tests writer
  serialization, not immutable reader snapshots or real database contention.
- **Black Box interference:** block the recorder writer in storage maintenance;
  four producer threads complete 8,000 record calls without waiting for storage.
  The eight-entry queue remains bounded and reports drops. Existing recorder tests
  cover rotation, restart/torn files, disk errors, export privacy and concurrent
  writing. No change to Black Box admission, tracing or storage is justified here.
- **Plugin stop isolation:** an injected first-plugin stop exception does not skip
  the next plugin. Inspection of the pinned lifecycle paths shows Observatory's
  bounded worker join and Chatter's wrapper restoration. This is not evidence
  that every provider/native worker stops after an indefinitely blocked call.

## Unresolved risks and tonight's observations

These continue the specifically unresolved #27/#29 risks; they are not newly
discovered gameplay incidents, and have no claimed measured failure frequency.

| Risk / mechanism | What to watch and preserve |
| --- | --- |
| **P2 long-session retention:** `EventManager.processed` appends every processed event; journal startup history and persistent event storage also retain records. The 2,000-event test confirms retention, not a steady-state bound. Retention changes require memory/query/replay compatibility work. | Record backend PID, working set, private bytes and handle/thread counts at startup and every 30 minutes. Compare quiet periods and scanning bursts; note database size. Growth alone is not proof of a leak. |
| **P2 blocked shutdown/provider calls:** joins remain bounded; provider/native I/O and plugin stop hooks can outlive normal cleanup. Constructor failures precede run cleanup. | Watch delayed Stop, microphone remaining busy, surviving backend PID, missing session stop and subsequent unclean-session evidence. With this follow-up, a restart timeout should leave the old process owned and start no replacement. On tonight's unchanged #29 MSI, avoid repeated Start while the old process remains alive. |
| **P2 mutable state readers:** `get_current_state` returns live projection objects; the writer lock does not provide an atomic multi-projection snapshot to asynchronous consumers. No incorrect action or concrete mixed-state output was reproduced. | Mark the time of any stale/contradictory target, location or ship answer. Keep the correlated event/tool/generation IDs. Do not infer a race solely from model wording. |
| **P2 native plugin reload ownership:** module/path/DLL handles remain process-lifetime resources. There is no demonstrated supported in-process hot-reload scenario or measured leak rate. | Compare counts across **backend process** restarts; check one plugin startup per new PID and cessation of prior-PID output. Avoid unsupported in-process reload experiments during acceptance. |
| **P2 diagnostics evidence loss:** full queues drop records; rotation removes old segments, and disk errors disable recording. Maintenance/export shares disk bandwidth, though producers do not wait for the writer. Synthetic tests do not measure contention with Windows antivirus or actual game I/O. | Check recording status, queue depth, dropped/pruned counts and disk space at intervals. Export checkpoints before retention removes early evidence. Record any gameplay/audio hesitation when opening Diagnostics or exporting, with clock time. Sequence gaps are missing evidence, never proof that TARS intentionally stayed silent. |
| **P2 physical audio/device recovery:** PCM writes/terminal outcomes cannot prove audibility, microphone hotplug behavior or driver cleanup. | Note visible response with no sound, interrupted/repeated playback, device changes and capture failures. Keep generation/delivery/attempt IDs and a human observation of what was heard. |

Use Standard recording for the session. Detailed content requires deliberate
Verbose consent and separate private export. At the end, export sanitized JSONL
plus the TXT timeline and note exact application/build, session, PID and wall-clock
times for anomalies. Keep private files separate from shareable support bundles.
Tonight's #29 MSI **does not contain these follow-up fixes** and is not replaced.

## Validation and limits

Run from the host root using existing development dependencies:

```sh
PYTHONPATH=src TARS_SPEECH_TRACE=1 python -m pytest -q
node --test --test-isolation=none test/electron/*.test.js
node test/frontend/run-tests.mjs
python tools/verify_tars_bundle.py --source ../TARS-Plugins
mkdocs build --strict
```

Local results and exact Windows workflow status are recorded in the Draft PR.
No physical Windows, microphone/speaker, several-hour RSS/handle trace or live
Elite session was performed. A successful synthetic scenario is not gameplay
acceptance. No existing test MSI, release, branch, plugin pin or personality is
modified by this investigation.
