TARS Expedition 1.0.4

Purpose
-------
A deliberately small expedition historian for COVAS:NEXT.

It:
- imports existing Elite Dangerous Journal.*.log files on first run
- continues tracking live journal events
- persists state in COVAS' per-plugin data folder
- tracks jumps, systems, scans, DSS maps, notable worlds, biology, actual sales,
  distance travelled, furthest distance from Sol, and docking context
- keeps a compact completed-expedition archive
- exposes focused status/history/start-finish control actions plus a dedicated
  no-argument journal rebuild action

Boundary heuristic
------------------
A data sale marks the expedition as ready to close. The trip is archived when the
next FSD jump occurs, so Universal Cartographics and Vista Genomics sales at the
same stop remain part of one expedition.

You can explicitly ask TARS to start a new expedition, finish the current one,
or rebuild expedition history from journals. Explicit rebuild requests now use
`tars_expedition_rebuild`; `tars_expedition_control` remains for start/finish
and accepts the old rebuild operation only for compatibility.

Important
---------
- Actual sales are journal-recorded payouts. The plugin does not invent estimates.
- Raw Elite journals remain the source of truth.
- Missing/deleted journals cannot be reconstructed.
- TARS Explorer still owns current-system exploration interpretation.
- TARS Galaxy still owns external station/system/service lookups.
- This plugin intentionally does not do route planning, engineering, ship health,
  material inventory, or general Elite knowledge.

Install
-------
Extract the TARSExpedition folder into:

%appdata%\com.covas-next.ui\plugins

Correct:
plugins\TARSExpedition\manifest.json
plugins\TARSExpedition\TARSExpedition.py

Restart/reload the COVAS chat after installation.


1.0.1
-----
- fixes expedition start-system tracking so the known departure/current system is retained
- incomplete file-level journal imports are no longer permanently marked complete and will retry on next startup


1.0.2
-----
- bodies_scanned and bodies_mapped now count unique physical bodies rather than raw journal event occurrences
- duplicate Scan/SAAScanComplete events no longer inflate terraformable, first-discovery, or first-mapped counters
- body identity is scoped by system so identical BodyID values in different systems remain distinct


1.0.3
-----
- fixes Universal Cartographics accounting by handling both SellExplorationData and
  MultiSellExplorationData journal events; the latter is used for page-by-page sales
- preserves distinct Cartographics pages written in the same second by fingerprinting
  the complete live journal event instead of only timestamp/event/location fields
- records separate Cartographics and Vista sale totals and event counts, while keeping
  TotalEarnings authoritative and using documented BaseValue + Bonus / BioData fallbacks
- makes rebuild_from_journals transaction-safe: live state is protected during replay,
  unexpected top-level failures restore the previous state, and control returns structured
  diagnostics instead of exposing a raw action exception
- full status now includes derived counts, complete highlights, sale breakdown, pending
  sale-boundary state, archive count, and actual recorded totals in one Expedition result
- strengthens action routing so current-expedition totals/highlights/payout questions use
  Expedition first and do not unnecessarily invoke Explorer or Navigator
- keeps Universal Cartographics + Vista Genomics sales at one stop in the same expedition;
  the first subsequent FSD jump archives that sold trip and starts the next leg


1.0.4
-----
- adds tars_expedition_rebuild as a dedicated no-argument action for explicit journal
  reconstruction, avoiding control-operation schema ambiguity in the model/tool layer
- keeps rebuild responses compact; full expedition detail remains available through
  tars_expedition_status(detail="full")
- JOURNAL_FILES_NOT_FOUND now returns the local paths that were checked and instructs
  TARS to report the concrete file/path failure rather than saying "backend failed"
- successful rebuild diagnostics include the journal directory and processed-file/event counts
- legacy tars_expedition_control rebuild requests delegate to the new rebuild path
