# TARS Observatory Bridge

TARS Observatory Bridge is the sixth official plugin in the pinned TARS plugin
bundle. It consumes live facts exported by the separate Elite Observatory-side
bridge and injects them into the normal TARS plugin event pipeline. It is not a
second built-in integration.

## Data path

By default the plugin watches:

```text
%LOCALAPPDATA%\TARS\observatory\events.jsonl
```

The path can be overridden in **Plugin Settings → TARS Observatory Bridge**. A
missing file is expected when Observatory or its writer is not running and does
not prevent TARS from starting.

The Observatory-side writer is distributed separately. TARS does not infer the
schema of other Observatory files and does not reproduce BioInsights,
Evaluator, Stat Scanner, AstroAnalytica, or other scientific analysis.

## Live-event protection

The plugin relays only records where `realtime` is true, `monitor_mode` is
`realtime`, `batch` is not true, and `fact_type` starts with `notification:`.
On first attachment to an existing log, and after replacement or rotation, it
starts at end-of-file so historical **Read All** output cannot become surprise
live speech. The byte cursor and recent event IDs are persisted in the normal
plugin-data directory.

Accepted records become `TARSObservatoryFact` events. The plugin asks the same
single TARS assistant for a short, natural, fact-preserving callout; it does not
create a separate personality.

## Diagnostics and degraded state

The `tars_observatory_diagnostics` action reports the configured path, whether
the file exists, watcher/cursor state, relay/filter counts, latest source and
latest error. “File not found” means the optional Observatory feed is currently
unavailable—not that TARS itself is offline.
