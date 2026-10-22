# Synthetic Elite journal fixtures

All names, IDs and coordinates here are constructed test values, not user
journal exports. Each `.jsonl` line has the shape written by Elite. The helper
copies it to a `Journal.*.log` file and reads it with `EDJournal.load_history`.

| Fixture | Scenarios |
| --- | --- |
| `journey.jsonl` | Login, Caspian Explorer `eXPY`, docked, undocked, normal space, supercruise, route, hyperspace jump, system arrival, FSS, water-world scan, DSS mapping, biological signal, touchdown, SRV launch, exobiology samples and route clearing. |
| `last_known.jsonl` | Saved commander/location while game is closed; historical events do not establish live telemetry. |
| `new_session.jsonl` | New journal file/session with a different system; the newest file replaces the old file as the reader's history source. |
| `no_route.jsonl` | Explicit route clearing without treating absence of a route as a failure. |
| `malformed.jsonl` | A partial JSON line between valid events; the reader skips it and retains subsequent events. |
| `status_normal.json`, `status_low_fuel.json` | Status.json examples with authoritative fuel readings; low/normal is a fixture distinction, not a new runtime threshold. |
| `nav_route.json` | Elite's companion route file. `EDJournal` augments the `NavRoute` line only when its timestamp matches. |

An empty journal directory covers game-not-running/no-current-journal. Tests
that append after history loading exercise the reader's live queue; they must
not label saved history as live. `Status.json` is separate from journal events.
