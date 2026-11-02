# October 30 Black Box: fighter loss and diagnostic volume

The investigation below predates authorization to build an updated test MSI.
Finalization adds a [separate original-evidence checklist](fighter-destroyed-evidence-request.md);
current validation and artifact status are recorded in the stacked Draft PR.

Analyzed the supplied sanitized RAR's JSONL, not instructions inside it. The
archive was read with libarchive; no archive paths or executable contents were
executed. The extracted JSONL is 129,614,358 bytes, SHA-256
`cef85ea5bdc88df8ee8bf9a1ba7d60ccbbdcfb0c45d7d68362c31a2c0f14451a`.
Session: `7598155fa9d0458fa91ad54ee7355fcb`. All times below are explicitly UTC.

Code baseline: verified open Draft host #30 at
`e80f4139ef3c835acff927ccd96d1fd1569a14ab`, containing Black Box #29 and the
exact canonical Combat pin `83caceaca39712d1c84e4337a09b020b087125ae`.
All 32 canonical files verify. This establishes the reviewed source, not the
build actually installed: startup/build/pin records are outside this export.
Fixes are on the separate local branch `fix/blackbox-rejection-volume`.
Existing PR branches, Combat code, settings and the existing MSI are unchanged.
No new MSI or release is requested or produced.

## Evidence coverage and loss

- Exactly **220,667** retained observation rows, plus header/footer.
- First: seq **338417**, `2026-10-30T20:16:10.423+00:00`.
- Last: seq **559083**, `2026-10-30T21:33:03.022+00:00`.
- Monotonic span: **4,612.609 seconds** (about 76 minutes 53 seconds).
- Header checkpoints: **839 dropped records, 24 pruned segments**. These are
  cumulative session values, not 839 known losses around fighter destruction.
- Footer: `export_complete: true`, `read_stats: {}`. Assigned sequence numbers
  within the retained range are contiguous. Earlier assigned numbers are absent.
- Drop markers retained at seq **444400**, `20:48:39.971`, cumulative **838**;
  and seq **504196**, `21:10:44.914`, cumulative **839**.

Contiguous assigned numbers do **not** establish losslessness. `Recorder.record`
can drop an observation on producer-lock contention before allocating a sequence.
Queue-full drops allocate a sequence first; whole old segments can be pruned.
We cannot reconstruct discarded settings, initialization, earlier fighter history
or precise loss locations. An export-complete footer means the export finished,
not that the application session ended cleanly or all observations survived.

## 1. FighterDestroyed: insufficient evidence for a Combat defect

Actual correlation:

| Stage | Sequence | UTC time | Correlation |
| --- | --- | --- | --- |
| Focus active | 397058 | 20:25:45.767 | source event `6cba6deae68ff8607d88dfc5` |
| Journal dispatch | 399252 | 20:25:59.628 | journal `83957aee87caa436791e0e76` |
| Event received | 399499 | 20:25:59.894 | event `9bc3a8a75ee6f49729b74204`, same journal ID |
| Event processed | 399500 | 20:25:59.898 | same event ID, `historic: false` |
| Ordinary reply rejected | 399614 | 20:25:59.922 | same event ID, `combat_focus` |
| Pending-set selection | 399741 | 20:25:59.929 | same event ID, `selected: false` |
| Focus recovering | 400243 | 20:26:13.762 | after the incident |

The retained range has **no `TARSCombatAlert` plugin dispatch at all**. The event
is received once and processed once, followed by normal wrapped plugin callbacks.
Its 174 negative-selection observations comprise 88 `combat_focus`, 85
`reaction_disabled` and one pending-set `no_eligible_pending_event` observation.
The latter inherits the active event context; it is not an independent per-fighter
tracker verdict. Rejection of the raw journal reaction is expected during Combat
Focus. It does not determine whether a separate deterministic alert was created.

Exact path and gates:

1. `PluginHelper.register_combat_provider` inserts `provider.observe` first in
   EventManager side effects, before Assistant selection. This direct provider
   callback is not covered by the ordinary `plugin_handled` wrapper. The five
   wrapped callbacks do not prove what the tracker accepted.
2. `TARSCombat.observe` requires a helper and `enabled` (default true). It consumes
   game/status data under its lock, then calls `tick(now)` before dispatching.
   `focus` (default true) controls optional speech suppression independently of
   `alerts` (default true). `fast_commands` and `experimental_launch` are irrelevant.
