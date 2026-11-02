# Evidence needed: fighter loss at 2026-10-30 20:25:59 UTC

This request concerns session `7598155fa9d0458fa91ad54ee7355fcb` only. The
sanitized export confirms a live `FighterDestroyed` receipt and processing, but
does not establish why no critical-alert dispatch is retained. Combat behavior
must not be changed based on that absence alone.

## Original journal records

Elite journals normally reside beneath
`%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous\`.
Find the file containing the **source** `FighterDestroyed` timestamp around
`2026-10-30T20:25:59Z`; the file's opening date can be earlier. The exact source
timestamp is not present in Standard Black Box metadata and must be verified.
Search adjacent journal files too if the game restarted or the journal rotated.

Preserve original record order and timestamp precision. A private local analysis
can use the full file; a shared excerpt should retain only relevant fields:

| Records | Required fields / extent | Why |
| --- | --- | --- |
| The loss record | `timestamp`, `event`, `ID`, including whether `ID` is absent/null, plus any other original fighter identity fields | The tracker uses uppercase `ID`; the Black Box journal hash and lowercase augmented `id` are unrelated. `Fighter: null` does not establish missing `ID`. |
| Fighter lifecycle | All preceding `LaunchFighter`, `DockFighter`, `FighterDestroyed`, `FighterRebuilt` records from the most recent scope reset through 20:26:15 UTC; retain `timestamp`, `event`, `ID`, `Loadout`, `PlayerControlled` when present | Reconstruct each fighter's state, pilot and ordering. Do not manufacture an `ID` for a record that only has `Loadout`. A preceding launch is useful context but is not a prerequisite for accepting a destruction with a new valid ID. |
| Recent losses across all fighters | Every `FighterDestroyed` in at least 20:25:20–20:25:59 UTC, retaining timestamps and IDs | The 30-second loss-alert cooldown is shared by alert code, not per fighter. Journal loss alone does not prove an earlier alert was actually created. |
| Immediate aftermath | Rebuild/relaunch/docking and other relevant records through at least 20:26:15 UTC | Rebuild/relaunch or scope changes can invalidate an outstanding loss alert. |
| Scope and ship identity | Most recent `LoadGame`, `Shutdown`, `Died`, `FSDJump`, `SupercruiseEntry`, `Docked`, and subsequent `Loadout` changes; preserve event timestamps and `ShipID`, `Ship`, `ShipIdent` as needed for consistent equality comparison | Scope resets, ship changes and out-of-order timestamps can reject or clear old evidence. Replace identifying values consistently if sharing them. |
| Focus evidence | `Music` with `MusicTrack`, `UnderAttack`, relevant target/bounty events around 20:25:40–20:26:15 UTC | Reconstruct threat/hysteresis. Status-derived danger transitions are not necessarily journal records. |
| Game/session metadata | Journal file order, line order, and `Fileheader` game/build version if present | Check journal schema and align source order. No commander name, FID or absolute personal path is needed. |

Use the most recent relevant scope-reset boundary rather than arbitrarily taking
only five preceding lines. If lifecycle spans a previous file, retain the cross-
file ordering. Keep missing fields missing. Sanitized replacements must preserve
ID equality and differences across launch/loss/rebuild records.

## Runtime settings and evidence

Provide the settings that were effective **at that time**, or identify that only
current settings are available. Relevant configuration is the fragment beneath
`plugin_settings["203c9a85-7adc-4c15-8f70-1a7f5ab14d21"]` in TARS's profile
`config.json`, specifically `enabled`, `focus`, and `alerts`. Their factory defaults
are all true; a missing key invokes that default. Do not assume a current file
proves historical settings. The profile configuration may contain API keys: do
not send or commit the whole file. A three-key excerpt or historical UI evidence
is sufficient. `fast_commands`, `experimental_launch` and action permissions do
not enable or disable this deterministic loss alert and need not be disclosed.

Also useful, where actually retained:

- Exact installed host commit/build and canonical plugin revision; plugin load,
  start/stop, settings changes, backend restart and hook errors around the event.
- Original source timestamp **and host receipt/processing times**, plus any
  journal recovery/replay classification. A five-second-old event can be accepted
  for state tracking while its alert expires immediately; events over 30 seconds
  old are rejected outright. Over-two-second future timestamps are rejected.
- Time-stamped historical Status snapshots, if available, showing `InDanger`,
  `InFighter` and `InMainShip`. Current `Status.json` cannot reconstruct the past.
- Alert creation, expiry, dispatch or delivery evidence and any direct-user/TTS
  activity in the five seconds following the **source** event. Later speech
  admission or playback cancellation explains absent delivery, not absent dispatch.

Ordinary No reaction settings for the raw journal event are separate from the
plugin's critical-alert policy. Preserve them; do not change them to recreate an
alert. Existing Verbose Black Box capture also omits the needed uppercase `ID`,
source timestamp and tracker rejection reasons, so requesting Verbose alone is
not a reliable substitute for the original journal/settings evidence.

## Correlation and conclusions currently supported

- Journal dispatch: seq **399252**, **20:25:59.628 UTC**, journal hash
  `83957aee87caa436791e0e76`.
- Receipt/processing: seq **399499/399500**, **20:25:59.894/.898 UTC**, event ID
  `9bc3a8a75ee6f49729b74204`, `historic: false`.
- Last preceding Focus transition: active at **20:25:45.767 UTC**; next recovering
  transition **20:26:13.762 UTC**.
- No `TARSCombatAlert` dispatch appears in the retained export. It reports **839
  cumulative drops and 24 pruned segments**; these do not locate a loss at this
  incident or recover earlier settings/lifecycle.

Original Elite journal files were searched for in the available workspace,
attachment directories and the previously referenced attachment location during
finalization. **No original journal is available locally.** The supplied sanitized
Black Box and synthetic/sanitized test fixtures are not substitutes for that
original evidence. No original-journal investigation or confirmed Combat root
cause is claimed, and no private journal/configuration data is committed.

See the [session analysis](blackbox-2026-10-30-analysis.md) for exact tracker gates,
confirmed diagnostic defects and remaining uncertainties.
