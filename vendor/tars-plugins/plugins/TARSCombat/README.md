# TARS Combat V1

A quiet session-local combat copilot for the compatible Combat V1 host. It does
not narrate targets, kills or combat-music transitions. Awareness, Combat Focus
and critical alerts default on; fast controls and experimental fighter launch UI
default off. No action is issued by the tracker, timer, alerts or queries.

The tracker uses timestamped live journal/Status evidence, hysteresis and a
recovery period. It separates the mothership, player-controlled fighter, NPC
fighter and enemy target. Fighter hull damage without a unique launched fighter
remains unidentified. Full/partial target scans replace each other instead of
carrying bounty or condition across targets. Stale and historical evidence cannot
start live encounters or alarms. Source timestamps are required.

Focus suppresses optional speech without stopping source ingestion. Direct user
questions and safety warnings remain available. Old Chatter preparations cannot
revive after focus; the host drops stale queued exploration remarks. Critical
alerts use fixed wording, a five-second expiry, condition revalidation and a
30-second per-kind cooldown. Ordinary shield/heat cockpit warnings are not echoed
without additional danger/recorded hull damage. No own shield percentage exists.

The `tarsCombatQuery` read-only action provides situation, target, condition,
wanted status, bounty, subsystem, fighter, readiness, progress, report and latency
topics. Missing/partial/stale facts remain unknown. Reports are requested only,
never automatic. Bounty awards may be shared: neither awards nor combat-music
intervals prove an individual solo kill or exact fight count. Target observation
spans and focus intervals are separately labelled. Credits sum only known awards;
unknown reward amounts have a separate count. Records are bounded and lost when
the chat session ends; there is no new persistence of private combat history.

Fast controls use `Commands.py`'s exact allowlist and the host's existing
ActionManager. Enable fast controls and each relevant action's explicit Allow
permission; Ask/Block/master switches still deny the fast path. Mothership
fighter commands need fresh NPC fighter/bay state. Subsystem commands need a fresh
full scan. The model cannot bypass the parser for these controls. Unmatched input
can be discussed, but cannot invoke the protected controls. Disabled combat
awareness restores the ordinary host action route.

Current STT providers expose text without acoustic confidence. Voice control
therefore fails closed; use typed commands for this prototype. No new provider,
subscription, model, automatic weapons fire, enemy selection or autonomous flight
is added. Launch UI is experimental and separately off until Windows validation.
A sent key is not a confirmed action: pips/subsystem/NPC launch can be checked
against observed state; attack/defend/return and heat-sink results remain
unconfirmed where telemetry cannot prove the requested behavior.

The original October 29–30 journal was unavailable. Canonical replay tests use
documented synthetic equivalents; see `tests/fixtures/combat/README.md`. Real
Windows 11/Elite gameplay, key binding and audio acceptance remain required.