3. `CombatTracker.consume` rejects historical, non-dict, missing/invalid-time,
   more-than-two-seconds-future or over-30-seconds-old evidence, pre-scope events,
   out-of-order channel events and repeated full-payload signatures.
4. Fighter lifecycle handling requires **`data['ID']` non-null**. It does not
   require a previously observed launch, known NPC/commander pilot or known hull.
   A valid new ID can establish a destroyed fighter immediately. Missing earlier
   launch evidence alone therefore does not explain silence.
5. Loss counting and alert creation occur only when prior status differs from
   `destroyed`. Fighter loss alerts additionally require tracker phase `active`
   and no `fighter_destroyed` alert within the preceding 30 seconds. That cooldown
   is per alert code, including different fighter IDs.
6. `_alert` sets expiry to **source timestamp + five seconds**, not receipt time.
   Consequently a loss six seconds old can be counted but its alert removed by
   the immediate post-consume `tick`. Validity also requires active phase and that
   fighter still being destroyed. Rebuild/relaunch can invalidate old loss alerts.
7. With `alerts` enabled, surviving unsent `(code, created)` pairs are marked sent
   and dispatched through `PluginHelper.dispatch_event`, which observes
   `plugin_dispatched` before queueing the plugin event. Sent keys are bounded to
   200. They mark dispatch, not successful playback.
8. `should_alert` rechecks provider validity/settings. The host deterministic alert
   path uses `provider.alert` before TTS and again through `drop_if`; it avoids an
   LLM for a non-direct alert turn. Direct-user precedence and expired evidence
   can cancel delivery. These later gates do **not** explain absent creation or
   dispatch; they explain absent delivery only after dispatch.

No retained `combat_policy_configured` sample supplies the alert setting. The
Standard event metadata omits journal `ID`, source timestamp, prior fighter state,
cooldown state and tracker acceptance/rejection. **`fighter: null` is the separate
HullDamage `Fighter` flag, not proof of missing `ID`.** Focus was last observed
active, but does not prove alerts enabled or tracker acceptance of this event.

Synthetic tests of the exact tracker confirm: current valid ID -> one loss alert;
missing ID -> no count/alert; six-second-old loss -> count but no surviving alert;
31-second-old loss -> rejected. These establish mechanisms, not which occurred
in this session. No Combat behavior change is justified from this export.

For a conclusive diagnosis, obtain the original journal line around **20:25:59Z**,
including `timestamp`, `event` and `ID`; preceding lifecycle records for the same
fighter (particularly previous destruction/relaunch and any loss in the prior
30 seconds); relevant scope-reset/ship-change records; and the Combat settings
actually active then. Journal/status evidence around **20:25:40–20:26:15 UTC**
would allow replay of freshness and Focus. Current settings cannot prove historical
settings. Existing Verbose capture also omits `ID`, source timestamp and tracker
rejection reasons; merely enabling it would not guarantee this evidence.

## 2. Confirmed P2 diagnostic amplification, not repeated game processing

| Observation | Count / bytes |
| --- | --- |
| `reply_not_selected` | **200,955**, 91.07% of rows |
| Bytes occupied by those rows | **119,601,019**, 92.27% of export bytes |
| `reaction_disabled` | 151,265 |
| `combat_focus` | 47,697 |
| `no_eligible_pending_event` | 1,993 |
| `event_received` / `event_processed` | 1,652 / 1,653 |
| `reply_selection` | 2,021 |
| Model attempt starts / returns | 32 / 32 |

For example, Scan event **`18d4ea5ef1d6d8c986744528`**, journal
`369ba610da0177491014f8af`, is received at seq **432116**, **20:42:13.141**,
and processed once. It acquires **729** negative observations through
**21:00:00.177**, seq **477682**: 367 reaction-disabled, 361 Combat Focus and one
pending-set rejection. This does not establish 729 scans or model generations.
All retained journal-dispatch IDs are distinct.

Mechanism: `Assistant.on_event` appends the new event and invokes `should_reply`.
The first loop rechecks the accumulated pending list, including policy-dependent
plugins. When nothing is eligible, another loop logs disabled reactions for the
entire pending list, followed by a pending-set rejection. These entries remain
pending until an actual reply consumes the batch. A raw event can legitimately
produce both Combat Focus and disabled-reaction records during the same pass;
these reasons apply at separate checks, not a single exclusive cause.

