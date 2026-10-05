TARS GALAXY 1.4.1
===================

ROLE
----
TARS Galaxy is no longer a general-purpose replacement for COVAS:NEXT search.

COVAS NATIVE FIRST
------------------
Use COVAS native actions for normal questions:
- system_finder: system searches
- station_finder: stations, services, typed Material Traders, Technology Brokers,
  modules, ships and commodities
- body_finder: bodies and surface-signal searches
- material_finder: live engineering material state/sourcing
- blueprint_finder: engineering recipes against live inventory

Galaxy should be called only when it adds something COVAS does not:
1. A remote/unindexed exploration origin cannot be resolved by the normal station search.
2. A coordinate-verified deep-space station/service fallback is needed.
3. The commander explicitly asks to verify EDSM-synced private data.
4. Galaxy/provider diagnostics are requested.

REGISTERED ACTIONS
------------------
- tars_galaxy_nearest_station
  Fallback-only nearest regular-station lookup. Can bridge an obscure journal
  StarPos through EDSM to a nearby provider-known system, then recalculate
  returned station distances from the REAL journal coordinates.

- tars_galaxy_nearest_service
  Fallback-only station-service lookup using the same deep-space bridge.
  Normal service searches belong to COVAS station_finder. Material Traders and
  Technology Brokers are deliberately not accepted by Galaxy because native
  station_finder preserves Raw/Manufactured/Encoded and Human/Guardian subtype.
  When Galaxy fallback is actually needed for a specific service, this action
  owns the request alone; do not also call nearest_station unless it fails.

- tars_galaxy_commander_inventory
  Explicit EDSM-synced inventory fallback/verification only. Live COVAS material
  state remains authoritative.

- tars_galaxy_commander_status
  Explicit EDSM-synced credits/ranks/last-position verification only.
  Live COVAS journal location remains authoritative.

- tars_galaxy_diagnostics
  Reports current-location resolution, Ardent/EDData connectivity, whether the
  providers know the current origin, and whether the raw-coordinate fallback is ready.

REMOVED FROM THE ACTION SURFACE IN 1.4.0
----------------------------------------
- tars_galaxy_system_info
- tars_galaxy_stations_in_system

Those duplicated COVAS native system/station capabilities and encouraged the main
model to bypass the better-maintained Search Agent.

DEEP-SPACE FALLBACK
-------------------
When Ardent/EDData do not know the commander's current system:
1. Galaxy uses the current Elite journal StarPos as the authoritative origin.
2. EDSM sphere search finds nearby named systems from the raw XYZ coordinates.
3. Galaxy probes for the nearest system known by Ardent/EDData and uses it only
   as a QUERY PROXY.
4. Candidate destination-system coordinates are resolved.
5. Distances are recalculated from the commander's REAL StarPos.
6. Results are re-ranked using those corrected distances.

A proxy is never presented as the commander's actual location.

ACCURACY / FAILURE RULES
------------------------
- Live COVAS/journal state outranks external databases.
- Third-party station/service data may be stale.
- Provider failure or HTTP 404 means missing external data, not proof that no
  station/service exists.
- "Nearest permanent station" is the closest confirmed regular station among
  common service indexes; Ardent/EDData do not expose a mathematical
  nearest-any-station endpoint.
- Fleet Carriers are excluded unless explicitly allowed for service lookup.
- A generic Material Trader flag never establishes Raw/Manufactured/Encoded
  subtype and never means a station stocks or sells a named material.

EDSM COMMANDER PRIVACY
----------------------
Optional EDSM Commander Name + API Key are configured only in Galaxy settings.
The API key is never returned in action output. HTTP failures are sanitized so
requests-style exceptions cannot expose a query URL containing the key.
Never ask the commander to paste an API key into chat.

INSTALL / UPDATE
----------------
1. Close COVAS:NEXT.
2. Replace the existing TARSGalaxy folder.
3. Confirm:
   %APPDATA%\com.covas-next.ui\plugins\TARSGalaxy\manifest.json
4. Start COVAS and restart the active AI chat.

QUICK TESTS
-----------
Normal search routing:
  "Find me a Raw Material Trader."
Expected: COVAS station_finder, NOT Galaxy. Galaxy 1.4 rejects trader/broker
requests as a fail-safe even if an older prompt attempts to route them there.

Deep-space fallback:
  "Use the Galaxy fallback to find the closest permanent station."
Expected: tars_galaxy_nearest_station.

Diagnostics:
  "TARS, run Galaxy diagnostics."
Expected: tars_galaxy_diagnostics.

EDSM verification:
  "Verify my arsenic count against EDSM."
Expected: tars_galaxy_commander_inventory.

For an unindexed exploration system a healthy diagnostic may legitimately show
provider origin_known=false while journal coordinates and the coordinate proxy
are available.


1.4.1 SERVICE ROUTING
---------------------
- makes specific fallback service requests single-owner: tars_galaxy_nearest_service
  should answer alone when it succeeds
- tars_galaxy_nearest_station is no longer intended as a parallel companion call for
  every service lookup; it remains available for generic station requests or fallback
  after a service lookup failure
- keeps native COVAS station_finder as the first choice for ordinary service searches
