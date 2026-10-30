# Integration, reliability and maintenance audit — 2026-10-30

This audit examines the current integrated development stack, not just `main`.
It fixes existing runtime defects without adding gameplay capabilities, providers,
personality changes or new services. It is a bounded code review and automated
fault-injection audit, not proof that every race or device failure is absent.

## Verified GitHub baseline and isolation

GitHub open-PR metadata, remote branch heads and local ancestry were checked before
edits; remote heads were checked again during validation.

| Repository | Main | Corrective dependency | Combat dependency / audit base |
| --- | --- | --- | --- |
| TARS | `b3b3eb70e052566942497be9eabc943037eab306` | #25 `466e2ed370d5645e965e41a1fda1879008b80b12` | #26 `c3cb04b245a1b39ab8ed594a8416d35c3378f5e1` |
| TARS-Plugins | `794ca29cade61738e96f168f36052e76f26a2475` | #28 `54c9161412e9478a9ffe8de2d0b505fbf37f89db` | #29 `83caceaca39712d1c84e4337a09b020b087125ae` |

Host open PRs at audit start: #5, #7–12, #24–26. Canonical plugin open PRs:
#27–29. The corrective and Combat PRs remain Draft and unmerged. The Combat heads
contain their corrective bases. The new `fix/integration-reliability-audit` branch
is based on host #26; it does not alter any existing PR branch. No canonical
plugin edits are required: the seven-plugin bundle retains the exact #29 pin and
all 32 payload files still match canonical Git objects. No merge, rebase,
force-push, tag or release is authorized or performed.

## Confirmed defects and targeted fixes

P1 means potential lost input/state or retained action authority; P2 means resource,
recovery or maintenance defects. These are qualitative engineering priorities,
not incident-frequency estimates.

| Priority | Verified defect / evidence | Implemented correction |
| --- | --- | --- |
| P1 | `EDJournal.__init__` starts `_reading_loop` directly, bypassing the existing recovery wrapper. Injected failure after one live record kills ingestion. | Start the recovery worker, retain per-file consumed-line checkpoints and retry without replaying delivered records. Retry waits are cancellable. |
| P1 | A non-newline-terminated journal write is consumed as malformed; completing the write loses the event. | Keep incomplete records at their original stream offset. Startup history also leaves incomplete records for the live tail. Preserve physical line-based IDs; skip complete malformed/non-object records. |
| P1 | `ActionManager.actions` is class-scoped. A second manager retains a first manager's callbacks even when it never registered those actions. | Each manager owns its registry. Existing registration, permissions, approvals and actuators remain in use. This proves in-process isolation; it does not claim an observed cross-process exploit. |
| P1 | `STT.resultQueue` is class-scoped; a new STT instance can consume a prior instance's transcription. | Each instance owns its queue and capture state. No provider/model changes. |
| P2 | Microphone read errors bypass `source.close()` in both PTT and continuous listening. | Close streams in `finally`; reset recording state. PTT releases capture before provider transcription. |
| P2 | Muting leaves unfinished voice frames/activity in the buffer, allowing an old phrase to be transcribed after unmute. | Discard incomplete phrase buffers while muted. A deterministic voiced/muted/silent sequence verifies no transcription. |
| P2 | Repeated continuous-listen startup can create multiple workers; backoff grows without bound. | Retain a single worker per instance, cap retry delay at 30 seconds, interrupt waits on stop, and reject results after stop. |
| P2 | `TTS.quit()` is a no-op; device streams are not closed when playback fails. | Stop/abort output, close streams in `finally`, terminate PortAudio in the worker's finalizer, cap recovery backoff, and bound join to two seconds. Late text/file submissions settle as cancelled instead of accumulating after shutdown. |
| P2 | Chat teardown runs only after the normal loop exit. An initialization exception skips plugin/device cleanup. Journal, status and projection timer workers have no normal teardown path. | Run component cleanup in `finally`, including hotkeys, STT, plugins, journal, status, timer and TTS. Each cleanup failure is isolated; stop methods are repeatable. |
| P2 | An empty `EventManager.process()` still commits and rewrites projections on each idle chat poll (nominally ten polls/second). | Return before persistence when incoming **and pending** work are empty. Existing real-event/timer persistence remains covered by integration tests. |

