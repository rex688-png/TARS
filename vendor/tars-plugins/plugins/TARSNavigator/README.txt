TARS Navigator 1.1.4

Purpose
-------
A deliberately small journey-awareness plugin for COVAS:NEXT.

Tracks:
- current and starting system
- tracked destination
- Elite NavRoute when the journal supplies it
- jumps completed on the current leg
- actual jump distance travelled
- average/recent jump distance
- route jumps remaining
- route progress percentage
- straight-line distance to the captured route destination
- fuel scoop count and tonnes scooped
- arrival at the tracked destination

It exposes only:
- tars_navigator_status
- tars_navigator_control

Important boundaries
--------------------
Navigator does NOT:
- plot routes
- search for stations/services
- control the ship
- estimate jumps remaining without a real NavRoute
- replace TARS Explorer or TARS Expedition

Elite/COVAS native navigation remains responsible for plotting and controlling routes.
TARS Navigator remembers and interprets journey progress.

Install
-------
Extract TARSNavigator into:

%appdata%\com.covas-next.ui\plugins\TARSNavigator\

manifest.json and TARSNavigator.py must be directly inside that folder.

Restart/reload the COVAS chat.

Suggested tests
---------------
"Where are we heading?"
"How many jumps have we done this leg?"
"How many jumps are left?"
"How far have we travelled?"
"Give me the full journey stats."

If Elite has not emitted a NavRoute, TARS should say remaining jumps are unknown
instead of inventing a number.


1.1.0 proactive journey commentary
----------------------------------
Navigator can now selectively dispatch TARSNavigatorTarget at meaningful journey moments:
- broad route progress milestones (25%, 50%, 75%)
- last 3 / last 2 jumps
- final jump
- arrival at the tracked destination
- meaningful destination changes
- substantial reroutes to the same destination

It deliberately does NOT speak on every jump. Raw Elite navigation events should remain KNOWN ON / REACT OFF.
All spoken milestones are generated from real tracked/NavRoute facts; Navigator still does not estimate remaining jumps without NavRoute data.


1.1.1 route progress fix
------------------------
- repeated NavRoute snapshots for the same destination no longer reset route progress to 0%
- same-destination reroutes preserve completed route work while adjusting the total progress basis to completed + newly remaining jumps
- a genuinely different destination starts a fresh progress basis
- route snapshots that do not begin with the known current system count all returned stars as remaining jumps


1.1.4 final-jump route continuity
- preserves a just-cleared Elite route destination privately for the next jump so
  NavRouteClear immediately before the final jump cannot suppress arrival detection
- never exposes that cleared route as current, and discards it after one unrelated jump

1.1.2 proactive event freshness
--------------------------------
- Navigator milestone events now carry session, timestamp, current-system and destination context
- queued milestones are dropped when the chat session ended, the event is older than 60 seconds, the ship moved on, or the tracked destination changed
- internal guard metadata is removed before building the model-facing prompt
