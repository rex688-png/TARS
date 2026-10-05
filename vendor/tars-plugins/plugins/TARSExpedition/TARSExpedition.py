from __future__ import annotations

import json
import math
import os
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, override

from pydantic import BaseModel, Field

from lib.PluginBase import PluginBase, PluginManifest
from lib.PluginHelper import PluginHelper
from lib.Logger import log


class ExpeditionRebuildArgs(BaseModel):
    """No-argument schema for explicit journal rebuild requests."""
    pass


class ExpeditionStatusArgs(BaseModel):
    detail: Literal["brief", "full"] = Field(
        default="brief",
        description="brief for normal questions; full only when the commander asks for a detailed expedition report."
    )


class ExpeditionHistoryArgs(BaseModel):
    query: str = Field(
        default="latest",
        description=(
            "What to retrieve from expedition history. Examples: latest, previous, all, "
            "'Rohini', 'Earth-like', 'best biology'. Keep this close to the commander's wording."
        )
    )
    limit: int = Field(default=5, ge=1, le=20, description="Maximum archived expeditions to return.")


class ExpeditionControlArgs(BaseModel):
    operation: Literal["start_new", "finish_current", "rebuild_from_journals"] = Field(
        description=(
            "Destructive/administrative expedition operation. Use ONLY when the commander explicitly asks "
            "to start a new expedition, finish/archive the current expedition, or rebuild history from journals."
        )
    )
    label: str = Field(
        default="",
        description="Optional human-readable expedition label supplied by the commander."
    )