The initial fault suite on the unchanged base produced **seven failing cases**
(partial live write, recovery, malformed live record/worker stop, STT isolation,
two microphone read-error paths, action isolation). Further lifecycle/muting/idle
regressions exercise the production worker/orchestration methods with fake devices.
No raw journal, credentials or real utterances were added to fixtures/logging.

## Architecture and integration review

| Area | Inspected boundary and evidence | Assessment |
| --- | --- | --- |
| Plugins | PluginManager synthetic import packages, ordered required plugin loading, provider allowlist, PluginHelper observer/admission hooks, canonical provenance | Keep existing architecture. Source pin verification and loading tests cover the integrated stack. DLL/import resource lifetime remains a reload concern below. |
| Events/state | Journal history/live tail, StatusParser rewrite retry, EventManager serialization/timer/conditions, projection replay, supplied sanitized combat replay | History does not request ordinary live reactions; new journal fixes preserve IDs across recovery. Partial status JSON retains previous valid state. Timer writes and real-event processing still run. |
| Speech/model calls | Assistant scheduling/empty-event guard, direct/optional execution locks, SpeechArbiter epochs/leases, semantic delivery ledger, explicit abstention, TTS outcomes | Existing corrective tests cover empty generations, direct priority, stale optional output, ordinary discussions of silence, cross-plugin evidence and failed-playback retries. No new speech policy/personality changes were justified. |
| Replay/bridge | Observatory live/batch checks, persisted cursor/recent IDs, replaced-file handling; Combat historical/freshness gates | Existing bridge tests verify no historical dispatch, reconnect cursor behavior and retained live facts. Combat replay verifies zero model commentary. Not equivalent to acceptance of an installed Observatory process. |
| Actions | ActionManager registration/Allow-Ask-Block, one-use approvals, Combat exact parser/session/freshness/confirmation checks | Fix shared registry; retain existing COVAS:NEXT-derived actuator implementation. No duplicate control system, autonomous action or new gameplay action. Unscored voice controls continue to fail closed. |
| Providers/recovery | Model response selection/rejection handling, STT failures, TTS retries/terminal evidence, installed provider integrity/rollback tests | Fake provider/device failures exercise existing contracts. Existing OpenAI, Parakeet, Pocket-TTS and configurable providers are retained. No paid API acceptance or live outage testing performed. |
| Settings | Config command copy-before-save, ConfigPersistence atomic replace/previous-good/manual backup, provider migration and profile tests | Existing corruption, interrupted-replace, backup restore, provider-tuning and permission tests pass. No user profile, defaults or No reaction settings changed. Power-loss durability on physical disks is not demonstrated. |
| Frontend/process | Electron process/error/close notification and stop paths, frontend lifecycle/settings contracts, overlay fallback and cleanup | Existing Node tests pass; prior exact-base Windows Edge/E2E evidence is available. Overlapping process restart is a remaining concurrency risk, not a reproduced audit failure. |

## Remaining uncertainties and maintenance priorities

These are **not** asserted as reproduced gameplay incidents or measured memory leaks.

1. **P1 live acceptance:** Windows key semantics, permission prompts during real game
   focus, fighter UI navigation, physical microphone/speaker reconnection, and
   interruption/audibility still require a real installation. Unit tests cannot
   prove a key reached the intended game or audio reached a listener.
2. **P2 blocked external calls / startup:** a two-second join cannot cancel arbitrary
   native/provider I/O. Workers clean up after those calls return; a permanently
   blocked provider may survive until process termination. Partial failures inside
   the `Chat` constructor precede `run()` and are not covered by its teardown.
   Test provider hangs/device drivers on Windows before stronger shutdown claims.
3. **P2 state concurrency:** `get_current_state()` exposes projection state objects,
   while timer and event threads may update projections. The processing lock
   serializes writers, but does not make every consumer's view an immutable atomic
   snapshot. No inconsistent command execution was reproduced. A future correction
   should begin with a deterministic interleaving, not a projection rewrite.
