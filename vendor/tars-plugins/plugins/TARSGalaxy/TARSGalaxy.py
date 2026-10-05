from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Literal
from urllib.parse import quote

import requests
from pydantic import BaseModel, Field

from lib.PluginBase import PluginBase, PluginManifest
from lib.PluginHelper import PluginHelper
from lib.Logger import log


class NearestStationArgs(BaseModel):
    system_name: str = Field(
        default="",
        description="Origin system. Leave blank to use the commander's current system."
    )
    min_landing_pad_size: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Minimum pad size: 1=small, 2=medium, 3=large. Default 2 for a medium ship."
    )


ServiceName = Literal[
    "interstellar-factors",
    "black-market",
    "universal-cartographics",
    "refuel",
    "repair",
    "shipyard",
    "outfitting",
    "search-and-rescue",
]


class NearestServiceArgs(BaseModel):
    service: ServiceName = Field(description="Station service to find.")
    system_name: str = Field(
        default="",
        description="Origin system. Leave blank to use the commander's current system."
    )
    min_landing_pad_size: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Minimum pad size: 1=small, 2=medium, 3=large. Default 2 for a medium ship."
    )
    include_fleet_carriers: bool = Field(
        default=False,
        description="Include player Fleet Carriers. Defaults to false."
    )


class DiagnosticsArgs(BaseModel):
    network_checks: bool = Field(
        default=True,
        description="Also test Ardent and EDData connectivity."
    )


class CommanderInventoryArgs(BaseModel):
    category: Literal["all", "materials", "data", "cargo"] = Field(
        default="all",
        description="EDSM commander inventory category. Use all only for explicit EDSM verification/fallback."
    )
    search: str = Field(
        default="",
        description="Optional material/cargo name filter, for example arsenic or chemical manipulators."
    )


class CommanderStatusArgs(BaseModel):
    include_position: bool = Field(default=True, description="Include EDSM last known position.")
    include_credits: bool = Field(default=True, description="Include EDSM credit balance.")
    include_ranks: bool = Field(default=True, description="Include EDSM commander ranks.")


