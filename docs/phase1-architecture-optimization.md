# Phase 1 architecture audit: unchanged plugin persistence

Baseline: `stabilize/tars-windows-rc@7a447a4c37d5b91808ad9b4fc5b4147e0336f4c9`.
The six-plugin bundle remains source-verified against TARS-Plugins; this phase
changes only Navigator and Expedition state writes. It does not change their
event handling, callouts, prompts, actions, or saved JSON format.

## Verified behavior and measurement

Navigator's live game side effect called `_save()` after every accepted event,
including exact duplicate events. Its stop callback also called `_save()`.
Expedition already returned early for exact duplicate events, but its stop
callback still rewrote the unchanged state. Both `_save()` methods serialized
state to a temporary JSON file and atomically replaced the destination on
every call. A successful save now caches the exact serialized bytes as text;
subsequent identical payloads skip the disk write and replace when the file
still contains that payload. A missing, unreadable, or externally changed file
is rewritten even if memory has not changed. A failed save does not advance the
cache, so the next call retries. Loading compares against the actual file text,
so normalization of an older file still gets persisted.

Measurement used the real plugin entrypoints, a temporary state file, one live
`Location` event, then 100 repetitions of that identical event and 100 stop
calls. `Path.replace` was counted; wall time used `time.perf_counter()` on this
cloud workspace and is illustrative, not a Windows performance claim.

| Plugin | Before replacements | After replacements | Before elapsed | After elapsed |
| --- | ---: | ---: | ---: | ---: |
| Navigator | 200 | 0 | 8.99 ms | 3.36 ms |
| Expedition | 100 | 0 | 6.62 ms | 2.49 ms |

The table records the initial Phase 1 implementation. Final integration review
added a file-content check on unchanged saves to recover deleted or externally
modified files during an active session. In five subsequent runs of the same
200-callback workload, the final implementation still made zero replacements;
median elapsed time was approximately 4.7 ms for Navigator and 3.3 ms for
Expedition. These cloud timings are illustrative. The stronger recovery check
adds a read on unchanged saves, so the documented benefit is reduced disk
replacement and safe recovery, not a guaranteed latency reduction.

Actual state changes still produce the same UTF-8 JSON, and the tests cover
restart, unchanged stop, changed state, deleted and externally modified files,
and retry after failed replacement. The optimization targets disk churn; it
still serializes and checks the file content on an unchanged save attempt.

## Ranked findings

1. **Confirmed and addressed: redundant state-file replacement.** The two
   plugin `_save()` paths above produced unnecessary replacement operations.
   This is narrow because it leaves dedup keys and event processing intact.
2. **Confirmed, deferred: separate journal traversal for Expedition import.**
   `TARSExpedition._rebuild_from_journals` opens and parses every `Journal.*.log`
   on first import or explicit rebuild, while `src/lib/EDJournal.py` also reads
   journal files for the live event pipeline. The plugin's historical rebuild
   has distinct semantics and rollback behavior; sharing the traversal needs a
   separately measured design and replay tests.
3. **Confirmed conditional extra LLM call, deferred:** with
   `use_action_cache_var` enabled, an uncached single tool action can invoke
   `Assistant.verify_action`, which calls `llmModel.generate` again to verify a
   cache candidate. This supports action-cache correctness; changing it may
   alter tool selection, latency, and model cost. Instrument call frequency on
   representative Windows sessions before proposing a change.
4. **Potential overlap, not yet proven waste:** Explorer, Navigator, Galaxy,
   Expedition, and Chatter subscribe to game side effects. They maintain
   different state and public contracts. No shared event-processing refactor
   is justified by this audit.

No prompts, speech policy, Chatter logic, provider behavior, or plugin loader
mechanism changed. Windows disk latency, real journal volume, and LLM call
frequency require separate measurement on a real installation.
