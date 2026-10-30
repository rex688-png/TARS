# TARS Combat V1 implementation and acceptance

This is a functional prototype with synthetic replay validation, not live combat
acceptance. Dedicated `feature/combat-v1` branches depend on unmerged speech
corrective drafts [TARS #25](https://github.com/rex688-png/TARS/pull/25) and
[TARS-Plugins #28](https://github.com/rex688-png/TARS-Plugins/pull/28).

Before editing, GitHub heads were verified against clean local checkouts:

- Host: `466e2ed370d5645e965e41a1fda1879008b80b12`.
- Canonical plugins: `54c9161412e9478a9ffe8de2d0b505fbf37f89db`.

The host corrective build/test workflow and current-tree security workflow were
confirmed successful on that exact host revision. Neither corrective branch/PR
was changed. The Combat host pins canonical source
`6eb5010b3096e969f06ba8c5e63fcc0cb0080f86`: seven behavior plugins, 32 verified
payload files. The previous six plugin payloads and prompt are unchanged.

## Audit and reuse

| Existing capability | Verified boundary and Combat V1 use |
| --- | --- |
| InCombat | Music-only indicator with immediate transitions; not a fight tracker. Retained as legacy context; Combat Focus uses the canonical tracker's hysteresis/multiple evidence. Default music entry/exit reactions cannot narrate combat under Combat Focus. |
| Target | Reset per partial/full scan or unlock. Reused for bounded subsystem cycling and confirmation; event ID is an update ID, not an enemy identity. Canonical tracker adds source time, scan completeness and stale labels. |
| CurrentStatus | InMainShip/InFighter, InDanger, ShieldsUp, OverHeating, GUI focus and normalized pips are available. Status parsing previously dropped source time; it now preserves it. No own shield percentage, capacitor charge or ship heat percentage is available. |
| ShipInfo | Ship model, bay readiness, launched fighter IDs and player/NPC pilot state reused. Fighter damage is assigned only when the journal identifies a unique launched fighter. |
| Loadout/ModuleInfo | Readiness snapshots expose modules, hull and available ammo/health with source timestamps. They do not establish current weapon DPS, accuracy or a heat-sink deployment. Existing Loadout already excludes explicit Fighter hull damage. |
| SpeechArbiter/Assistant | Shared focus gate acts before selection/generation in every rollout mode. Direct questions/safety bypass; history/projections continue updating. In-flight output revalidates, queued optional audio has drop conditions, and old Chatter leases cannot revive after recovery. |
| ActionManager/ActionPermissions | Existing controls remain the actuator implementation. Master switches, explicit allow keys and central permission checks remain. Ask/Block are not bypassed. Read-only Combat query uses a separate read action type, available when game controls are off. |
| STT | Existing providers/capture preserved. Capture completion and STT-result timing are additive. Current provider contract returns text without acoustic confidence; voice control fails closed. |
| Power distribution | Old action counted key increments as absolute pips. The verified bounded sequence supports full reset/balance or max four pips to one system: reset 2/2/2, then four half-pip increases. Other absolute/partial allocations now return an error without input. Actual binding semantics still require game validation. |
| Subsystem action | Existing action cycled without bounded waits and could continue across a target change. It now checks target identity/scan, has a two-second budget, bounded key count and update timeout. A returned request is not success. |
| Fighter orders/UI | Direct NPC-order bindings are reused. Attack/defend behavior has no confirmation telemetry; return is also reported unconfirmed. Launch UI is separately experimental/off until its panel navigation is validated on Windows. No enemy is selected automatically. |

## Behavior and configuration

Under Settings → Plugins → TARS Combat, awareness, Combat Focus and critical
alerts default on. Fast control commands and experimental launch UI default off.
The module can be disabled independently. No saved profile, journal No reaction
setting, model/provider default, release/MSI infrastructure or subscription is
changed. No weapons firing or autonomous flight is added.

The state machine consumes live music, UnderAttack, danger/status, target scans,
shield/hull changes, bounty awards and fighter launch/dock/loss/rebuild events.
It rejects stale/future/historical events, respects event and ship boundaries,
and keeps separate mothership/fighter/target records. Repeated music/attack/scan
events do not create new fights. Focus waits for quiet evidence plus hysteresis,
then recovers for 15 seconds. A clock worker also handles quiet periods with no
new journal events. Source facts continue updating during silence.

Critical speech is deterministic and short: serious recorded mothership hull
loss, shield loss with fresh meaningful damage/danger, relevant fighter loss or
replacement readiness, and overheating combined with critical recorded hull.
Alerts expire after five seconds, deduplicate per kind for 30 seconds and cancel
when stale, repaired, recovered or superseded. They do not invoke an LLM and
revalidate pending user priority. Ordinary cockpit warnings alone are not echoed.

Exact command examples:

- Fighter, attack my target. / Fighter, defend me. / Fighter, return.
- Launch the fighter. (separate experimental launch setting required)
- Target power plant. / Target drives.
- Four pips to systems. / Balance power. / Deploy heat sink.

Controls require fast-command opt-in, the master game-action/tool switches, the
specific existing action enabled and permission set to Allow, fresh piloted-ship
telemetry and a suitable ship/UI state. Ask/Block deny the fast path rather than
queuing a delayed control against a possibly changed target. Target controls
require a fresh complete scan; fighter commands require appropriate NPC/bay
state. The exact matched command does not construct a prompt or call the main
model. Commands are bound to the current input session and handled at most once
per event. Old-session history cannot replay controls. Unmatched dialogue can
be answered, but the conversational model cannot bypass the parser for protected
combat controls.

The current STT interface supplies no confidence score, so use typed commands
for the opt-in prototype. Unscored or low-confidence voice orders are refused.
This is a documented provider limitation, not a claim that Parakeet or OpenAI
has measured poor accuracy or excessive latency. Acoustic confidence is not
inferred from matching an exact string.

The read-only `tarsCombatQuery` action supports situation, target, condition,
wanted, bounty, subsystem, fighter, readiness, progress, report and latency.
Combat questions are instructed to query current evidence; legacy snapshots are
not proof of freshness. Missing, incomplete or stale values remain unknown.
Reports are brief and requested only: known bounty credits and unknown amounts,
shield/hull milestones, fighter launches/losses/rebuilds, observed targets and
focus intervals are distinct. Bounty credit may be shared. Neither an award nor
a music interval proves an individual solo kill. No exact DPS/accuracy is inferred.
Records are bounded and session-local, with no new private history file.

## Measurements

`python tools/benchmark_combat_parser.py` measured 2,400 local CPU parses of
synthetic text after 100 warm-up rounds:

| Boundary | Samples | Median | p95 |
| --- | ---: | ---: | ---: |
| Intent recognition, local parser only | 2,400 | 0.002389 ms | 0.004415 ms |
| Voice capture completion → STT result | 0 live | unavailable | unavailable |
| Real action dispatch | 0 live | unavailable | unavailable |
| Game-state confirmation | 0 live | unavailable | unavailable |
| End-to-end voice command | 0 live | unavailable | unavailable |

These parser measurements are CPU microbenchmarks, not real-world combat or
voice performance. Unit-test/fake-key timings are not published as live results.
`STTResult` and the runtime command router collect bounded duration samples with
median/p95 through the latency query when actual inputs exist. The records contain
counts/durations, no utterances. Confirmation samples require an observed requested
state; timeout/unobservable outcomes remain unconfirmed. The current provider
contract blocks voice controls, so live voice-to-control latency is unavailable.

## Replay validation and remaining acceptance

No original October 29–30 journal was present in the attached workspace. Tests use
explicitly documented synthetic equivalents, including prolonged Python Mk II,
rapid Anaconda award, NPC fighter loss/rebuild/relaunch, consecutive awards,
scan/UnderAttack bursts, bounced music and optional exploration/Observatory events.

Phase checks passed before integration:

- A: 126 canonical cases; 814 existing host cases.
- B: 126 canonical cases; 262 focused host/integration cases.
- C: 129 canonical cases; 227 host/command/STT/speech cases.
- D: 133 canonical cases; 248 host/query/STT/speech cases, followed by targeted
  parity and recovery regressions. Current final totals belong to the PR head.

Required live Windows 11/Elite validation: actual key bindings and half-pip
increments; NPC order/launch panel navigation; target cycling/cancellation during
rapid kills; permission/UI behavior; actual STT/provider confidence support,
latency, microphone/speaker timing and alert usefulness. Original sanitized
journal captures are still needed for incident fidelity. No real combat, physical
audio, voice speed or installed-game acceptance is claimed.

## Dependency and rebase handoff

These are stacked Draft PRs, not changes to the existing corrective PRs. After
all underlying corrective PRs and their bases have been integrated, fetch and
verify ancestry before moving the Combat-only commits:

- Canonical Combat base is `54c9161412e9478a9ffe8de2d0b505fbf37f89db`.
- Host Combat base is `466e2ed370d5645e965e41a1fda1879008b80b12`.
- A future `git rebase --onto origin/main <corrective-base> feature/combat-v1`
  should include only Combat commits. Resolve against verified current main.
- If rebasing changes the canonical Combat SHA, update the host pin, copy exact
  canonical payload bytes, regenerate provenance and rerun exact-source bundle
  verification plus regression suites before changing PR bases.

Do not silently rewrite a canonical SHA already pinned by a host. No merge,
tag, release or MSI publishing was performed in this sprint.
