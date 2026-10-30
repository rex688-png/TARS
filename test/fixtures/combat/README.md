# Combat replay provenance

The initial V1 tests used synthetic equivalents while no journal was available.
The commander later supplied the October 29–30 journal. `journal_combat.jsonl`
is a minimal sanitized derivative of that file, beginning with the Python Mk II
loadout and covering the later Anaconda combat session: 1,094 records, including
904 target updates, 39 UnderAttack events, 36 bounty awards, six hull-damage
records and the NPC fighter destruction/rebuild/relaunch/dock sequence.

`sanitize_journal.py` is the reproducible field allowlist. It removes commander,
location, chat, ship-name, account and unrelated content; aliases pilot, faction
and ship-ident strings; and shifts absolute dates to 2000-01-01 while preserving
intervals and ordering. It does not invent missing ShipID, Status, vehicle flags,
shield percentages or voice timestamps. The original file is not committed.

The raw journal has no Status.json samples. Tests keep that absence explicit.
Two seconds elapse between the first complete target scan and a matching-class
bounty award in one Anaconda-owned sequence; this is not proof of a two-second
complete fight, a solo kill, or an Anaconda-target kill. Focus intervals, target
observation spans and awards remain separate. No DPS/accuracy or STT/action
latency is derived from this journal.

Additional synthetic tests cover player-controlled fighter transitions, current
Status flags, permissions, stale data and concurrent optional speech.
