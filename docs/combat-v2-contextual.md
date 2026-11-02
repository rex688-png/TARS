# Combat V2 contextual assistance prototype

Baseline: verified host Draft #32 `ee28c5bcd8c69265efc7e02e1b9a2f2973b4284b`
and its exact canonical pin `7450db03a7b3bed7920994f3632634dde111566d`.
That baseline's full Windows/security workflow passed. New host/plugin work uses
separate `feature/combat-v2-contextual` branches. The canonical companion is
[plugin Draft #31](https://github.com/rex688-png/TARS-Plugins/pull/31), pinned at
`d828c02336484f520b2cae8d7548e65904ea5757` (33 exact payload files).

## What the game evidence supports

| Evidence | Reliable use / limitation |
| --- | --- |
| `ShipTargeted` scan stage, lock, ship/pilot labels, sampled shield/hull percentages | Full scans can support observed changes. The supplied sanitized fixture has 904 target updates, 360 complete scans, and 462 shield/hull readings. These are samples, not continuous telemetry or a unique enemy entity ID. |
| `ShieldState`, Status `InMainShip` / `ShieldsUp`, explicit `HullDamage.Fighter=false` and fractional `Health` | Correlate mothership shield outage and repeated recorded hull decreases. No exact commander shield percentage exists. Fresh Status and explicit mothership evidence are required. |
| Fighter launch/loss/rebuild events and identity | Keep V1 awareness, critical alerts and queries. No second readiness/loss announcer; unknown IDs remain unknown. NPC fighter damage must not become mothership advice. |
| Bounty and encounter records | Keep requested progress/after-action queries. Bounty does not prove that the currently selected enemy died or a solo kill. No new kill/credit commentary. |
| Combat Focus, speech leases, direct/tool requests and critical alerts | Reuse the host arbiter, cancellation and TTS. No new scheduler, voice worker or conversational model route. |

No positions, relative velocities, weapon DPS, accuracy, capacitor levels, enemy
intent or manoeuvre recommendations can be derived reliably from this evidence.
Enemy hull percentage alone does not establish damage efficiency; no such
comparison is attempted. Ordinary target/shield/kill updates already visible on
the HUD are not sufficient opportunities. The prototype adds only sampled history
that requires remembering an extended sequence.

## Working capability, default OFF

The separate Combat setting **Optional contextual tactical observations
(experimental)** (`commentary`) defaults false. Existing critical alerts, Focus,
controls, permissions, provider configuration and prompts retain their settings.

1. **Repeated target shield recovery:** complete scan, nonempty stable ship/pilot
   identity, valid shield/hull values, sampled zero-to-at-least-20% shield changes
   at least twice, at least 45 seconds observing that identity, positive current
   target hull and fresh current shields. A partial/lost/switched target or a gap
   over ten seconds resets history. Current evidence must remain within five
   seconds; future or over-three-second-old input cannot create an opportunity.
   Wording: “We've seen that target's shields recover at least twice.”
2. **Sustained unshielded mothership damage:** at least 30 seconds of fresh
   shields-down/in-main-ship Status samples, no Status gap over five seconds,
   at least two observed decreasing mothership hull samples, and a recent hull
   decrease. Recorded hull must remain above the existing critical threshold.
   Wording: “We're still taking hull damage after half a minute unshielded.”

These report history; neither selects a target nor recommends an unsupported
action. Source time, not event-arrival count, drives the thresholds. Explicit
repair, vehicle/scope changes and contradictory fresh evidence invalidate the
relevant context. All V1 tracker/control policy code remains unchanged.

## Noise, priority and delivery

- At most **one opportunity per Combat Focus interval** and a **120-second global
  cooldown**, including suppressed attempts. Focus intervals are not individual
  fights. The budget deliberately stays conservative pending acceptance.
- No new observation while a critical alert exists or within 15 seconds of its
  creation. Bounty/ship/vehicle changes introduce a ten-second quiet period and
  invalidate prepared remarks. No automatic retries or backlog after combat.
- A four-second strict ticket reuses the existing optional-speech lease map and
  cancellation epochs. The opt-in Combat ticket permits its narrow contextual
  source during active Focus; it does not admit Chatter/exploration or weaken
  their existing Focus suppression. The ticket remains strict even if the legacy
  speech-director mode is off/observe.
- Direct/tool requests, critical alerts and existing admitted speech work win.
  The optional event cannot consume an enabled native reply. Critical/direct
  events and loss of valid context can abort the optional line. Queued stale
  remarks are discarded before speech; normal output completion does not prove
  audibility.
- Text goes directly through the existing Assistant/TTS/postprocessing and
  conversation-persistence path after revalidation. **Zero LLM calls** are needed
  for either observation. Direct conversations retain their original model path.
- The feature's state is session-local and bounded: one pending opportunity and
  one current target/history, not an accumulating event buffer. Off skips the
  detector entirely. No new service, dependency, model subscription or action
  permission is required.

## Reproducible replay comparison

Run in the canonical plugin repository:

```sh
python tools/replay_tactical_observations.py
python tools/replay_tactical_observations.py --journal tests/fixtures/combat/journal_combat.jsonl
python -m unittest discover -s tests
```

The tool prints exact source timestamps, candidate text, critical-alert counts
and state equality. A potential opportunity is **not** an assertion that it was
delivered: busy/priority/context checks can reduce the count to zero. Synthetic
times below are relative to `2000-01-01T00:00:00Z`, not the original October session.

| Replay | V1 critical alerts | Additional opportunity, with otherwise idle speech |
| --- | --- | --- |
| Extended target with two sampled recoveries | 0 | One at +45 seconds, target-history wording above |
| Sustained unshielded mothership damage | 0 | One at +30 seconds, own-ship wording above |
| Five-second kill | 0 | 0 |
| Target switches before the history threshold | 0 | 0 |
| Fighter loss at +44 seconds before a potential remark | 1 | 0 |
| Supplied sanitized journal | 1 | 0; V1 state and alerts identical |

The actual sanitized journal does not provide the live Status snapshots needed
for the own-ship cue; sparse/short target histories do not satisfy the recovery
cue. That result demonstrates restraint, **not live usefulness or a false claim
of historical callouts**. Host regressions exercise admitted delivery in each
rollout mode, repeated scans, direct/native priority, active critical/target-change
interruption, stale/disabled/scope cancellation and default-off silence. Existing
V1 controls, diagnostics, Chatter, Explorer and Observatory regressions remain in
the full suite. Final exact-head results are recorded in the Draft PRs.

## Uncertainties and live acceptance

Ship/pilot continuity is not a unique journal target ID. Missing samples, identical
labels or an unobserved switch can limit confidence. Resetting on partial scans,
gaps and observed switches reduces that risk but cannot establish perfect identity.
Real target-update cadence may make the detector too quiet. Do not relax the
guards or enable it by default without evidence.

Physical Windows/Elite testing must establish whether either phrase adds value
beyond the HUD, whether it is timely and natural, whether Status/target sampling
sustains the required history, and whether direct/critical interruption works with
real devices/providers. Record opportunity versus actual delivery counts, repeats,
stale-context mistakes and user feedback using existing Black Box. No real-world
latency, acoustic delivery, conversational-quality score or live acceptance is
claimed. Keep the feature OFF until the commander explicitly opts into acceptance.