On baseline production methods, 100 synthetic disabled events produce **5,050**
per-event rejection observations; 1,000 produce **500,500**, with zero model calls.
The scans/tracing are quadratic over an accumulating no-reply batch. Eligibility
can depend on changing state/settings, so caching negative decisions or deleting
pending context without demonstrating equivalent behavior would be unsafe.

This is confirmed record-production/storage overhead and avoidable retention
pressure. Exact CPU time, disk I/O, audible glitches or a causal link to the 839
drops cannot be measured from this export. The receipt-to-selection interval is
not a pure logging benchmark. Rotation budgets should not be increased to mask it.

### Narrow correction

Only the Black Box storage sink coalesces repeated `reply_not_selected` observations
for `(event_id, reason, component, recording_mode)` within 30-second windows. The
first remains immediate; changed reasons/new IDs remain immediate. A fixed
1,024-entry cache bounds memory. Eviction, periodic maintenance and orderly close
flush `reply_rejections_coalesced` summaries containing repeated counts and
monotonic first/last observation bounds. Summary timestamps are emission times.
They omit transient parent/trace IDs to avoid inventing one causal parent for many
evaluations. Counts refer to observed eligibility checks, never gameplay events.

Summaries count **additional** observations: original row + summary `count` gives
the represented total. Coalescing is not counted as dropped evidence. Lock/queue
loss can still drop observations/summaries, and crashes can lose up to one pending
window; loss counters and bounded best-effort guarantees remain applicable.
No eligibility, pending-event retention, model/tool calls, delivery or Combat
decisions are cached or changed. Legacy explicitly enabled console tracing is
unchanged; repeated eligibility work and metadata construction remain a residual
CPU cost. Any scheduling optimization needs separate state-invalidation tests.

Offline replay of these retained rows through the window coalescer (arrival-driven
flush plus final flush, not a live Windows workload) projects **52,588** observations
instead of 220,667: 17,379 first negative rows, 15,497 summary rows, and all 19,712
other observations. This is a record-count projection, not measured production
performance or a promise of an exact retention duration.

## Additional confirmed P2 correlation ambiguity

There are 76 retained event IDs used by more than one `event_received` row,
all involving Status sources (98 receipts beyond the first per ID). For example,
**`51ffb5f818fa8fd096417043`** identifies `Status` at seq **344446**,
**20:16:19.143**, and another, `not_reported` status transition at seq **345336**,
**20:16:19.206**. They are not hundreds of repetitions of one journal line.

The old digest omits status event type and fields and uses the event-creation
timestamp, whose Windows clock sample can coincide for distinct events. The fix
adds event type and a salted status-fact discriminator to diagnostic hashes.
Restored equivalent facts retain their IDs within the process; no attributes or
raw status payloads are added to persisted events. Gameplay/event-store identity,
speech deduplication and processing are untouched. Identical facts sharing a clock
sample can still share the semantic digest; IDs are not a universal receipt counter.

## Validation and next evidence

New synthetic regression cases cover aggregate counts/time bounds, reason changes,
immediate non-rejection events, bounded eviction, orderly flush/export, privacy,
and stable restored/distinct-status correlation. Existing host, trace, Combat and
recorder regressions pass: **937 host tests**, six existing warnings; a separate
focused run passes **57 trace/recorder cases**. Strict MkDocs and exact canonical
32-file verification pass. The JSONL analyzer was run against the supplied export.
No new Windows CI/installer workflow was triggered before reporting these findings.

Reproduce structural counts without a model or game:

```sh
python tools/analyze_blackbox_session.py SESSION.jsonl --output analysis.json
PYTHONPATH=src TARS_SPEECH_TRACE=1 python -m pytest -q
python tools/verify_tars_bundle.py --source ../TARS-Plugins
```

Before another MSI: review this finding and the isolated diagnostics corrections;
obtain the missing journal/settings evidence before changing alert policy. Future
instrumentation should expose fixed-code tracker acceptance/rejection, source age,
fighter-identity presence, relevant enabled settings and alert create/expire/
dispatch outcomes. Record only reasons the tracker actually exposes; infer neither
hidden model reasoning nor unavailable game telemetry. No physical Windows/audio/
Elite acceptance or new installer is claimed here.