4. **P2 long sessions:** EventManager's processed history and startup journal history
   retain records; event persistence also grows. No long-duration RSS/handle/DB-size
   measurements exist. Measure before changing retention, since memory/query/replay
   consumers depend on history. Journal reconnect cursors are bounded to 32 files;
   reattachment to an evicted old file or same-name truncation/replacement is not
   guaranteed by this fix. Normal new-name journal rotation is covered.
5. **P2 native ownership/reload:** STT closes microphone streams, but its per-open
   PyAudio owner does not have explicit termination ownership. PluginManager retains
   import paths/modules and DLL directory handles for the process lifetime. The
   normal Electron lifecycle starts a fresh backend process; in-process reload
   stress and Windows native handle measurements remain needed. No measured leak
   rate or unsafe hot-reload support is claimed.
6. **P2 Electron restart ordering:** start requests signal an existing backend then
   spawn its replacement without awaiting close. Late output from the old process
   and simultaneous profile/database use warrant a dedicated deterministic child-
   process interleaving test. Existing lifecycle notification tests do not prove
   overlap is harmless. No new restart controller was introduced speculatively.
7. **P3 maintenance:** plugin-specific fallback abstention recognition duplicates the
   host detector for compatibility with older hosts; removing it now breaks that
   contract. Baseline/non-TARS plugin loading, legacy `covas.db`/UI build names and
   upstream action implementations remain compatibility surfaces, not proof of
   obsolete code. Several tests rely on `src` being importable as both `lib` and
   `src.lib`; targeted runs should set `PYTHONPATH=src`. Broad deletion/renaming would
   need a dependency/migration demonstration. No such rewrite is included.
8. **P3 diagnostics:** six existing Python dependency/fixture serialization warnings
   remain. The full suite passes; warnings are not silently represented as fixes.

## Windows packaging and installation readiness

Exact audit base `c3cb04b2` has successful GitHub Windows validation:
[Build and Test Executable, run 41048337447](https://github.com/rex688-png/TARS/actions/runs/41048337447).
Verified job/step results include backend tests/PyInstaller, frontend tests,
Microsoft Edge settings navigation, Electron tests, actual MSI metadata inspection,
clean packaged TARS profile, portable ZIP, clean-VM E2E, and disposable real MSI
install/upgrade/downgrade acceptance. Its security run `41048337625` also passed.
The release-publishing job was **skipped**.

That evidence applies to the base SHA, not automatically to this audit PR.
The new Draft PR triggers the existing Windows/security workflows; inspect their
exact head before claiming packaging success for these fixes. Packaging identity,
version mapping, release configuration and MSI publishing files are unchanged.
Local metadata/MSI mapping and canonical-bundle checks pass. A physical Windows 11
installation must still verify upgraded user profiles, antivirus/driver behavior,
microphone/speaker hotplug, suspend/resume, device selection, overlay focus and
live Elite actions. No live combat/audio acceptance or signing/release claim is made.

## Reproduction and validation

Run from the host root with the existing development dependencies. Linux UI/audio
imports need an accessible display; devices/providers are faked by tests.

```sh
PYTHONPATH=src TARS_SPEECH_TRACE=1 python -m pytest -q
PYTHONPATH=src python -m pytest -q test/lib/test_integration_reliability.py
node test/frontend/run-tests.mjs
node --test --test-isolation=none test/electron/*.test.js
node --test test/release/msi-version.test.cjs
python tools/verify_tars_bundle.py --source ../TARS-Plugins
python -m pip check
python tools/release_metadata.py
mkdocs build --strict
# In ../TARS-Plugins:
python -m unittest discover -s tests
```

Final local validation: **891 host tests passed**, including **19 new reliability
cases**, with six existing dependency/fixture serialization warnings and no skips
or errors; **142 canonical plugin tests**, **34 frontend tests**, **16 Electron
tests**, and **one MSI mapping test** passed. A separate focused run passed all
42 lifecycle/journal/TTS cases. Strict MkDocs, dependency consistency, release
metadata and exact 32-file canonical verification passed. The new Draft PR URL
and current Windows CI status are recorded in the PR description. The new
regressions use real workers with fake streams, temporary journals, and failure
injection. Chat teardown tests execute its production orchestration method with
fake components; they do not claim full physical startup acceptance. Existing
synthetic and sanitized journal integration tests remain in the full suite.
