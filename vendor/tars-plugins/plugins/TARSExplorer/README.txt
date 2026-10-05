TARS Explorer 1.4.9

Major upgrade over 1.2.0:
- exceptional-body detection from journal facts (rings, gravity, temperature, mass/size, orbit, rotation, eccentricity, axial tilt, pressure, unusual classes)
- combines multiple exceptional properties into one target callout
- class-aware conservative thresholds to avoid ring/gas-giant spam
- system character and within-system relative highlights
- unfinished important-target warning on departure
- richer biology task completion when all DSS-confirmed genera are analysed
- exceptional properties exposed through body/system actions and priority scoring
- existing FSS completion, DSS, Codex, approach context and selective biology callouts retained

IMPORTANT: keep relevant journal events KNOWN, REACT OFF. Explorer emits TARSExplorerTarget selectively.
This includes derived COVAS exobiology reactions ScanOrganicFirst, ScanOrganicSecond,
and ScanOrganicThird when they are exposed; otherwise a raw completion reaction can
speak immediately before Explorer's selective completion callout.

Heuristics intentionally describe facts as unusual/exceptional; they do not claim statistical rarity unless the journal/body class itself supports the wording.

1.3.2: core ELW/Water World/Ammonia/terraformable callouts are protected from exceptional-body heuristics; diagnostics now retain recent callout decisions and suppression reasons.


1.3.4: body-family-aware exceptional rules; water/ammonia-life gas giants; ring combinations; no honk-only body-count chatter; no post-FSDJump old-system warnings; player-facing FSS payloads; TTS-friendly quantities.


1.4.0:
- explicit system composition: stars, planets, moons and belt clusters
- moon/planet distinction from Scan Parents journal data
- zero-planet systems are only declared when FSSAllBodiesFound confirms completion
- completed zero-planet systems expose fss_required=false, so TARS can say FSS needs no further work
- existing 1.3.4 noteworthy-world, exceptional-body, biology, DSS, Codex, diagnostics and anti-chatter behavior retained

- system-level novelty suppression: repeated non-core observations (for example similar ring, gravity, orbit or rotation remarks) do not each trigger a new callout
- novelty is based on observation families rather than exact wording/numbers
- a later body still speaks if it introduces at least one genuinely new exceptional idea
- ELW, Water World, Ammonia World and terraformable callouts bypass novelty suppression
- diagnostics expose recent suppression reasons and novelty idea families seen in the current system


1.4.1:
- clears stale system address/coordinates when a new system arrives without those fields
- diagnostics now report the actual 1.4.1 plugin version


1.4.2:
- DSS completion now participates in the same-body speech cooldown used by scan/biology callouts
- immediate DSS + biology/scan event bursts produce one conversational remark instead of two near-duplicates
- suppressed DSS decisions are recorded in diagnostics
- genuinely new same-body information can still speak after the cooldown window


1.4.3:
- unifies body records when early journal events identify a body only by name and later events provide BodyID
- name-only events reuse an existing named BodyID record instead of creating a duplicate
- partial ID-only and name-only records merge when a later event proves they are the same body
- body callout/deduplication tracking migrates to the stable BodyID key when identity is promoted


1.4.4:
- proactive Explorer events now carry a session/time/system guard
- queued events older than 60 seconds, from an ended chat, or from a previous system are dropped before the model replies
- internal guard metadata is removed before constructing the model-facing prompt


1.4.5:
- proactive Explorer callouts are explicitly fact-first; humor is optional rather than required
- suppresses recurring canned endings built around mystery/mysterious, "main character",
  "wants attention", "invitation", "refuses", "ambitious", "misbehaving", "trying hard"
  and similar anthropomorphic planet/system personalities
- suppresses paperwork/bureaucracy filler in Explorer callouts
- prefers a plain useful observation over a forced joke when no fresh grounded punchline exists
- moderate size/mass on non-landable icy/rocky bodies no longer earns an automatic callout by itself
- two ring systems on an otherwise ordinary gas giant are supporting context, not a standalone reason to interrupt


1.4.6:
- suppresses recurring work/payoff idioms such as "earn their keep", "work for their keep"
  and "earn the right to complain" in proactive Explorer callouts
- keeps useful factual phrases such as "worth mapping" or "worth landing on" legal when
  they are genuinely grounded in the current target


1.4.9:
- FSS completion wrap-ups now wait briefly for trailing same-second Scan events,
  preventing incomplete multi-star/body composition summaries.

1.4.7:
- narrows automatic speech to high-value exploration facts: ELW/Water World/Ammonia,
  terraformables, meaningful biology, Codex and useful DSS/organic milestones
- keeps axial tilt, ordinary short orbits, normal ring trivia and moderate gas-giant
  gravity available in actions without interrupting the commander automatically
- raises the standalone gas-giant gravity threshold to a genuinely extreme 20 g
- ordinary FSS-complete systems may remain silent; useful/biological/zero-planet
  systems can still receive a concise wrap-up
- extends same-body speech gating to 45 seconds and prevents a biology-rich scan
  from immediately generating a second biology callout for the same fact
- FSS completion payloads now explicitly expose FSS and DSS state; model prompting
  forbids describing FSSAllBodiesFound as "fully mapped" or equivalent
