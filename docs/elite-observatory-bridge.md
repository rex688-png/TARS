# TARS Observatory Bridge

`TARS Observatory Bridge` is a first-party TARS runtime integration that consumes live facts exported by the Elite Observatory TARS bridge/output writer and injects them into the TARS event pipeline.

## Data path

By default the bridge watches:

```text
%LOCALAPPDATA%\TARS\observatory\events.jsonl
```

The path can be overridden in the **TARS Observatory Bridge** plugin settings. The integration is deliberately file-based: TARS does not need Observatory to expose a network service, and a missing `events.jsonl` file is non-fatal.

The uploaded bridge package contains the TARS/COVAS-side consumer only. An Elite Observatory-side component still has to write compatible JSONL records to the path above.

## Live-event protection

The bridge only relays records that satisfy all of the following:

- `realtime` is `true`;
- `monitor_mode` is `realtime`;
- `batch` is not `true`;
- `fact_type` starts with `notification:`.

On first attachment to an existing log, or after the log is replaced/rotated, the bridge starts at end-of-file so historical **Read All** output is not replayed as live speech. It stores its byte cursor and the most recent event IDs in the normal TARS plugin data directory.

## TARS behavior

Accepted records are dispatched as `TARSObservatoryFact` plugin events. The bridge registers a minimal passthrough prompt handler so the current TARS runtime can make a short exploration callout without requiring changes to the pinned external `TARS-Plugins` payload. The raw fact remains the source of truth; TARS is instructed not to invent missing values.

The integration is loaded after the five pinned TARS behavior plugins. This keeps the immutable `vendor/tars-plugins` payload and its provenance unchanged.

## Diagnostics

TARS exposes the global action:

```text
tars_observatory_diagnostics
```

It reports whether the events file exists, current watcher state, cursor position, relayed count, ignored historical/non-notification counts, the last source/fact type, and the most recent error.

If Observatory is not installed or the writer is not running, TARS continues normally and the bridge simply remains idle.
