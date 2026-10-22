TARS Observatory Bridge 0.1.0

This TARS plugin reads Elite Observatory bridge output at:

%LOCALAPPDATA%\TARS\observatory\events.jsonl

It relays only new realtime notification records into the TARS event pipeline.
Historical Read All/pre-read records and non-notification records are consumed
without triggering speech. On first installation it attaches at EOF so existing
Observatory history is not replayed as live commentary.

The byte cursor and recent event IDs are persisted in the plugin data directory.

Use the action tars_observatory_diagnostics to inspect connection state. An
alternate events.jsonl path can be entered in the plugin settings.