class TARSGalaxy(PluginBase):
    # COVAS only exposes loaded plugins in the plugin-settings UI when
    # settings_config is not None. This read-only panel makes Galaxy visible
    # without adding unnecessary configuration.
    settings_config = {
        "key": "TARSGalaxy",
        "label": "TARS Galaxy",
        "icon": "wrench",
        "grids": [
            {
                "key": "about",
                "label": "TARS Galaxy",
                "fields": [
                    {
                        "key": "about_text",
                        "label": "Galaxy lookup tools",
                        "type": "paragraph",
                        "readonly": True,
                        "placeholder": None,
                        "content": (
                            "TARS Galaxy is a fallback/verification layer for COVAS:NEXT. "
                            "Normal system, station, service, material and engineering searches should use "
                            "COVAS native Search Agent actions first. Galaxy keeps the deep-space coordinate "
                            "fallback, external-provider diagnostics and optional EDSM Commander verification."
                        ),
                    }
                ],
            },
            {
                "key": "edsm_commander",
                "label": "EDSM Commander",
                "fields": [
                    {
                        "key": "edsm_commander_name",
                        "label": "EDSM Commander Name",
                        "type": "text",
                        "readonly": False,
                        "placeholder": "Your EDSM commander name",
                        "default_value": "",
                    },
                    {
                        "key": "edsm_api_key",
                        "label": "EDSM API Key",
                        "type": "text",
                        "readonly": False,
                        "placeholder": "Paste the NEW EDSM API key here",
                        "default_value": "",
                    },
                    {
                        "key": "edsm_note",
                        "label": "EDSM private commander data",
                        "type": "paragraph",
                        "readonly": True,
                        "placeholder": None,
                        "content": (
                            "Optional. Enables TARS to query your EDSM inventory, encoded data, cargo, "
                            "credits, ranks and EDSM last-known position. The API key stays in COVAS settings "
                            "and is never returned by TARS Galaxy actions."
                        ),
                    },
                ],
            }
        ],
    }

    """
    Focused fallback/verification plugin only.

    Normal system/station/service/material/engineering lookup belongs to COVAS native tools.
    Galaxy registers deep-space fallback, EDSM verification and diagnostics actions plus a location side-effect.
    It does not alter the conversational model, prompt, logbook, or speech behaviour.
    """

    PROVIDERS = (
        ("ardent", "https://api.ardent-insight.com/v2"),
        ("eddata", "https://api.eddata.dev/v2"),
    )
    EDSM_BASE = "https://www.edsm.net/api-v1"
    EDSM_COMMANDER_BASE = "https://www.edsm.net"

    # Neither external API currently documents a generic nearest-any-station
    # route. Querying several common service indexes gives a practical set of
    # permanent-station candidates without pretending the API offers more than it does.
    GENERIC_STATION_SERVICES = (
        "refuel",
        "repair",
        "shipyard",
        "outfitting",
        "universal-cartographics",
    )

    CARRIER_TYPE_MARKERS = (
        "fleet carrier",
        "drake-class carrier",
        "carrier",
    )

    def __init__(self, plugin_manifest: PluginManifest):
        super().__init__(plugin_manifest)
        self._helper: PluginHelper | None = None
        self._current_system: str = ""
        self._current_system_address: int | None = None
        self._current_coords: tuple[float, float, float] | None = None

    def on_chat_start(self, helper: PluginHelper):
        self._helper = helper

        # Prime location from COVAS' already-built projections/history. This fixes
        # the old "must jump once after startup" failure mode.
        self._prime_current_location()
        helper.register_sideeffect(self._observe_event)

        helper.register_status_generator(
            lambda states: [(
                "TARS Galaxy routing rules",
                (
                    "COVAS native tools are the default. Use system_finder, station_finder, body_finder, "
                    "material_finder and blueprint_finder for normal lookup, service, trader, inventory and "
                    "engineering questions. Use TARS Galaxy only as a fallback when a remote/unindexed origin "
                    "cannot be resolved by the native station search, for coordinate-verified deep-space lookup, "
                    "for explicit EDSM Commander verification, or for Galaxy diagnostics. Live COVAS/journal "
                    "state is authoritative over third-party databases. Never infer that a Material Trader stocks "
                    "or sells a named engineering material."
                )
            )]
        )

        helper.register_action(
            name="tars_galaxy_nearest_station",
            description=(
                "FALLBACK ONLY. Find the closest confirmed regular station when COVAS native station_finder "
                "could not resolve a remote/unindexed origin, or when the commander explicitly requests the "
                "Galaxy coordinate fallback. Normal nearest-station searches must use station_finder first. "
                "Galaxy can bridge a journal StarPos through EDSM to a provider-known proxy and recalculate "
                "candidate distances from the commander's real coordinates. Excludes Fleet Carriers. "
                "Do NOT call this action in parallel with tars_galaxy_nearest_service when the commander asked "
                "for a specific service; let the service action answer that request."
            ),
            parameters=NearestStationArgs,
            method=self._action_nearest_station,
            action_type="global",
        )

        helper.register_action(
            name="tars_galaxy_nearest_service",
            description=(
                "FALLBACK ONLY. Find a nearby station service when COVAS native station_finder could not "
                "resolve a remote/unindexed origin, or when an explicit coordinate-verified fallback is wanted. "
                "Normal service searches must use station_finder first. Material Traders and Technology Brokers "
                "are intentionally NOT supported by this Galaxy action because COVAS station_finder can distinguish "
                "Raw/Manufactured/Encoded traders and Human/Guardian brokers while Galaxy's external generic flags cannot. "
                "For a specific service request, call THIS action alone; do not also call tars_galaxy_nearest_station "
                "unless this service lookup fails or the commander separately asks for a generic station. "
                "Third-party service flags may be stale."
            ),
            parameters=NearestServiceArgs,
            method=self._action_nearest_service,
            action_type="global",
        )

        helper.register_action(
            name="tars_galaxy_commander_inventory",
            description=(
                "Explicit EDSM-SYNCED inventory lookup only. Use ONLY when the commander specifically asks "
                "to check/verify EDSM inventory, or when live COVAS material data is unavailable. "
                "For normal questions such as 'how much arsenic do I have?' or 'what materials am I missing?', "
                "prefer COVAS' native live material_finder / blueprint_finder because journal state is authoritative. "
                "This action reports what EDSM has synced; it does NOT locate stations, traders, material sources, "
                "or prove where a material can be obtained. Never ask the commander to paste an API key into chat."
            ),
            parameters=CommanderInventoryArgs,
            method=self._action_commander_inventory,
            action_type="global",
        )

        helper.register_action(
            name="tars_galaxy_commander_status",
            description=(
                "Explicit EDSM verification/fallback only: read EDSM-synced credits, ranks and/or last-known position. "
                "Use live COVAS state for normal current-state questions. Requires EDSM Commander Name and API Key "
                "in plugin settings; live COVAS journal location remains authoritative."
            ),
            parameters=CommanderStatusArgs,
            method=self._action_commander_status,
            action_type="global",
        )

        helper.register_action(
            name="tars_galaxy_diagnostics",
            description=(
                "Run TARS Galaxy diagnostics. Use when asked to test Galaxy, check database connections, "
                "or diagnose location/database lookup problems."
            ),
            parameters=DiagnosticsArgs,
            method=self._action_diagnostics,
            action_type="global",
        )

        log("info", f"TARS Galaxy 1.4.1 started. Current system: {self._current_system or 'unresolved'}")

    def on_chat_stop(self, helper: PluginHelper):
        self._helper = None

    # ------------------------------------------------------------------
    # Current location
    # ------------------------------------------------------------------

    @staticmethod
    def _as_dict(value: Any) -> Any:
        if value is None or isinstance(value, (dict, list, tuple)):
            return value
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            try:
                return model_dump()
            except Exception:
                return value
        return value

    @staticmethod
    def _clean_system_name(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        value = value.strip()
        if not value or value.casefold() in {"unknown", "none", "null"}:
            return ""
        return value

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clean_coords(value: Any) -> tuple[float, float, float] | None:
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            try:
                coords = (float(value[0]), float(value[1]), float(value[2]))
                return coords if all(math.isfinite(v) for v in coords) else None
            except (TypeError, ValueError):
                return None
        if isinstance(value, dict):
            # Ardent uses x/y/z; EDData uses systemX/systemY/systemZ.
            def pick(*keys: str):
                for key in keys:
                    if value.get(key) is not None:
                        return value.get(key)
                return None
            try:
                coords = (
                    float(pick("x", "X", "systemX", "system_x")),
                    float(pick("y", "Y", "systemY", "system_y")),
                    float(pick("z", "Z", "systemZ", "system_z")),
                )
                return coords if all(math.isfinite(v) for v in coords) else None
            except (TypeError, ValueError):
                return None
        return None

    def _find_coords_in_states(self, states: Any) -> tuple[float, float, float] | None:
        candidates: list[tuple[int, tuple[float, float, float]]] = []
        positive_path_words = ("location", "current", "commander", "ship", "status")
        negative_path_words = ("route", "target", "destination", "next", "waypoint")

        def walk(node: Any, path: tuple[str, ...] = ()):
            node = self._as_dict(node)
            if isinstance(node, dict):
                for key, value in node.items():
                    key_s = str(key)
                    nk = key_s.replace("_", "").casefold()
                    path2 = path + (key_s,)
                    path_text = "/".join(path2).casefold()
                    if nk in {"starpos", "systemposition", "systemcoords", "coordinates", "coords"}:
                        coords = self._clean_coords(value)
                        if coords is not None:
                            score = 70
                            if nk == "starpos":
                                score += 60
                            if any(word in path_text for word in positive_path_words):
                                score += 20
                            if any(word in path_text for word in negative_path_words):
                                score -= 150
                            if score > 0:
                                candidates.append((score, coords))
                    nested = self._as_dict(value)
                    if isinstance(nested, (dict, list, tuple)):
                        walk(nested, path2)
            elif isinstance(node, (list, tuple)):
                for idx, item in enumerate(node):
                    walk(item, path + (str(idx),))

        walk(states)
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _find_coords_in_events(self, events: list[Any], system_name: str = "") -> tuple[float, float, float] | None:
        wanted = system_name.casefold() if system_name else ""
        for require_live in (True, False):
            for event in reversed(events or []):
                if getattr(event, "kind", None) != "game":
                    continue
                if require_live and bool(getattr(event, "historic", False)):
                    continue
                content = getattr(event, "content", None)
                if not isinstance(content, dict) or content.get("event") not in ("Location", "FSDJump", "CarrierJump"):
                    continue
                event_system = self._clean_system_name(content.get("StarSystem"))
                if wanted and event_system and event_system.casefold() != wanted:
                    continue
                coords = self._clean_coords(content.get("StarPos"))
                if coords is not None:
                    return coords
        return None

    def _find_location_in_states(self, states: Any) -> tuple[str, int | None]:
        """
        Projection class names are not part of PluginHelper's public contract, so
        search Pydantic/dict state recursively for strongly named current-system fields.
        Route/target/destination branches are heavily penalised to avoid using a waypoint.
        """
        candidates: list[tuple[int, str, int | None]] = []
        positive_path_words = ("location", "current", "commander", "ship", "status")
        negative_path_words = (
            "route", "target", "destination", "next", "mission", "stored",
            "engineer", "search", "result", "waypoint",
        )

        def walk(node: Any, path: tuple[str, ...] = ()):
            node = self._as_dict(node)

            if isinstance(node, dict):
                local_address = None
                for key, value in node.items():
                    nk = str(key).replace("_", "").casefold()
                    if nk in {"systemaddress", "staraddress"}:
                        local_address = self._to_int(value)
                        if local_address is not None:
                            break

                for key, value in node.items():
                    key_s = str(key)
                    nk = key_s.replace("_", "").casefold()
                    path2 = path + (key_s,)
                    path_text = "/".join(path2).casefold()

                    name = self._clean_system_name(value)
                    if name:
                        score = None
                        if nk in {"starsystem", "currentsystem", "currentstarsystem"}:
                            score = 120
                        elif nk in {"systemname", "starsystemname"}:
                            score = 55

                        if score is not None:
                            if any(word in path_text for word in positive_path_words):
                                score += 20
                            if any(word in path_text for word in negative_path_words):
                                score -= 150
                            if score > 0:
                                candidates.append((score, name, local_address))

                    nested = self._as_dict(value)
                    if isinstance(nested, (dict, list, tuple)):
                        walk(nested, path2)

            elif isinstance(node, (list, tuple)):
                for idx, item in enumerate(node):
                    walk(item, path + (str(idx),))

        walk(states)

        if not candidates:
            return "", None

        candidates.sort(key=lambda item: item[0], reverse=True)
        _, system_name, system_address = candidates[0]
        return system_name, system_address

    def _find_location_in_events(self, events: list[Any]) -> tuple[str, int | None]:
        # Location, FSDJump and CarrierJump explicitly identify where the player is.
        for require_live in (True, False):
            for event in reversed(events or []):
                if getattr(event, "kind", None) != "game":
                    continue
                if require_live and bool(getattr(event, "historic", False)):
                    continue
                content = getattr(event, "content", None)
                if not isinstance(content, dict):
                    continue
                if content.get("event") not in ("Location", "FSDJump", "CarrierJump"):
                    continue
                name = self._clean_system_name(content.get("StarSystem"))
                if name:
                    return name, self._to_int(content.get("SystemAddress"))

        for event in reversed(events or []):
            if getattr(event, "kind", None) != "game" or bool(getattr(event, "historic", False)):
                continue
            content = getattr(event, "content", None)
            if not isinstance(content, dict):
                continue
            name = self._clean_system_name(content.get("CurrentSystem"))
            if name:
                return name, self._to_int(content.get("SystemAddress"))

        return "", None

    def _prime_current_location(self):
        if self._helper is None:
            return
        try:
            manager = getattr(self._helper, "_event_manager", None)
            if manager is None:
                return

            events, states = manager.get_current_state()
            name, address = self._find_location_in_states(states)
            if not name:
                name, address = self._find_location_in_events(events)

            coords = self._find_coords_in_events(events, name) or self._find_coords_in_states(states)

            if name:
                changed_system = bool(self._current_system) and name.casefold() != self._current_system.casefold()
                self._current_system = name
                self._current_system_address = address
                if changed_system:
                    self._current_coords = coords
                elif coords is not None:
                    self._current_coords = coords
                log(
                    "info",
                    f"TARS Galaxy resolved startup location: {name} "
                    f"({address or 'no address'}; coords={self._current_coords or 'unknown'})"
                )
            else:
                log("warn", "TARS Galaxy could not resolve startup location from COVAS state/history.")
        except Exception as exc:
            log("warn", f"TARS Galaxy startup location lookup failed: {exc}")

    def _observe_event(self, event: Any, context: dict):
        if getattr(event, "kind", None) != "game":
            return
        content = getattr(event, "content", None)
        if not isinstance(content, dict):
            return

        if content.get("event") in ("Location", "FSDJump", "CarrierJump"):
            name = self._clean_system_name(content.get("StarSystem"))
            if name:
                self._current_system = name
                # These events are authoritative system-boundary updates. Clear
                # metadata when the new event does not provide it rather than
                # accidentally carrying the previous system's address/position.
                self._current_system_address = self._to_int(content.get("SystemAddress"))
                self._current_coords = self._clean_coords(content.get("StarPos"))
                return

        name = self._clean_system_name(content.get("CurrentSystem"))
        if name:
            changed_system = bool(self._current_system) and name.casefold() != self._current_system.casefold()
            address = self._to_int(content.get("SystemAddress"))
            coords = self._clean_coords(content.get("StarPos"))
            self._current_system = name
            if changed_system:
                self._current_system_address = address
                self._current_coords = coords
            else:
                if address is not None:
                    self._current_system_address = address
                if coords is not None:
                    self._current_coords = coords

    def _resolve_origin(self, requested: str, context: dict) -> tuple[str, int | None, str]:
        explicit = self._clean_system_name(requested)
        if explicit:
            if explicit.casefold() == self._current_system.casefold() and self._current_system_address is not None:
                return explicit, self._current_system_address, "explicit_name+current_address"
            return explicit, None, "explicit_name"

        name, address = self._find_location_in_states(context)
        if name:
            changed_system = bool(self._current_system) and name.casefold() != self._current_system.casefold()
            coords = self._find_coords_in_states(context)
            self._current_system = name
            if changed_system:
                self._current_system_address = address
                self._current_coords = coords
            else:
                if address is not None:
                    self._current_system_address = address
                if coords is not None:
                    self._current_coords = coords
            resolved_address = address if address is not None else self._current_system_address
            return name, resolved_address, "action_context"

        self._prime_current_location()
        if self._current_system:
            return self._current_system, self._current_system_address, "covas_state_or_history"

        return "", None, "unresolved"

    # ------------------------------------------------------------------
    # JSON / network
    # ------------------------------------------------------------------

    @staticmethod
    def _json(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _float_or_inf(value: Any) -> float:
        try:
            result = float(value)
            return result if math.isfinite(result) else float("inf")
        except (TypeError, ValueError):
            return float("inf")

    @staticmethod
    def _pad_rank(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            i = int(value)
            return i if i in (1, 2, 3) else None
        text = str(value).strip().upper()
        return {"S": 1, "SMALL": 1, "M": 2, "MEDIUM": 2, "L": 3, "LARGE": 3}.get(text)

    def _provider_url(
        self,
        base: str,
        system_name: str,
        system_address: int | None,
        suffix: str,
    ) -> str:
        if system_address is not None:
            return f"{base}/system/address/{system_address}{suffix}"
        return f"{base}/system/name/{quote(system_name, safe='')}{suffix}"

    def _request_json(
        self,
        provider: str,
        url: str,
        params: dict | None = None,
        timeout: tuple[float, float] = (3.05, 7.0),
    ) -> Any:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": "TARS-Galaxy/1.4.1 COVAS-NEXT"},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

        # EDData documents structured HTTP-200 failure payloads. Handle the same
        # shape for either provider so "upstream down" never becomes "no station".
        if isinstance(data, dict) and str(data.get("status", "")).casefold() in {"error", "unavailable"}:
            msg = data.get("message") or data.get("info") or "provider reported unavailable"
            raise RuntimeError(f"{provider}: {msg}")

        return data

    @staticmethod
    def _distance_ly(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)

    def _origin_coords(self, system_name: str) -> tuple[float, float, float] | None:
        if self._current_system and system_name.casefold() == self._current_system.casefold():
            if self._current_coords is not None:
                return self._current_coords
        return self._edsm_system_coords(system_name)

    def _edsm_system_coords(self, system_name: str) -> tuple[float, float, float] | None:
        if not system_name:
            return None
        try:
            data = self._request_json(
                "edsm",
                f"{self.EDSM_BASE}/system",
                params={"systemName": system_name, "showCoordinates": 1},
                timeout=(3.05, 6.0),
            )
            if isinstance(data, dict):
                return self._clean_coords(data.get("coords"))
        except Exception as exc:
            log("warn", f"TARS Galaxy EDSM coordinate lookup failed for {system_name}: {exc}")
        return None

    def _edsm_nearby_from_coords(
        self,
        coords: tuple[float, float, float],
        radius: int = 100,
    ) -> list[dict]:
        data = self._request_json(
            "edsm",
            f"{self.EDSM_BASE}/sphere-systems",
            params={
                "x": coords[0],
                "y": coords[1],
                "z": coords[2],
                "radius": max(1, min(100, int(radius))),
                "showId": 1,
                "showCoordinates": 1,
            },
            timeout=(3.05, 9.0),
        )
        if not isinstance(data, list):
            return []
        rows = [row for row in data if isinstance(row, dict) and self._clean_system_name(row.get("name"))]
        rows.sort(key=lambda row: self._float_or_inf(row.get("distance")))
        return rows

    def _provider_system_info(
        self,
        provider_name: str,
        base: str,
        system_name: str,
        timeout: tuple[float, float] = (2.0, 4.0),
    ) -> dict:
        data = self._request_json(
            provider_name,
            f"{base}/system/name/{quote(system_name, safe='')}",
            timeout=timeout,
        )
        return data if isinstance(data, dict) else {}

    def _find_proxy_origin(
        self,
        origin_system: str,
        origin_coords: tuple[float, float, float],
    ) -> tuple[dict | None, list[str]]:
        """
        Find a nearby system that a nearest-service provider knows.

        The commander's journal is authoritative for the real XYZ origin. EDSM's
        sphere endpoint accepts raw XYZ coordinates, so it can supply nearby named
        systems even when Ardent/EDData do not know the current system itself.
        """
        errors: list[str] = []
        try:
            candidates = self._edsm_nearby_from_coords(origin_coords, radius=100)
        except Exception as exc:
            return None, [f"edsm sphere lookup: {exc}"]

        candidates = [
            row for row in candidates
            if str(row.get("name") or "").casefold() != origin_system.casefold()
        ][:30]
        if not candidates:
            return None, ["edsm sphere lookup returned no nearby known systems within 100 ly"]

        # Probe candidates concurrently. Picking the closest successful candidate keeps
        # the proxy offset small while avoiding a long serial chain of 404 responses.
        provider_limits = {"ardent": 24, "eddata": 6}
        provider_timeouts = {"ardent": (1.8, 3.5), "eddata": (1.2, 2.5)}

        for provider_name, base in self.PROVIDERS:
            rows = candidates[:provider_limits.get(provider_name, 12)]

            def probe(row: dict):
                candidate = self._clean_system_name(row.get("name"))
                if not candidate:
                    return None, None
                try:
                    info = self._provider_system_info(
                        provider_name, base, candidate,
                        timeout=provider_timeouts.get(provider_name, (2.0, 4.0)),
                    )
                    known_name = self._clean_system_name(info.get("systemName") or info.get("name"))
                    if not known_name:
                        return None, f"{provider_name} proxy {candidate}: unusable system record"
                    coords = self._clean_coords(info) or self._clean_coords(row.get("coords"))
                    distance = (
                        self._distance_ly(origin_coords, coords)
                        if coords is not None
                        else self._float_or_inf(row.get("distance"))
                    )
                    return {
                        "system": known_name,
                        "system_address": self._to_int(info.get("systemAddress")),
                        "coords": coords,
                        "distance_from_origin_ly": round(distance, 2) if math.isfinite(distance) else None,
                        "provider": provider_name,
                    }, None
                except Exception as exc:
                    return None, f"{provider_name} proxy {candidate}: {exc}"

            successes: list[dict] = []
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(rows)))) as pool:
                futures = [pool.submit(probe, row) for row in rows]
                for future in as_completed(futures):
                    try:
                        result, error = future.result()
                        if result:
                            successes.append(result)
                        elif error and len(errors) < 10:
                            errors.append(error)
                    except Exception as exc:
                        if len(errors) < 10:
                            errors.append(f"{provider_name} proxy probe: {exc}")

            if successes:
                successes.sort(key=lambda item: self._float_or_inf(item.get("distance_from_origin_ly")))
                return successes[0], errors

        return None, errors

    def _lookup_destination_coords(self, system_name: str) -> tuple[float, float, float] | None:
        # A nearest-service result came from Ardent/EDData, so those providers are
        # likely to know the destination system. Prefer them before EDSM.
        for provider_name, base in self.PROVIDERS:
            if provider_name == "eddata":
                # EDData was timing out in the reported runtime. Keep it as a fallback
                # with a short timeout so a distance correction cannot stall the answer.
                timeout = (1.5, 2.5)
            else:
                timeout = (2.0, 4.0)
            try:
                info = self._provider_system_info(provider_name, base, system_name, timeout=timeout)
                coords = self._clean_coords(info)
                if coords is not None:
                    return coords
            except Exception:
                pass
        return self._edsm_system_coords(system_name)

    def _recalculate_distances_from_coords(
        self,
        stations: list[dict],
        origin_coords: tuple[float, float, float],
        limit: int = 20,
    ) -> list[dict]:
        """Recalculate proxy-origin distances against the commander's real journal StarPos."""
        candidates = [dict(station) for station in stations[:max(1, limit)]]
        systems = sorted({str(s.get("system") or "") for s in candidates if s.get("system")})
        coords_by_system: dict[str, tuple[float, float, float] | None] = {}

        def resolve(name: str):
            return name, self._lookup_destination_coords(name)

        with ThreadPoolExecutor(max_workers=min(6, max(1, len(systems)))) as pool:
            futures = [pool.submit(resolve, name) for name in systems]
            for future in as_completed(futures):
                try:
                    name, coords = future.result()
                    coords_by_system[name] = coords
                except Exception:
                    pass

        for station in candidates:
            system = str(station.get("system") or "")
            station["proxy_distance_ly"] = station.get("distance_ly")
            coords = coords_by_system.get(system)
            if coords is not None:
                station["distance_ly"] = round(self._distance_ly(origin_coords, coords), 2)
                station["distance_reference"] = "journal StarPos"
                station["distance_exact_from_origin"] = True
            else:
                station["distance_reference"] = "proxy system"
                station["distance_exact_from_origin"] = False

        candidates.sort(
            key=lambda s: (
                0 if s.get("distance_exact_from_origin") else 1,
                self._float_or_inf(s.get("distance_ly")),
                self._float_or_inf(s.get("distance_to_arrival_ls")),
            )
        )
        return candidates

    @staticmethod
    def _rows(data: Any) -> list[dict]:
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            for key in ("stations", "results", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
            if data.get("stationName") or data.get("name"):
                return [data]
        return []

    def _query_provider(
        self,
        provider_name: str,
        base: str,
        system_name: str,
        system_address: int | None,
        suffix: str,
        params: dict | None = None,
    ) -> list[dict]:
        url = self._provider_url(base, system_name, system_address, suffix)
        return self._rows(self._request_json(provider_name, url, params=params))

    def _query_rows_redundant(
        self,
        system_name: str,
        system_address: int | None,
        suffix: str,
        params: dict | None = None,
    ) -> tuple[list[dict], list[str], list[str]]:
        merged: list[dict] = []
        successes: list[str] = []
        errors: list[str] = []

        def one(provider_name: str, base: str):
            return provider_name, self._query_provider(
                provider_name, base, system_name, system_address, suffix, params
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(one, provider_name, base): provider_name
                for provider_name, base in self.PROVIDERS
            }
            for future in as_completed(futures):
                provider_name = futures[future]
                try:
                    name, rows = future.result()
                    successes.append(name)
                    for row in rows:
                        row = dict(row)
                        row["_provider"] = name
                        merged.append(row)
                except Exception as exc:
                    errors.append(f"{provider_name}: {exc}")

        return merged, successes, errors

    # ------------------------------------------------------------------
    # Station normalization
    # ------------------------------------------------------------------

    def _normalize_station(self, row: dict) -> dict | None:
        name = row.get("stationName") or row.get("name")
        system = row.get("systemName") or row.get("system")
        if not isinstance(name, str) or not name.strip():
            return None
        if not isinstance(system, str) or not system.strip():
            return None

        return {
            "station": name.strip(),
            "system": system.strip(),
            "distance_ly": row.get("distance"),
            "distance_to_arrival_ls": (
                row.get("distanceToArrival")
                if row.get("distanceToArrival") is not None
                else row.get("distance_to_arrival")
            ),
            "station_type": row.get("stationType") or row.get("type"),
            "max_landing_pad_size": (
                row.get("maxLandingPadSize")
                if row.get("maxLandingPadSize") is not None
                else row.get("max_landing_pad_size")
            ),
            "carrier_docking_access": row.get("carrierDockingAccess"),
            "service": row.get("service"),
            "updated_at": row.get("updatedAt") or row.get("updated_at"),
            "provider": row.get("_provider"),
        }

    def _carrier_state(self, station: dict) -> Literal["carrier", "regular", "unknown"]:
        if station.get("carrier_docking_access") is not None:
            return "carrier"

        station_type = station.get("station_type")
        if isinstance(station_type, str) and station_type.strip():
            low = station_type.casefold()
            if any(marker in low for marker in self.CARRIER_TYPE_MARKERS):
                return "carrier"
            return "regular"

        # EDDN/API Fleet Carrier station names are commonly their six-character
        # callsign (e.g. ABC-123). Nearest-service responses do not always include
        # stationType, so use this as a conservative secondary carrier marker.
        station_name = str(station.get("station") or "").strip().upper()
        if re.fullmatch(r"[A-Z0-9]{3}-[A-Z0-9]{3}", station_name):
            return "carrier"

        return "unknown"

    @staticmethod
    def _station_key(station: dict) -> tuple[str, str]:
        return (
            str(station.get("system", "")).casefold(),
            str(station.get("station", "")).casefold(),
        )

    def _merge_stations(self, raw_rows: list[dict]) -> list[dict]:
        by_key: dict[tuple[str, str], dict] = {}

        for row in raw_rows:
            station = self._normalize_station(row)
            if station is None:
                continue

            key = self._station_key(station)
            existing = by_key.get(key)
            if existing is None:
                station["providers"] = [station.get("provider")] if station.get("provider") else []
                by_key[key] = station
                continue

            provider = station.get("provider")
            if provider and provider not in existing.setdefault("providers", []):
                existing["providers"].append(provider)

            for field in (
                "distance_ly",
                "distance_to_arrival_ls",
                "station_type",
                "max_landing_pad_size",
                "carrier_docking_access",
                "updated_at",
            ):
                if existing.get(field) is None and station.get(field) is not None:
                    existing[field] = station.get(field)

            services = set(existing.get("services") or [])
            if existing.get("service"):
                services.add(str(existing["service"]))
            if station.get("service"):
                services.add(str(station["service"]))
            if services:
                existing["services"] = sorted(services)

        result = list(by_key.values())
        result.sort(
            key=lambda s: (
                self._float_or_inf(s.get("distance_ly")),
                self._float_or_inf(s.get("distance_to_arrival_ls")),
                str(s.get("system", "")).casefold(),
                str(s.get("station", "")).casefold(),
            )
        )
        return result

    def _lookup_station_metadata(
        self,
        station: dict,
        cache: dict[tuple[str, str], list[dict]],
    ) -> dict:
        system = str(station.get("system") or "")
        provider_preference: list[str] = []
        if station.get("provider"):
            provider_preference.append(str(station["provider"]))
        provider_preference.extend(name for name, _ in self.PROVIDERS if name not in provider_preference)
        provider_map = dict(self.PROVIDERS)

        for provider_name in provider_preference:
            cache_key = (provider_name, system.casefold())
            rows = cache.get(cache_key)
            if rows is None:
                try:
                    rows = self._query_provider(
                        provider_name,
                        provider_map[provider_name],
                        system,
                        None,
                        "/stations",
                        None,
                    )
                    cache[cache_key] = rows
                except Exception:
                    cache[cache_key] = []
                    rows = []

            wanted = str(station.get("station") or "").casefold()
            for row in rows:
                row_name = str(row.get("stationName") or row.get("name") or "").casefold()
                if row_name != wanted:
                    continue

                enriched_row = dict(row)
                enriched_row["_provider"] = provider_name
                enriched = self._normalize_station(enriched_row)
                if enriched:
                    for key, value in enriched.items():
                        if value is not None:
                            station[key] = value
                    if provider_name not in station.setdefault("providers", []):
                        station["providers"].append(provider_name)
                return station

        return station

    def _filter_regular_and_pad(
        self,
        stations: list[dict],
        min_pad: int,
        include_carriers: bool,
        verify_unknown: bool = True,
    ) -> list[dict]:
        station_cache: dict[tuple[str, str], list[dict]] = {}
        accepted: list[dict] = []

        for station in stations[:50]:
            state = self._carrier_state(station)

            if not include_carriers and state == "unknown" and verify_unknown:
                station = self._lookup_station_metadata(station, station_cache)
                state = self._carrier_state(station)

            if not include_carriers:
                # "Regular station" must mean we actually established that it is
                # not a Fleet Carrier. Unknown classification is not confirmation.
                if state != "regular":
                    continue

            station["carrier_status"] = state

            pad = self._pad_rank(station.get("max_landing_pad_size"))
            if pad is not None and pad < min_pad:
                continue
            station["landing_pad_match"] = (
                "confirmed_from_metadata" if pad is not None else "provider_filtered"
            )

            accepted.append(station)
            # Actions only return the best result plus four alternatives. Avoid
            # dozens of metadata calls when nearest-service rows omit stationType.
            if len(accepted) >= 12:
                break

        accepted.sort(
            key=lambda s: (
                self._float_or_inf(s.get("distance_ly")),
                self._float_or_inf(s.get("distance_to_arrival_ls")),
            )
        )
        return accepted

    # ------------------------------------------------------------------
    # External fallback actions
    # ------------------------------------------------------------------

    def _fetch_service_pool(
        self,
        system: str,
        address: int | None,
        service: str,
        min_pad: int,
        preferred_provider: str | None = None,
    ) -> tuple[list[dict], str | None, list[str]]:
        errors: list[str] = []
        providers = list(self.PROVIDERS)
        if preferred_provider:
            providers.sort(key=lambda item: 0 if item[0] == preferred_provider else 1)

        # A provider counts as useful only if it returns parseable station rows.
        # This prevents an HTTP-200 but empty/unrecognised payload from suppressing
        # the fallback provider.
        for provider_name, base in providers:
            try:
                rows = self._query_provider(
                    provider_name,
                    base,
                    system,
                    address,
                    f"/nearest/{service}",
                    {"minLandingPadSize": min_pad},
                )
                if not rows:
                    errors.append(f"{provider_name}: nearest/{service} returned no usable rows")
                    continue
                for row in rows:
                    row["_provider"] = provider_name
                    if not row.get("service"):
                        row["service"] = service
                return rows, provider_name, errors
            except Exception as exc:
                errors.append(f"{provider_name}: {exc}")

        return [], None, errors

    def _collect_generic_station_rows(
        self,
        system: str,
        address: int | None,
        min_pad: int,
        preferred_provider: str | None = None,
    ) -> tuple[list[dict], dict[str, str], list[str]]:
        all_rows: list[dict] = []
        service_sources: dict[str, str] = {}
        errors: list[str] = []

        with ThreadPoolExecutor(max_workers=len(self.GENERIC_STATION_SERVICES)) as pool:
            future_map = {
                pool.submit(
                    self._fetch_service_pool,
                    system,
                    address,
                    service,
                    min_pad,
                    preferred_provider,
                ): service
                for service in self.GENERIC_STATION_SERVICES
            }
            for future in as_completed(future_map):
                service = future_map[future]
                try:
                    rows, provider, provider_errors = future.result()
                    all_rows.extend(rows)
                    errors.extend(provider_errors)
                    if provider:
                        service_sources[service] = provider
                except Exception as exc:
                    errors.append(f"{service}: {exc}")

        return all_rows, service_sources, errors

    def _action_nearest_station(self, args: NearestStationArgs, context: dict) -> str:
        system, address, resolved_by = self._resolve_origin(args.system_name, context)
        if not system:
            return self._json({
                "ok": False,
                "error_code": "CURRENT_SYSTEM_UNKNOWN",
                "message": "TARS Galaxy could not determine the origin system.",
                "assistant_instruction": "Say that the origin system could not be resolved. Do not guess a station."
            })

        min_pad = max(1, min(3, int(args.min_landing_pad_size)))
        all_rows, service_sources, errors = self._collect_generic_station_rows(
            system, address, min_pad
        )

        lookup_mode = "direct_provider_origin"
        origin_coords: tuple[float, float, float] | None = None
        proxy: dict | None = None

        # Exploration fallback: the journal can know a system before community APIs do.
        # In that case use journal StarPos -> EDSM raw-XYZ sphere -> nearby provider-known
        # proxy, then query nearest services from the proxy and correct destination
        # distances back to the real journal coordinates.
        if not service_sources:
            origin_coords = self._origin_coords(system)
            if origin_coords is not None:
                proxy, proxy_errors = self._find_proxy_origin(system, origin_coords)
                errors.extend(proxy_errors)
                if proxy:
                    fallback_rows, fallback_sources, fallback_errors = self._collect_generic_station_rows(
                        str(proxy.get("system") or ""),
                        self._to_int(proxy.get("system_address")),
                        min_pad,
                        preferred_provider=str(proxy.get("provider") or "") or None,
                    )
                    errors.extend(fallback_errors)
                    if fallback_sources:
                        all_rows = fallback_rows
                        service_sources = fallback_sources
                        lookup_mode = "journal_coordinates_via_proxy"

        if not service_sources:
            return self._json({
                "ok": False,
                "error_code": "UPSTREAM_UNAVAILABLE",
                "origin_system": system,
                "origin_system_address": address,
                "origin_coordinates": list(origin_coords) if origin_coords is not None else None,
                "resolved_by": resolved_by,
                "coordinate_fallback_attempted": origin_coords is not None,
                "proxy_origin": proxy,
                "provider_errors": errors[:30],
                "message": "Direct lookup failed and no usable coordinate-proxy station lookup could be completed.",
                "assistant_instruction": (
                    "Say that the external station lookup is unavailable. "
                    "Do NOT say there is no station, and do NOT invent a nearby system."
                )
            })

        stations = self._merge_stations(all_rows)
        if lookup_mode == "journal_coordinates_via_proxy" and origin_coords is not None:
            # Re-rank a generous set using the commander's real XYZ, not the proxy's
            # provider distance. This is what makes a 700+ ly result meaningful.
            stations = self._recalculate_distances_from_coords(stations, origin_coords, limit=30)

        regular = self._filter_regular_and_pad(
            stations,
            min_pad=min_pad,
            include_carriers=False,
            verify_unknown=True,
        )

        if not regular:
            return self._json({
                "ok": False,
                "error_code": "NO_CONFIRMED_RESULT",
                "origin_system": system,
                "origin_system_address": address,
                "origin_coordinates": list(origin_coords) if origin_coords is not None else None,
                "resolved_by": resolved_by,
                "lookup_mode": lookup_mode,
                "proxy_origin": proxy,
                "service_indexes_queried": list(self.GENERIC_STATION_SERVICES),
                "successful_service_sources": service_sources,
                "provider_errors": errors[:30],
                "message": "The available service indexes returned no confirmed regular station matching the pad requirement.",
                "assistant_instruction": (
                    "Say that no regular station could be confirmed from the available database results. "
                    "This is not proof that no station exists."
                )
            })

        best = regular[0]
        return self._json({
            "ok": True,
            "routing": "fallback_after_covas_native_station_finder",
            "origin_system": system,
            "origin_system_address": address,
            "origin_coordinates": list(origin_coords) if origin_coords is not None else None,
            "resolved_by": resolved_by,
            "lookup_mode": lookup_mode,
            "proxy_origin": proxy,
            "source_method": (
                "Nearest service indexes (refuel, repair, shipyard, outfitting, universal cartographics). "
                "If the provider does not know the journal origin, EDSM raw-XYZ sphere lookup supplies a "
                "nearby provider-known proxy and candidate distances are corrected against journal StarPos."
            ),
            "best": best,
            "alternatives": regular[1:5],
            "service_indexes_queried": list(self.GENERIC_STATION_SERVICES),
            "successful_service_sources": service_sources,
            "provider_errors": errors[:30],
            "caveat": (
                "Neither external provider documents a generic nearest-any-station endpoint. "
                "This is the closest confirmed regular station among the returned common-service candidates."
            ),
            "assistant_instruction": (
                "Answer with the returned station, system and distance. "
                "If distance_exact_from_origin is true, the distance was recalculated from the commander's "
                "journal StarPos. If false during proxy mode, call the distance approximate and mention the proxy offset. "
                "Do not claim stronger certainty than the caveat permits."
            )
        })

    def _action_nearest_service(self, args: NearestServiceArgs, context: dict) -> str:
        if str(getattr(args, "service", "") or "").casefold() in {"material-trader", "technology-broker"}:
            return self._json({
                "ok": False,
                "error_code": "USE_COVAS_NATIVE_STATION_FINDER",
                "service": getattr(args, "service", None),
                "message": "This service requires COVAS native station_finder rather than Galaxy.",
                "assistant_instruction": (
                    "Use COVAS station_finder. Material Traders must preserve Raw/Manufactured/Encoded subtype; "
                    "Technology Brokers must preserve Human/Guardian subtype. Do not answer from a generic Galaxy flag."
                )
            })

        system, address, resolved_by = self._resolve_origin(args.system_name, context)
        if not system:
            return self._json({
                "ok": False,
                "error_code": "CURRENT_SYSTEM_UNKNOWN",
                "message": "TARS Galaxy could not determine the origin system.",
                "assistant_instruction": "Say that the origin system could not be resolved. Do not guess."
            })

        min_pad = max(1, min(3, int(args.min_landing_pad_size)))
        rows, successes, errors = self._query_rows_redundant(
            system,
            address,
            f"/nearest/{args.service}",
            {"minLandingPadSize": min_pad},
        )

        lookup_mode = "direct_provider_origin"
        origin_coords: tuple[float, float, float] | None = None
        proxy: dict | None = None

        if not successes:
            origin_coords = self._origin_coords(system)
            if origin_coords is not None:
                proxy, proxy_errors = self._find_proxy_origin(system, origin_coords)
                errors.extend(proxy_errors)
                if proxy:
                    fallback_rows, provider, fallback_errors = self._fetch_service_pool(
                        str(proxy.get("system") or ""),
                        self._to_int(proxy.get("system_address")),
                        args.service,
                        min_pad,
                        preferred_provider=str(proxy.get("provider") or "") or None,
                    )
                    errors.extend(fallback_errors)
                    if provider:
                        rows = fallback_rows
                        successes = [provider]
                        lookup_mode = "journal_coordinates_via_proxy"

        if not successes:
            return self._json({
                "ok": False,
                "error_code": "UPSTREAM_UNAVAILABLE",
                "origin_system": system,
                "origin_coordinates": list(origin_coords) if origin_coords is not None else None,
                "service": args.service,
                "coordinate_fallback_attempted": origin_coords is not None,
                "proxy_origin": proxy,
                "provider_errors": errors[:30],
                "message": "Direct service lookup failed and the coordinate-proxy fallback could not complete.",
                "assistant_instruction": (
                    "Say the service lookup is unavailable. "
                    "Do NOT interpret provider failure as no station existing."
                )
            })

        stations = self._merge_stations(rows)
        if lookup_mode == "journal_coordinates_via_proxy" and origin_coords is not None:
            stations = self._recalculate_distances_from_coords(stations, origin_coords, limit=20)

        filtered = self._filter_regular_and_pad(
            stations,
            min_pad=min_pad,
            include_carriers=bool(args.include_fleet_carriers),
            verify_unknown=not bool(args.include_fleet_carriers),
        )

        if not filtered:
            return self._json({
                "ok": False,
                "error_code": "NO_CONFIRMED_RESULT",
                "origin_system": system,
                "origin_coordinates": list(origin_coords) if origin_coords is not None else None,
                "service": args.service,
                "lookup_mode": lookup_mode,
                "proxy_origin": proxy,
                "successful_providers": successes,
                "provider_errors": errors[:30],
                "message": "No matching station was confirmed by the available provider results.",
                "assistant_instruction": "Say no matching result was confirmed. Do not claim the service does not exist."
            })

        instruction = (
            "Use the returned result as a third-party database report, not in-game confirmation. "
            "If distance_exact_from_origin is true, the distance was recalculated from journal StarPos; "
            "otherwise a proxy-mode distance is approximate. Station service data may be stale."
        )
        if args.service == "material-trader":
            instruction += (
                " CRITICAL: this result is only a GENERIC Material Trader flag. It does not establish trader type "
                "(Raw, Manufactured, or Encoded), and it never means the station stocks or sells a named material. "
                "Do not say 'material trader with arsenic/chemical manipulators/etc'. For a named engineering material, "
                "use COVAS material_finder to determine its category/source, then COVAS/Search Agent station_finder "
                "with the matching material_trader type."
            )

        return self._json({
            "ok": True,
            "routing": "fallback_after_covas_native_station_finder",
            "origin_system": system,
            "origin_system_address": address,
            "origin_coordinates": list(origin_coords) if origin_coords is not None else None,
            "resolved_by": resolved_by,
            "service": args.service,
            "lookup_mode": lookup_mode,
            "proxy_origin": proxy,
            "successful_providers": successes,
            "provider_errors": errors[:30],
            "best": filtered[0],
            "alternatives": filtered[1:5],
            "data_confidence": "third_party_reported_not_in_game_confirmed",
            "assistant_instruction": instruction
        })

    def _settings_snapshot(self) -> dict[str, Any]:
        """Return plugin settings in a tolerant flat form without exposing secrets.

        COVAS versions have represented plugin settings as a plain mapping, a
        pydantic-like object, or nested grid/value structures.  Do not assume
        one concrete representation.
        """
        raw = getattr(self, "settings", None)
        if raw is None:
            return {}

        if hasattr(raw, "model_dump"):
            try:
                raw = raw.model_dump()
            except Exception:
                pass
        elif hasattr(raw, "dict") and not isinstance(raw, dict):
            try:
                raw = raw.dict()
            except Exception:
                pass

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return {}

        found: dict[str, Any] = {}

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                # Common COVAS serialized setting shape: {key: ..., value/default_value: ...}
                key = value.get("key")
                if isinstance(key, str):
                    if "value" in value:
                        found[key] = value.get("value")
                    elif "current_value" in value:
                        found[key] = value.get("current_value")
                for k, v in value.items():
                    if isinstance(k, str) and k in {"edsm_commander_name", "edsm_api_key"}:
                        found[k] = v
                    if isinstance(v, (dict, list, tuple)):
                        walk(v)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    walk(item)

        if isinstance(raw, dict):
            # Normal/current COVAS path documented by PluginBase: self.settings.get(...).
            found.update(raw)
        walk(raw)
        return found

    def _edsm_credentials(self) -> tuple[str, str]:
        settings = self._settings_snapshot()
        commander = str(settings.get("edsm_commander_name", "") or "").strip()
        api_key = str(settings.get("edsm_api_key", "") or "").strip()
        return commander, api_key

    def _edsm_config_diagnostic(self) -> dict[str, Any]:
        settings = self._settings_snapshot()
        commander, api_key = self._edsm_credentials()
        # Never return values; only harmless metadata useful for debugging.
        return {
            "commander_name_configured": bool(commander),
            "api_key_configured": bool(api_key),
            "visible_setting_keys": sorted(
                str(k) for k in settings.keys()
                if str(k) != "edsm_api_key" and "key" not in str(k).lower()
            )[:30],
        }

    def _edsm_private_get(self, path: str, extra: dict[str, Any] | None = None) -> Any:
        commander, api_key = self._edsm_credentials()
        if not commander or not api_key:
            diag = self._edsm_config_diagnostic()
            missing = []
            if not commander:
                missing.append("commander name")
            if not api_key:
                missing.append("API key")
            raise RuntimeError(
                "EDSM Commander integration cannot read the configured " + " and ".join(missing) +
                ". Open TARS Galaxy plugin settings, save the fields, then restart the COVAS chat. "
                f"Credential visibility: commander={diag['commander_name_configured']}, api_key={diag['api_key_configured']}. "
                "Never paste an API key into chat."
            )
        params: dict[str, Any] = {"commanderName": commander, "apiKey": api_key}
        if extra:
            params.update(extra)
        try:
            response = requests.get(
                f"{self.EDSM_COMMANDER_BASE}{path}",
                params=params,
                timeout=(3.0, 8.0),
                headers={"User-Agent": "TARS-Galaxy/1.4.1 COVAS-NEXT"},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            # requests HTTP errors commonly embed the full request URL. Because
            # EDSM authenticates via query parameters, returning/logging str(exc)
            # can expose commanderName/apiKey. Surface only non-secret metadata.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            kind = type(exc).__name__
            detail = f"HTTP {status}" if status is not None else kind
            raise RuntimeError(f"EDSM Commander request failed ({detail}).") from None

        try:
            data = response.json()
        except ValueError:
            raise RuntimeError("EDSM Commander returned an invalid JSON response.") from None

        if isinstance(data, dict) and data.get("msgnum") not in (None, 100):
            # Do not echo provider text here: authentication failures may include
            # request details. The numeric EDSM error code is enough for diagnosis.
            raise RuntimeError(f"EDSM returned error code {data.get('msgnum')}.")
        return data

    def _action_commander_inventory(self, args: CommanderInventoryArgs, context: dict) -> str:
        categories = [args.category] if args.category != "all" else ["materials", "data", "cargo"]
        result: dict[str, Any] = {"source": "EDSM private Commander API", "categories": {}}
        search = (args.search or "").strip().lower()
        for category in categories:
            try:
                data = self._edsm_private_get(
                    "/api-commander-v1/get-materials", {"type": category}
                )
                entries = data.get(category, []) if isinstance(data, dict) else []
                if search:
                    entries = [
                        x for x in entries
                        if search in str(x.get("name", "")).lower()
                        or search in str(x.get("type", "")).lower()
                    ]
                result["categories"][category] = entries
            except Exception as exc:
                result["categories"][category] = {"error": str(exc)}
        result["assistant_instruction"] = (
            "This is EDSM-synced inventory only. Prefer COVAS live journal material state whenever available. "
            "This result answers what EDSM currently records; it does NOT locate material sources or traders. "
            "Never infer that a station stocks a named engineering material from this result. "
            "Never reveal or repeat the configured API key, and never ask the commander to paste it into chat."
        )
        return self._json(result)

    def _action_commander_status(self, args: CommanderStatusArgs, context: dict) -> str:
        result: dict[str, Any] = {"source": "EDSM private Commander API"}
        if args.include_credits:
            try:
                result["credits"] = self._edsm_private_get("/api-commander-v1/get-credits").get("credits", [])
            except Exception as exc:
                result["credits"] = {"error": str(exc)}
        if args.include_ranks:
            try:
                ranks = self._edsm_private_get("/api-commander-v1/get-ranks")
                result["ranks"] = {
                    "ranks": ranks.get("ranks", {}),
                    "progress": ranks.get("progress", {}),
                    "ranksVerbose": ranks.get("ranksVerbose", {}),
                }
            except Exception as exc:
                result["ranks"] = {"error": str(exc)}
        if args.include_position:
            try:
                result["edsm_last_position"] = self._edsm_private_get(
                    "/api-logs-v1/get-position", {"showCoordinates": 1, "showId": 1}
                )
            except Exception as exc:
                result["edsm_last_position"] = {"error": str(exc)}
        result["live_covas_location"] = {
            "system": self._current_system or None,
            "system_address": self._current_system_address,
            "coordinates": list(self._current_coords) if self._current_coords else None,
        }
        result["assistant_instruction"] = (
            "For current location, prefer live COVAS journal state over EDSM last position. "
            "EDSM private data can lag until the user's EDSM sync client uploads new journal events. Never reveal the API key."
        )
        return self._json(result)

    def _action_diagnostics(self, args: DiagnosticsArgs, context: dict) -> str:
        system, address, resolved_by = self._resolve_origin("", context)
        coords = self._origin_coords(system) if system else None

        report: dict[str, Any] = {
            "plugin": "TARS Galaxy",
            "version": "1.4.1",
            "scope": "deep-space external fallback, EDSM verification and provider diagnostics",
            "current_location": {
                "system": system or None,
                "system_address": address,
                "coordinates": list(coords) if coords is not None else None,
                "resolved_by": resolved_by,
                "ok": bool(system),
            },
            "covas": {
                "event_manager_available": bool(
                    self._helper and getattr(self._helper, "_event_manager", None)
                ),
                "native_first_policy": True,
                "normal_lookup_actions": [
                    "system_finder",
                    "station_finder",
                    "body_finder",
                    "material_finder",
                    "blueprint_finder",
                ],
            },
            "providers": {},
            "coordinate_fallback": {
                "journal_coordinates_available": coords is not None,
                "edsm_raw_xyz_lookup_ok": None,
            },
            "edsm_commander": {
                "configured": all(bool(x) for x in self._edsm_credentials()),
                "credentials_exposed": False,
            },
        }

        if args.network_checks:
            def check(provider_name: str, base: str):
                result: dict[str, Any] = {
                    "version_ok": False,
                    "origin_known": None,
                }
                try:
                    data = self._request_json(
                        provider_name,
                        f"{base}/version",
                        timeout=(2.0, 4.0),
                    )
                    result["version_ok"] = True
                    result["version"] = data.get("version") if isinstance(data, dict) else data
                except Exception as exc:
                    result["version_error"] = str(exc)
                    result["ok"] = False
                    return provider_name, result

                if system:
                    try:
                        origin_url = self._provider_url(base, system, address, "")
                        origin_data = self._request_json(
                            provider_name, origin_url, timeout=(1.8, 3.5)
                        )
                        result["origin_known"] = isinstance(origin_data, dict) and bool(origin_data)
                        if isinstance(origin_data, dict):
                            result["origin_record_name"] = (
                                origin_data.get("systemName") or origin_data.get("name")
                            )
                    except Exception as exc:
                        result["origin_known"] = False
                        result["origin_error"] = str(exc)

                result["ok"] = bool(result["version_ok"])
                return provider_name, result

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(check, provider_name, base)
                    for provider_name, base in self.PROVIDERS
                ]
                for future in as_completed(futures):
                    name, result = future.result()
                    report["providers"][name] = result

            if coords is not None:
                try:
                    nearby = self._edsm_nearby_from_coords(coords, radius=25)
                    report["coordinate_fallback"].update({
                        "edsm_raw_xyz_lookup_ok": True,
                        "nearby_known_systems_within_25ly": len(nearby),
                        "sample_system": nearby[0].get("name") if nearby else None,
                    })
                except Exception as exc:
                    report["coordinate_fallback"].update({
                        "edsm_raw_xyz_lookup_ok": False,
                        "edsm_error": str(exc),
                    })

        provider_ok = (
            not args.network_checks
            or any(x.get("version_ok") for x in report["providers"].values())
        )
        direct_origin_ok = any(
            x.get("origin_known") is True for x in report["providers"].values()
        )
        coordinate_fallback_ready = bool(
            coords is not None
            and (
                not args.network_checks
                or report["coordinate_fallback"].get("edsm_raw_xyz_lookup_ok") is True
            )
            and provider_ok
        )

        report["nearest_lookup_route"] = {
            "direct_origin_available": direct_origin_ok,
            "coordinate_proxy_available": coordinate_fallback_ready,
        }
        report["ok"] = bool(
            report["current_location"]["ok"]
            and provider_ok
            and (direct_origin_ok or coordinate_fallback_ready or not args.network_checks)
        )
        report["assistant_instruction"] = (
            "Normal searches should stay on COVAS native finder actions. Report provider connectivity separately from "
            "whether each provider knows the current origin. If the provider does not know the origin but journal "
            "coordinates plus EDSM raw-XYZ lookup are available, say that Galaxy's coordinate-proxy fallback is ready. "
            "Provider failure or 404 means missing external data, not proof that no station exists."
        )

        return self._json(report)