class TARSExpedition(PluginBase):
    """
    TARS Expedition 1.0.4

    Small persistent expedition historian:
      * one-time retroactive Elite journal import
      * incremental live journal updates through COVAS sideeffects
      * current expedition + compact completed archive
      * factual highlights, actual sales, and simple trip metrics
      * focused status/history/control actions plus a dedicated no-argument rebuild action

    It deliberately does NOT do route planning, station search, engineering,
    ship-health monitoring, or general exploration interpretation.
    """

    settings_config = {
        "key": "TARSExpedition",
        "label": "TARS Expedition",
        "icon": "explore",
        "grids": [
            {
                "key": "about",
                "label": "Expedition History",
                "fields": [
                    {
                        "key": "about_text",
                        "label": "What this plugin does",
                        "type": "paragraph",
                        "readonly": True,
                        "placeholder": None,
                        "content": (
                            "Tracks exploration expeditions from Elite journal events, persists them across "
                            "COVAS restarts, and imports existing journals retroactively on first run. "
                            "It exposes only status, history, and explicit expedition-control actions."
                        ),
                    }
                ],
            }
        ],
    }

    def __init__(self, plugin_manifest: PluginManifest):
        super().__init__(plugin_manifest)
        self._manifest = plugin_manifest
        self._helper: PluginHelper | None = None
        self._lock = threading.RLock()
        self._state_path: Path | None = None
        self._state = self._empty_state()

    # ---------- lifecycle ----------

    @override
    def on_chat_start(self, helper: PluginHelper):
        self._helper = helper
        data_dir = Path(helper.get_plugin_data_path(self._manifest))
        data_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = data_dir / "expeditions.json"
        self._load()

        # First run: reconstruct history from the commander's local Elite journals.
        if not self._state.get("journal_import_done"):
            try:
                result = self._rebuild_from_journals()
                log("info", f"TARS Expedition retroactive import: {result}")
            except Exception as exc:
                log("warning", f"TARS Expedition journal import failed: {exc}")

        helper.register_sideeffect(self._observe_event)

        helper.register_action(
            name="tars_expedition_status",
            description=(
                "PRIMARY source for CURRENT-EXPEDITION totals, stats, highlights, discoveries and payout breakdowns. "
                "Returns jumps, systems, scans, maps, notable worlds, biology, distance, docking, first discoveries, "
                "and actual journal-recorded Cartographics/Vista sales. Use detail='full' for 'full stats', detailed "
                "reports, highlights, or payout breakdown questions. Use this action FIRST and normally ALONE for "
                "questions like 'full stats for this expedition', 'what were the highlights?', 'how much did I make "
                "from cartography and exobiology?', 'how many systems?', or 'what have we found this trip?'. "
                "Do NOT also call Explorer/Navigator unless the commander separately asks about the current system "
                "or current plotted route."
            ),
            parameters=ExpeditionStatusArgs,
            method=self._action_status,
            action_type="global",
        )

        helper.register_action(
            name="tars_expedition_history",
            description=(
                "PRIMARY source for COMPLETED expedition history reconstructed from Elite journals. "
                "Use for previous/latest completed trips, historical discoveries, historical payout breakdowns, "
                "or comparisons between expeditions. Do not substitute Explorer current-system state, Navigator "
                "route state, or conversational memory for archived expedition facts."
            ),
            parameters=ExpeditionHistoryArgs,
            method=self._action_history,
            action_type="global",
        )

        helper.register_action(
            name="tars_expedition_rebuild",
            description=(
                "EXPLICIT JOURNAL REBUILD action. Use when the commander directly asks to rebuild, re-read, "
                "or reconstruct expedition history from local Elite Journal.*.log files. This action takes no "
                "arguments, so do NOT use tars_expedition_control for a normal rebuild request. Returns compact "
                "structured diagnostics instead of a large history payload."
            ),
            parameters=ExpeditionRebuildArgs,
            method=self._action_rebuild,
            action_type="global",
        )

        helper.register_action(
            name="tars_expedition_control",
            description=(
                "Administrative expedition control for explicitly starting or finishing an expedition. "
                "Legacy rebuild_from_journals remains accepted for compatibility, but normal explicit rebuild "
                "requests should use tars_expedition_rebuild. Never call this merely to answer an expedition question."
            ),
            parameters=ExpeditionControlArgs,
            method=self._action_control,
            action_type="global",
        )

        helper.register_status_generator(self._status_context)
        log("info", "TARS Expedition 1.0.4 started.")

    @override
    def on_chat_stop(self, helper: PluginHelper):
        self._save()
        self._helper = None

    # ---------- state ----------

    def _empty_trip(self, started_at: str | None = None, label: str = "") -> dict[str, Any]:
        return {
            "label": label,
            "started_at": started_at,
            "ended_at": None,
            "start_system": None,
            "last_system": None,
            "last_docked_station": None,
            "last_docked_system": None,
            "jumps": 0,
            "jump_distance_ly": 0.0,
            "systems": [],
            "bodies_scanned": 0,
            "bodies_mapped": 0,
            "terraformables_scanned": 0,
            "earthlikes": [],
            "water_worlds": [],
            "ammonia_worlds": [],
            "bio_signal_count": 0,
            "bio_bodies": {},
            "organic_completed": 0,
            "organic_species": [],
            "first_discovery_scans": 0,
            "first_mapped": 0,
            "furthest_from_sol_ly": 0.0,
            "furthest_system": None,
            "cartography_sales_cr": 0,
            "exobiology_sales_cr": 0,
            "cartography_sale_events": 0,
            "exobiology_sale_events": 0,
            "sale_events": 0,
            "last_sale_at": None,
            "last_sale_system": None,
            "highlights": [],
            "_scanned_body_keys": [],
            "_mapped_body_keys": [],
            "_sale_event_keys": [],
            "_pending_sale": False,
            "_activity": False,
        }

    def _empty_state(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "journal_import_done": False,
            "current": self._empty_trip(),
            "archive": [],
            "last_event_key": None,
        }

    def _load(self):
        if not self._state_path or not self._state_path.exists():
            return
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("schema") == 1:
                self._state = raw
                self._normalise_state()
        except Exception as exc:
            log("warning", f"TARS Expedition could not load state: {exc}")

    def _normalise_trip(self, trip: dict[str, Any]):
        defaults = self._empty_trip()
        for key, value in defaults.items():
            if key not in trip:
                trip[key] = deepcopy(value)

    def _normalise_state(self):
        current = self._state.get("current")
        if not isinstance(current, dict):
            self._state["current"] = self._empty_trip()
        else:
            self._normalise_trip(current)
        archive = self._state.get("archive")
        if not isinstance(archive, list):
            self._state["archive"] = []
        else:
            for trip in archive:
                if isinstance(trip, dict):
                    self._normalise_trip(trip)

    def _save(self):
        if not self._state_path:
            return
        try:
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._state_path)
        except Exception as exc:
            log("warning", f"TARS Expedition could not save state: {exc}")

    # ---------- journal discovery/import ----------

    def _journal_dir(self) -> Path | None:
        # Standard location first.
        home = Path.home()
        candidates = [
            home / "Saved Games" / "Frontier Developments" / "Elite Dangerous",
            Path(os.environ.get("USERPROFILE", str(home))) / "Saved Games" / "Frontier Developments" / "Elite Dangerous",
        ]

        # Windows Known Folder lookup handles redirected/localized Saved Games.
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes
                # FOLDERID_SavedGames = {4C5C32FF-BB9D-43B0-BF7D-5D9A1B3D6B83}
                class GUID(ctypes.Structure):
                    _fields_ = [
                        ("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)
                    ]
                guid = GUID(0x4C5C32FF, 0xBB9D, 0x43B0, (ctypes.c_ubyte * 8)(0xBF,0x7D,0x5D,0x9A,0x1B,0x3D,0x6B,0x83))
                path_ptr = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path_ptr)) == 0:
                    candidates.insert(0, Path(path_ptr.value) / "Frontier Developments" / "Elite Dangerous")
                    ctypes.windll.ole32.CoTaskMemFree(path_ptr)
            except Exception:
                pass

        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return None

    def _journal_files(self) -> list[Path]:
        d = self._journal_dir()
        if not d:
            return []
        return sorted(d.glob("Journal.*.log"), key=lambda p: p.name)

    def _rebuild_from_journals(self) -> dict[str, Any]:
        started = time.monotonic()
        files = self._journal_files()
        if not files:
            home = Path.home()
            user_home = Path(os.environ.get("USERPROFILE", str(home)))
            searched = list(dict.fromkeys(str(p) for p in (
                home / "Saved Games" / "Frontier Developments" / "Elite Dangerous",
                user_home / "Saved Games" / "Frontier Developments" / "Elite Dangerous",
            )))
            return {
                "ok": False,
                "error_code": "JOURNAL_FILES_NOT_FOUND",
                "error": "Elite Dangerous journal folder not found or contains no Journal.*.log files.",
                "searched_paths": searched,
                "assistant_instruction": (
                    "Report that local Journal.*.log files were not found and include the searched paths. "
                    "Do not describe this as a generic backend failure."
                ),
            }

        # Rebuild under the plugin lock so live journal sideeffects cannot interleave
        # with a state reset. Keep the previous state available for rollback if an
        # unexpected top-level failure occurs.
        with self._lock:
            previous_state = self._state
            self._state = self._empty_state()
            count = 0
            bad = 0
            failed_files: list[str] = []
            try:
                for path in files:
                    try:
                        with path.open("r", encoding="utf-8", errors="replace") as fh:
                            for line in fh:
                                try:
                                    event = json.loads(line)
                                    if isinstance(event, dict):
                                        self._process_game_event(event, historic=True, save=False)
                                        count += 1
                                except Exception:
                                    bad += 1
                    except Exception as exc:
                        failed_files.append(path.name)
                        log("warning", f"TARS Expedition skipped {path.name}: {exc}")

                import_complete = not failed_files
                self._state["journal_import_done"] = import_complete
                self._normalise_state()
                self._save()
                current = self._state["current"]
                return {
                    "ok": import_complete,
                    "journal_directory": str(files[0].parent),
                    "journal_files": len(files),
                    "journal_files_failed": len(failed_files),
                    "failed_journal_files": failed_files[:20],
                    "events_processed": count,
                    "malformed_lines_skipped": bad,
                    "completed_expeditions": len(self._state["archive"]),
                    # Keep the action payload compact. Full expedition detail remains
                    # available through tars_expedition_status(detail="full").
                    "current_expedition": self._public_trip(current, full=False),
                    "current_sales": self._sales_breakdown(current),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "assistant_instruction": (
                        "Rebuild completed from local Elite journal files. Use these journal-derived facts only. "
                        "If ok is false, report the failed files and do not claim the rebuild succeeded."
                    ),
                }
            except Exception as exc:
                self._state = previous_state
                log("error", f"TARS Expedition rebuild failed and previous state was restored: {exc}")
                return {
                    "ok": False,
                    "error_code": "REBUILD_FAILED",
                    "error": str(exc),
                    "previous_state_restored": True,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }

    # ---------- live events ----------

    def _observe_event(self, event, context):
        if getattr(event, "kind", "") != "game":
            return
        content = getattr(event, "content", {}) or {}
        if not isinstance(content, dict):
            return

        # COVAS may replay historic game events on startup. Retroactive import already
        # handles those, so only consume live events here.
        if getattr(event, "historic", False):
            return

        with self._lock:
            self._process_game_event(content, historic=False, save=True)

    def _event_key(self, e: dict[str, Any]) -> str:
        """Fingerprint the complete event so same-second sale pages remain distinct."""
        try:
            return json.dumps(e, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except Exception:
            return "|".join(str(e.get(k, "")) for k in (
                "timestamp", "event", "StarSystem", "BodyName", "StationName",
                "TotalEarnings", "BaseValue", "Bonus", "MarketID",
            ))

    def _process_game_event(self, e: dict[str, Any], historic: bool, save: bool):
        name = str(e.get("event", "") or "")
        if not name:
            return

        key = self._event_key(e)
        if not historic and key and key == self._state.get("last_event_key"):
            return
        if not historic:
            self._state["last_event_key"] = key

        trip = self._state["current"]
        ts = e.get("timestamp")

        # A sale closes an expedition only when the commander subsequently leaves
        # on another jump. This groups Cartographics + Vista sales at the same stop.
        if name == "FSDJump" and trip.get("_pending_sale") and self._has_meaningful_trip(trip):
            departure_system = trip.get("last_system")
            self._archive_current(end_time=ts)
            trip = self._state["current"]
            if departure_system:
                trip["start_system"] = departure_system
                trip["last_system"] = departure_system
                self._add_unique(trip["systems"], departure_system)

        if name == "FSDJump":
            self._touch_trip(trip, ts)
            system = e.get("StarSystem")
            if system:
                # Prefer the known departure/current system as expedition start.
                # If no Location/history established one, the arrival system is
                # still a last-resort fallback rather than leaving it blank.
                if not trip.get("start_system"):
                    trip["start_system"] = trip.get("last_system") or system
                trip["last_system"] = system
                self._add_unique(trip["systems"], system)
            trip["jumps"] += 1
            try:
                trip["jump_distance_ly"] += float(e.get("JumpDist") or 0)
            except Exception:
                pass
            self._update_furthest(trip, e.get("StarPos"), system)
            trip["_activity"] = True

        elif name in ("Location", "CarrierJump"):
            system = e.get("StarSystem")
            if system:
                if not trip.get("start_system"):
                    trip["start_system"] = system
                trip["last_system"] = system
                self._add_unique(trip["systems"], system)
                self._update_furthest(trip, e.get("StarPos"), system)

        elif name == "Docked":
            trip["last_docked_station"] = e.get("StationName")
            trip["last_docked_system"] = e.get("StarSystem") or trip.get("last_system")

        elif name == "Scan":
            self._touch_trip(trip, ts)
            body_key = self._event_body_key(trip, e)
            new_scan = self._mark_unique_key(trip, "_scanned_body_keys", body_key)
            if new_scan:
                trip["bodies_scanned"] += 1
            trip["_activity"] = True
            body = e.get("BodyName") or "unknown body"
            planet_class = str(e.get("PlanetClass", "") or "")
            terraform = str(e.get("TerraformState", "") or "").casefold()
            if "terraform" in terraform:
                if new_scan:
                    trip["terraformables_scanned"] += 1
                self._highlight(trip, "terraformable", body)
            if planet_class == "Earthlike body":
                self._add_unique(trip["earthlikes"], body)
                self._highlight(trip, "earth_like", body)
            elif planet_class == "Water world":
                self._add_unique(trip["water_worlds"], body)
                self._highlight(trip, "water_world", body)
            elif planet_class == "Ammonia world":
                self._add_unique(trip["ammonia_worlds"], body)
                self._highlight(trip, "ammonia_world", body)
            if new_scan and e.get("WasDiscovered") is False:
                trip["first_discovery_scans"] += 1

        elif name == "SAAScanComplete":
            self._touch_trip(trip, ts)
            body_key = self._event_body_key(trip, e)
            new_map = self._mark_unique_key(trip, "_mapped_body_keys", body_key)
            if new_map:
                trip["bodies_mapped"] += 1
            trip["_activity"] = True
            if new_map and e.get("WasMapped") is False:
                trip["first_mapped"] += 1

        elif name in ("FSSBodySignals", "SAASignalsFound"):
            signals = e.get("Signals") or []
            bio_count = 0
            for sig in signals:
                if not isinstance(sig, dict):
                    continue
                typ = str(sig.get("Type", "") or "").casefold()
                if "biological" in typ:
                    try:
                        bio_count += int(sig.get("Count") or 0)
                    except Exception:
                        pass
            if bio_count:
                self._touch_trip(trip, ts)
                body = e.get("BodyName") or "unknown body"
                old = int(trip["bio_bodies"].get(body, 0))
                trip["bio_bodies"][body] = max(old, bio_count)
                trip["bio_signal_count"] = sum(int(v) for v in trip["bio_bodies"].values())
                trip["_activity"] = True
                if bio_count >= 4:
                    self._highlight(trip, "rich_biology", body, {"signals": bio_count})

        elif name == "ScanOrganic":
            self._touch_trip(trip, ts)
            trip["_activity"] = True
            if str(e.get("ScanType", "")).casefold() == "analyse":
                trip["organic_completed"] += 1
                species = e.get("Species_Localised") or e.get("Species") or e.get("Genus_Localised") or e.get("Genus")
                if species:
                    self._add_unique(trip["organic_species"], species)
                    self._highlight(trip, "organic_complete", species, {"body": e.get("Body") or e.get("BodyName")})
                if e.get("NewDiscovery") is True:
                    self._highlight(trip, "first_organic_discovery", species or "organic sample")

        elif name in ("SellExplorationData", "MultiSellExplorationData"):
            # Elite writes MultiSellExplorationData when selling a Cartographics page
            # at a time, and SellExplorationData in other sale flows. TotalEarnings is
            # authoritative; BaseValue + Bonus is a documented fallback.
            sale_key = self._event_key(e)
            if self._mark_unique_key(trip, "_sale_event_keys", sale_key):
                amount = self._number(e.get("TotalEarnings"))
                if not amount:
                    amount = self._number(e.get("BaseValue")) + self._number(e.get("Bonus"))
                if amount:
                    self._touch_trip(trip, ts)
                    trip["cartography_sales_cr"] += int(amount)
                    trip["cartography_sale_events"] = int(trip.get("cartography_sale_events") or 0) + 1
                    trip["sale_events"] += 1
                    trip["last_sale_at"] = ts
                    trip["last_sale_system"] = trip.get("last_docked_system") or trip.get("last_system")
                    trip["_pending_sale"] = True

        elif name == "SellOrganicData":
            # Odyssey journals normally store per-organism Value + first-log Bonus in
            # BioData. Accept TotalEarnings too when a schema/provider supplies it.
            sale_key = self._event_key(e)
            if self._mark_unique_key(trip, "_sale_event_keys", sale_key):
                amount = self._number(e.get("TotalEarnings"))
                if not amount:
                    amount = 0
                    for item in e.get("BioData") or []:
                        if isinstance(item, dict):
                            amount += self._number(item.get("Value"))
                            amount += self._number(item.get("Bonus"))
                if amount:
                    self._touch_trip(trip, ts)
                    trip["exobiology_sales_cr"] += int(amount)
                    trip["exobiology_sale_events"] = int(trip.get("exobiology_sale_events") or 0) + 1
                    trip["sale_events"] += 1
                    trip["last_sale_at"] = ts
                    trip["last_sale_system"] = trip.get("last_docked_system") or trip.get("last_system")
                    trip["_pending_sale"] = True

        if save:
            self._save()

    # ---------- helpers ----------

    def _touch_trip(self, trip: dict[str, Any], ts: str | None):
        if not trip.get("started_at"):
            trip["started_at"] = ts or datetime.now(timezone.utc).isoformat()

    def _number(self, x) -> float:
        try:
            return float(x or 0)
        except Exception:
            return 0.0

    def _add_unique(self, seq: list, value):
        if value not in seq:
            seq.append(value)

    def _event_body_key(self, trip: dict[str, Any], e: dict[str, Any]) -> str | None:
        """Stable expedition-wide identity for a physical body when journal facts allow it."""
        system = str(
            e.get("StarSystem")
            or e.get("SystemName")
            or trip.get("last_system")
            or ""
        ).strip()
        address = e.get("SystemAddress")
        body_id = e.get("BodyID")
        if body_id is None and e.get("event") == "ScanOrganic":
            body_id = e.get("Body")
        body_name = str(e.get("BodyName") or "").strip()

        system_key = f"addr:{address}" if address is not None else (f"name:{system.casefold()}" if system else "")
        if body_id is not None:
            return f"{system_key}|id:{body_id}" if system_key else f"id:{body_id}"
        if body_name:
            return f"{system_key}|name:{body_name.casefold()}" if system_key else f"name:{body_name.casefold()}"
        return None

    @staticmethod
    def _mark_unique_key(trip: dict[str, Any], field: str, key: str | None) -> bool:
        """Return True for a new identifiable body, or for an unidentifiable event.

        Hidden key lists are persisted so duplicate journal events do not inflate
        counters. Existing 1.0.1 state remains compatible; its prior counters are
        preserved and only post-upgrade events participate in the new dedupe set.
        """
        if not key:
            return True
        seen = trip.setdefault(field, [])
        if key in seen:
            return False
        seen.append(key)
        return True

    def _update_furthest(self, trip: dict[str, Any], pos, system):
        if not isinstance(pos, (list, tuple)) or len(pos) < 3:
            return
        try:
            d = math.sqrt(float(pos[0])**2 + float(pos[1])**2 + float(pos[2])**2)
        except Exception:
            return
        if d > float(trip.get("furthest_from_sol_ly") or 0):
            trip["furthest_from_sol_ly"] = round(d, 2)
            trip["furthest_system"] = system

    def _highlight(self, trip: dict[str, Any], kind: str, subject: Any, extra: dict | None = None):
        if not subject:
            return
        item = {"type": kind, "subject": str(subject)}
        if extra:
            item.update({k: v for k, v in extra.items() if v is not None})
        # Exact semantic duplicates are not useful history.
        if item not in trip["highlights"]:
            trip["highlights"].append(item)
            if len(trip["highlights"]) > 120:
                trip["highlights"] = trip["highlights"][-120:]

    def _has_meaningful_trip(self, trip: dict[str, Any]) -> bool:
        return bool(
            trip.get("_activity")
            or trip.get("jumps")
            or trip.get("bodies_scanned")
            or trip.get("organic_completed")
            or trip.get("cartography_sales_cr")
            or trip.get("exobiology_sales_cr")
        )

    def _archive_current(self, end_time: str | None = None, label: str = ""):
        trip = self._state["current"]
        if not self._has_meaningful_trip(trip):
            self._state["current"] = self._empty_trip(started_at=end_time, label=label)
            return
        archived = deepcopy(trip)
        archived["ended_at"] = end_time or datetime.now(timezone.utc).isoformat()
        if label:
            archived["label"] = label
        archived.pop("_pending_sale", None)
        archived.pop("_activity", None)
        self._state["archive"].append(archived)
        # Keep a substantial but bounded archive. Raw journals remain source of truth.
        self._state["archive"] = self._state["archive"][-250:]
        self._state["current"] = self._empty_trip(started_at=end_time)

    def _sales_breakdown(self, trip: dict[str, Any]) -> dict[str, Any]:
        cartography = int(trip.get("cartography_sales_cr") or 0)
        exobiology = int(trip.get("exobiology_sales_cr") or 0)
        return {
            "cartography_cr": cartography,
            "exobiology_cr": exobiology,
            "total_cr": cartography + exobiology,
            "cartography_sale_events": int(trip.get("cartography_sale_events") or 0),
            "exobiology_sale_events": int(trip.get("exobiology_sale_events") or 0),
            "sale_events_total": int(trip.get("sale_events") or 0),
            "last_sale_at": trip.get("last_sale_at"),
            "last_sale_system": trip.get("last_sale_system"),
        }

    def _public_trip(self, trip: dict[str, Any], full: bool = False) -> dict[str, Any]:
        result = {k: deepcopy(v) for k, v in trip.items() if not k.startswith("_")}
        result["systems_visited"] = len(trip.get("systems", []))
        result["earthlike_count"] = len(trip.get("earthlikes", []))
        result["water_world_count"] = len(trip.get("water_worlds", []))
        result["ammonia_world_count"] = len(trip.get("ammonia_worlds", []))
        result["organic_species_count"] = len(trip.get("organic_species", []))
        result["highlight_count"] = len(trip.get("highlights", []))
        result["sales"] = self._sales_breakdown(trip)
        result["actual_sales_cr"] = result["sales"]["total_cr"]
        result["sale_boundary_pending"] = bool(trip.get("_pending_sale"))
        if not full:
            result.pop("systems", None)
            result["highlights"] = trip.get("highlights", [])[-12:]
            result.pop("earthlikes", None)
            result.pop("water_worlds", None)
            result.pop("ammonia_worlds", None)
            result.pop("organic_species", None)
            result.pop("bio_bodies", None)
        return result

    # ---------- actions ----------

    def _action_status(self, args: ExpeditionStatusArgs):
        with self._lock:
            trip = self._public_trip(self._state["current"], full=(args.detail == "full"))
            return json.dumps({
                "ok": True,
                "detail": args.detail,
                "completed_expeditions_total": len(self._state.get("archive", [])),
                "current_expedition": trip,
                "sales_breakdown": self._sales_breakdown(self._state["current"]),
                "assistant_instruction": (
                    "These are the authoritative journal-derived CURRENT-EXPEDITION facts. "
                    "For expedition totals, highlights and Cartographics/Vista payout breakdowns, answer from this "
                    "result without calling Explorer or Navigator again. Actual sales are recorded payouts only; "
                    "do not invent unsold value. Use Explorer only if the commander separately asks about the "
                    "current system, and Navigator only if they separately ask about the current plotted route."
                )
            }, ensure_ascii=False)

    def _action_history(self, args: ExpeditionHistoryArgs):
        with self._lock:
            archive = list(self._state.get("archive", []))
            q = (args.query or "latest").strip().casefold()

            if q in ("latest", "last", "previous"):
                chosen = archive[-args.limit:]
            elif q in ("all", "recent"):
                chosen = archive[-args.limit:]
            else:
                terms = [t for t in q.replace(",", " ").split() if len(t) >= 3]
                scored = []
                for trip in archive:
                    hay = json.dumps(trip, ensure_ascii=False).casefold()
                    score = sum(1 for t in terms if t in hay)
                    if score:
                        scored.append((score, trip.get("ended_at") or "", trip))
                scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
                chosen = [x[2] for x in scored[:args.limit]]

            return json.dumps({
                "ok": True,
                "query": args.query,
                "completed_expeditions_total": len(archive),
                "results": [self._public_trip(x, full=False) for x in chosen],
                "assistant_instruction": (
                    "Use only these journal-derived historical results. If the query returned no matches, say so. "
                    "Do not manufacture a past expedition from conversational memory."
                )
            }, ensure_ascii=False)

    def _action_rebuild(self, args: ExpeditionRebuildArgs):
        """Dedicated no-argument rebuild path.

        A separate action avoids function-schema failures around the control
        operation enum and keeps rebuild diagnostics compact and explicit.
        """
        try:
            result = self._rebuild_from_journals()
        except Exception as exc:
            log("error", f"TARS Expedition rebuild action failed: {exc}")
            result = {
                "ok": False,
                "error_code": "REBUILD_ACTION_FAILED",
                "error": str(exc),
                "assistant_instruction": (
                    "Report the exact Expedition rebuild error. Do not call it a generic backend failure."
                ),
            }
        return json.dumps(result, ensure_ascii=False)

    def _action_control(self, args: ExpeditionControlArgs):
        # Backward-compatible legacy route. New prompt/action descriptions direct
        # explicit rebuild requests to the no-argument action above.
        if args.operation == "rebuild_from_journals":
            return self._action_rebuild(ExpeditionRebuildArgs())

        with self._lock:
            if args.operation == "finish_current":
                if not self._has_meaningful_trip(self._state["current"]):
                    return json.dumps({"ok": False, "error": "Current expedition has no meaningful recorded activity."})
                finished = self._public_trip(self._state["current"], full=True)
                self._archive_current(label=args.label)
                self._save()
                return json.dumps({
                    "ok": True,
                    "message": "Current expedition archived.",
                    "label": args.label,
                    "archived_expedition": finished,
                }, ensure_ascii=False)

            if args.operation == "start_new":
                archived_previous = None
                if self._has_meaningful_trip(self._state["current"]):
                    archived_previous = self._public_trip(self._state["current"], full=False)
                    self._archive_current(label="")
                self._state["current"] = self._empty_trip(
                    started_at=datetime.now(timezone.utc).isoformat(),
                    label=args.label
                )
                self._save()
                return json.dumps({
                    "ok": True,
                    "message": "New expedition started.",
                    "label": args.label,
                    "previous_expedition_archived": archived_previous is not None,
                    "previous_expedition": archived_previous,
                }, ensure_ascii=False)

            return json.dumps({"ok": False, "error": "Unsupported operation."})

    # ---------- compact model context ----------

    def _status_context(self, states):
        with self._lock:
            t = self._state["current"]
            if not self._has_meaningful_trip(t):
                return []
            # Intentionally compact. Mini can call the status action when it needs details.
            bits = [
                f"{t.get('jumps', 0)} jumps",
                f"{len(t.get('systems', []))} systems",
                f"{t.get('bodies_scanned', 0)} bodies scanned",
                f"{t.get('bodies_mapped', 0)} mapped",
                f"{t.get('organic_completed', 0)} completed organics",
            ]
            notable = len(t.get("earthlikes", [])) + len(t.get("water_worlds", [])) + len(t.get("ammonia_worlds", []))
            if notable:
                bits.append(f"{notable} ELW/WW/AW")
            cartography = int(t.get("cartography_sales_cr", 0))
            exobiology = int(t.get("exobiology_sales_cr", 0))
            sold = cartography + exobiology
            if sold:
                bits.append(
                    f"{sold:,} CR actual sales "
                    f"({cartography:,} cartography, {exobiology:,} exobiology)"
                )
            if t.get("_pending_sale"):
                bits.append("sale stop pending archive on next FSD jump")
            return [(
                "TARS Expedition",
                "Current expedition: " + ", ".join(bits) + ". "
                "Use tars_expedition_status for details. This is trip history, not current-system analysis."
            )]
