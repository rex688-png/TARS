# TARS native shell

The main renderer now keeps one navigation frame through backend configuration,
start, active conversation, and stop. Its primary destinations are TARS,
Exploration, Storage, and Settings. `TarsApplicationCoordinator` still owns the
existing backend and overlay sequencing. Settings retains provider installation,
prompt editing, reaction configuration, keybind diagnostics, and advanced tools.

Chat remains mounted when another destination is selected. A completed
`web_search_agent` result is retained as an expandable detail card below the
conversation; it no longer switches to the former Search tab. Existing runtime
UI requests for Navigation and Storage map to the new destinations. A request
to show Search leaves the current destination unchanged.

Exploration summaries use Location, NavInfo, ExobiologyScan, and the existing
system-record view. Storage summaries use Materials and Cargo projections.
Unknown data is shown as unavailable rather than estimated. Detailed system
and inventory views remain expandable so their working queries and controls
are available without becoming primary navigation. Expedition history and
Observatory findings do not yet have a dedicated frontend projection; they
remain available through TARS conversation and can be added to this view when
an authoritative UI state interface exists.

The microphone label reports the configured voice/PTT mode. PTT itself remains
controlled by the existing runtime hotkeys; the UI links to its settings and
does not pretend to drive a new audio command. Live provider and model health
is reported only to the fidelity already supported by `TarsRuntimeFacade`.

The unchanged canonical avatar PNG is a 2×2 state sheet. CSS displays one
state at a time in the main shell, settings preview, and overlay. The packaged
Electron `app://` handler now decodes asset filenames containing spaces and
rejects paths outside the bundled UI directory. Production SVG logos are
copied from `branding/vector` into the Angular assets; the Windows icon is
rendered from the canonical app-icon SVG. The logo and conversational avatar
serve different roles.
