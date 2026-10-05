from __future__ import annotations

import json
import math
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, override

from pydantic import BaseModel, Field

from lib.PluginBase import PluginBase, PluginManifest
from lib.PluginHelper import PluginHelper, PluginEvent
from lib.Logger import log


class NavigatorStatusArgs(BaseModel):
    detail: Literal["brief", "full"] = Field(
        default="brief",
        description="brief for normal route questions; full only when the commander asks for detailed journey statistics."
    )


class NavigatorControlArgs(BaseModel):
    operation: Literal["set_destination", "clear_destination", "reset_leg"] = Field(
        description=(
            "Journey-state control. Use set_destination only when the commander explicitly states a destination "
            "or asks TARS to track a trip to one. clear_destination/reset_leg require explicit intent."
        )
    )
    destination: str = Field(
        default="",
        description="Destination system name when operation is set_destination."
    )


class TARSNavigator(PluginBase):
    """
    TARS Navigator 1.1.4

    Lightweight journey awareness:
      - watches FSDJump, Location, NavRoute, NavRouteClear, StartJump, FuelScoop
      - persists current leg across COVAS restarts
      - tracks actual distance/jumps since leg start
      - tracks destination and route progress when journal route data is available
      - exposes only status + explicit control

    It does not plan routes or search stations. Native COVAS/Elite navigation owns that.
    """

    settings_config = {
        "key": "TARSNavigator",
        "label": "TARS Navigator",
        "icon": "navigation",
        "grids": [{
            "key": "about",
            "label": "Journey Awareness",
            "fields": [{
                "key": "about_text",
                "label": "What this plugin does",
                "type": "paragraph",
                "readonly": True,
                "placeholder": None,
                "content": (
                    "Tracks the current journey: destination, route progress when Elite supplies NavRoute data, "
                    "actual jumps and distance travelled, fuel scooping, recent progress, and selective proactive journey milestones. "
                    "It does not replace Elite's route planner or COVAS navigation actions."
                ),
            }],
        }],
    }

    def __init__(self, plugin_manifest: PluginManifest):
        super().__init__(plugin_manifest)
        self._manifest = plugin_manifest
        self._helper: PluginHelper | None = None
        self._session_id: int = 0
        self._lock = threading.RLock()
        self._state_path: Path | None = None
        self._state = self._empty_state()

    @override
    def on_chat_start(self, helper: PluginHelper):
        self._helper = helper
        self._session_id += 1
        data_dir = Path(helper.get_plugin_data_path(self._manifest))
        data_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = data_dir / "navigator.json"
        self._load()

        helper.register_sideeffect(self._observe_event)

        helper.register_event(
            name="TARSNavigatorTarget",
            should_reply_check=self._should_reply_to_journey_target,
            prompt_generator=self._prompt_journey_target,
        )

        helper.register_action(
            name="tars_navigator_status",
            description=(
                "Get CURRENT JOURNEY progress: current system, destination if known, route jumps remaining if Elite "
                "has supplied a NavRoute, jumps and actual distance travelled on this leg, average jump distance, "
                "fuel-scoop count, and recent route progress. Use for 'how far have we gone?', 'how is the trip going?', "
                "'how many jumps have we done?', 'how many jumps left?', or 'where are we heading?'. "
                "Do not use for station/service searches or exploration-body analysis."
            ),
            parameters=NavigatorStatusArgs,
            method=self._action_status,
            action_type="global",
        )

        helper.register_action(
            name="tars_navigator_control",
            description=(
                "Explicitly manage TARS journey tracking. Use ONLY when the commander asks to track/set a destination, "
                "clear the destination, or reset the current journey leg. This does not plot an Elite route."
            ),
            parameters=NavigatorControlArgs,
            method=self._action_control,
            action_type="global",
        )

        helper.register_status_generator(self._status_context)
        log("info", "TARS Navigator 1.1.4 started.")

    @override
    def on_chat_stop(self, helper: PluginHelper):
        self._save()
        self._session_id += 1
        self._helper = None

    def _empty_state(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "leg_started_at": None,
            "start_system": None,
            "current_system": None,
            "current_starpos": None,
            "destination": None,
            "destination_source": None,
            "route": [],
            "route_initial_count": None,
            "route_updated_at": None,
            "jumps_this_leg": 0,
            "distance_this_leg_ly": 0.0,
            "last_jump_ly": None,
            "recent_jumps_ly": [],
            "fuel_scoops": 0,
            "fuel_scooped_tonnes": 0.0,
            "last_fuel_level": None,
            "last_event_key": None,
            "arrived": False,
            "journey_callouts": [],
            "last_route_destination": None,
            "last_route_initial_count": None,
            # NavRouteClear commonly arrives as Elite consumes the final leg.
            # Keep the former destination privately for one subsequent jump so
            # arrival detection survives without presenting a cleared route live.
            "cleared_route_destination": None,
            "cleared_route_at": None,
        }

    def _load(self):
        if not self._state_path or not self._state_path.exists():
            return
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("schema") == 1:
                base = self._empty_state()
                base.update(raw)
                self._state = base
        except Exception as exc:
            log("warning", f"TARS Navigator could not load state: {exc}")

    def _save(self):
        if not self._state_path:
            return
        try:
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._state_path)
        except Exception as exc:
            log("warning", f"TARS Navigator could not save state: {exc}")

    def _should_reply_to_journey_target(self, event: PluginEvent) -> bool:
        data = event.plugin_event_content if isinstance(event.plugin_event_content, dict) else {}
        guard = data.get("_guard") if isinstance(data.get("_guard"), dict) else {}
        if self._helper is None or guard.get("session_id") != self._session_id:
            return False
        triggered_at = guard.get("triggered_at")
        if not isinstance(triggered_at, (int, float)):
            return False
        age = time.time() - triggered_at
        if age < 0 or age > 60:
            return False

        guarded_destination = str(guard.get("destination") or "").strip()
        current_destination = str(self._state.get("destination") or "").strip()
        if guarded_destination and current_destination and not self._same_system(guarded_destination, current_destination):
            return False

        guarded_system = str(guard.get("current_system") or "").strip()
        current_system = str(self._state.get("current_system") or "").strip()
        if guarded_system and current_system and not self._same_system(guarded_system, current_system):
            return False
        return True

    def _guarded_journey_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload)
        data["_guard"] = {
            "session_id": self._session_id,
            "triggered_at": time.time(),
            "destination": self._state.get("destination"),
            "current_system": self._state.get("current_system"),
        }
        return data

    def _prompt_journey_target(self, event: PluginEvent) -> str:
        raw = event.plugin_event_content if isinstance(event.plugin_event_content, dict) else {}
        data = {k: v for k, v in raw.items() if k != "_guard"}
        kind = data.get("callout_kind")
        return (
            "TARS Navigator has identified a meaningful journey milestone from live Elite route/jump data. "
            "Give at most one short natural TARS-style line. Be dry, pragmatic and occasionally funny when earned. "
            "Do not sound like a satnav and do not recite every field. Never invent route length, jump count, destination, "
            "distance or arrival. If route data is absent, do not estimate it. Avoid generic cosmic philosophy. "
            "For progress milestones, mention the milestone or useful remaining route context without repeating the same template. "
            "For final_jumps/final_jump, a brief arrival-oriented remark is appropriate. For arrival, acknowledge reaching the "
            "destination without claiming docking or mission completion. For route_changed, state the meaningful change without "
            "complaining unless the facts support it. Use only supplied facts. "
            f"Milestone kind: {kind}. Journey facts: {json.dumps(data, ensure_ascii=False)}"
        )

    def _callout_seen(self, key: str) -> bool:
        return key in set(self._state.get("journey_callouts") or [])

    def _mark_callout(self, key: str):
        items = list(self._state.get("journey_callouts") or [])
        if key not in items:
            items.append(key)
        self._state["journey_callouts"] = items[-40:]

    def _dispatch_journey(self, kind: str, payload: dict[str, Any], key: str):
        if self._helper is None or self._callout_seen(key):
            return
        data = dict(payload)
        data["callout_kind"] = kind
        try:
            self._helper.dispatch_event(PluginEvent(
                plugin_event_name="TARSNavigatorTarget",
                plugin_event_content=self._guarded_journey_data(data),
            ))
            self._mark_callout(key)
            log("info", f"TARS Navigator milestone dispatched: {kind}")
        except Exception as exc:
            log("warning", f"TARS Navigator milestone dispatch failed: {exc}")

    def _journey_snapshot(self) -> dict[str, Any]:
        s = self._public_state(full=False)
        return {
            "current_system": s.get("current_system"),
            "destination": s.get("destination"),
            "jumps_completed_this_leg": s.get("jumps_this_leg"),
            "distance_travelled_this_leg_ly": s.get("distance_this_leg_ly"),
            "route_jumps_remaining": s.get("route_jumps_remaining"),
            "route_progress_percent": s.get("route_progress_percent"),
            "straight_line_distance_remaining_ly": s.get("straight_line_distance_to_route_destination_ly"),
            "last_jump_ly": s.get("last_jump_ly"),
        }

    def _maybe_progress_callout(self):
        remaining = self._route_jumps_remaining()
        initial = self._state.get("route_initial_count")
        if not isinstance(initial, int) or initial < 4 or not isinstance(remaining, int):
            return

        # Arrival is handled separately. Final-jump states are deliberately exact.
        snap = self._journey_snapshot()
        if remaining == 1:
            self._dispatch_journey("final_jump", snap, "route:final_jump")
            return
        if remaining in (2, 3):
            self._dispatch_journey("final_jumps", snap, f"route:remaining:{remaining}")
            return

        done = max(0, initial - remaining)
        pct = (done / initial) * 100.0 if initial else 0.0
        # Broad buckets prevent satnav-style narration. Each can fire once per leg.
        for threshold in (75, 50, 25):
            if pct >= threshold:
                self._dispatch_journey(
                    "progress",
                    {**snap, "milestone_percent": threshold},
                    f"route:progress:{threshold}",
                )
                break

    def _maybe_arrival_callout(self, system: str | None):
        dest = self._state.get("destination")
        if dest and system and self._same_system(dest, system):
            self._dispatch_journey(
                "arrival",
                self._journey_snapshot(),
                f"arrival:{str(dest).casefold()}",
            )

    def _observe_event(self, event, context):
        if getattr(event, "kind", "") != "game" or getattr(event, "historic", False):
            return
        content = getattr(event, "content", {}) or {}
        if not isinstance(content, dict):
            return
        with self._lock:
            self._process(content)
            self._save()

    def _event_key(self, e: dict[str, Any]) -> str:
        return "|".join(str(e.get(k, "")) for k in ("timestamp", "event", "StarSystem", "JumpDist"))

    def _process(self, e: dict[str, Any]):
        name = str(e.get("event", "") or "")
        if not name:
            return
        key = self._event_key(e)
        if key and key == self._state.get("last_event_key"):
            return
        self._state["last_event_key"] = key

        if name in ("Location", "CarrierJump"):
            system = e.get("StarSystem")
            if system:
                self._state["current_system"] = system
            if self._valid_pos(e.get("StarPos")):
                self._state["current_starpos"] = list(e["StarPos"])

        elif name == "FSDJump":
            system = e.get("StarSystem")
            if not self._state.get("leg_started_at"):
                self._state["leg_started_at"] = e.get("timestamp") or datetime.now(timezone.utc).isoformat()
                self._state["start_system"] = self._state.get("current_system") or system

            if system:
                self._state["current_system"] = system
            if self._valid_pos(e.get("StarPos")):
                self._state["current_starpos"] = list(e["StarPos"])

            d = self._number(e.get("JumpDist"))
            self._state["jumps_this_leg"] += 1
            self._state["distance_this_leg_ly"] += d
            self._state["last_jump_ly"] = round(d, 3) if d else None
            if d:
                recent = list(self._state.get("recent_jumps_ly") or [])
                recent.append(round(d, 3))
                self._state["recent_jumps_ly"] = recent[-12:]

            fuel = e.get("FuelLevel")
            if fuel is not None:
                self._state["last_fuel_level"] = self._number(fuel)

            self._advance_route(system)

            dest = self._state.get("destination")
            if not dest:
                cleared_at = self._state.get("cleared_route_at")
                try:
                    recently_cleared = (
                        cleared_at is not None
                        and 0.0 <= time.time() - float(cleared_at) <= 900.0
                    )
                except (TypeError, ValueError):
                    recently_cleared = False
                if recently_cleared:
                    dest = self._state.get("cleared_route_destination")
            if dest and system and self._same_system(dest, system):
                self._state["destination"] = dest
                self._state["destination_source"] = "elite_navroute_arrival"
                self._state["arrived"] = True
                self._state["route"] = []
                self._maybe_arrival_callout(system)
            else:
                self._maybe_progress_callout()
            self._state["cleared_route_destination"] = None
            self._state["cleared_route_at"] = None

        elif name == "FuelScoop":
            self._state["fuel_scoops"] += 1
            self._state["fuel_scooped_tonnes"] += self._number(e.get("Scooped"))
            if e.get("Total") is not None:
                self._state["last_fuel_level"] = self._number(e.get("Total"))

        elif name == "NavRoute":
            route = self._normalise_route(e.get("Route"))
            if route:
                old_dest = self._state.get("destination")
                old_remaining = self._route_jumps_remaining()
                old_initial = self._state.get("route_initial_count")
                old_arrived = bool(self._state.get("arrived"))
                final = route[-1].get("StarSystem")
                first = route[0].get("StarSystem")
                if first and not self._state.get("current_system"):
                    self._state["current_system"] = first
                new_remaining = self._route_jumps_for(route)

                destination_changed = bool(
                    final and old_dest and not self._same_system(final, old_dest)
                )
                same_destination = bool(
                    final and old_dest and self._same_system(final, old_dest)
                )
                same_destination_reroute = bool(
                    same_destination
                    and isinstance(old_remaining, int)
                    and isinstance(new_remaining, int)
                    and abs(new_remaining - old_remaining) >= 3
                )

                # Re-emitted NavRoute data for the SAME destination is a route
                # refresh, not a fresh journey. Preserve already-completed route
                # work instead of resetting progress to zero. If Elite genuinely
                # reroutes the same destination, retain completed jumps and adjust
                # the total route basis to completed + newly remaining jumps.
                if same_destination and not old_arrived:
                    completed = (
                        max(0, old_initial - old_remaining)
                        if isinstance(old_initial, int) and isinstance(old_remaining, int)
                        else 0
                    )
                    route_initial_count = (
                        completed + new_remaining
                        if isinstance(new_remaining, int)
                        else None
                    )
                else:
                    route_initial_count = new_remaining

                if not same_destination or old_arrived:
                    self._state["journey_callouts"] = []
                self._state["route"] = route
                self._state["cleared_route_destination"] = None
                self._state["cleared_route_at"] = None
                self._state["route_initial_count"] = route_initial_count
                self._state["route_updated_at"] = e.get("timestamp")
                self._state["arrived"] = False
                if final:
                    self._state["destination"] = final
                    self._state["destination_source"] = "elite_navroute"
                if destination_changed:
                    self._dispatch_journey(
                        "route_changed",
                        {
                            "previous_destination": old_dest,
                            "destination": final,
                            "route_jumps_remaining": self._route_jumps_remaining(),
                        },
                        f"route:destination:{str(final).casefold()}",
                    )
                elif same_destination_reroute:
                    self._dispatch_journey(
                        "route_changed",
                        {
                            "destination": final,
                            "previous_jumps_remaining": old_remaining,
                            "new_jumps_remaining": self._route_jumps_remaining(),
                        },
                        f"route:reroute:{old_remaining}:{self._route_jumps_remaining()}",
                    )

        elif name == "NavRouteClear":
            previous_destination = (
                self._state.get("destination")
                if self._state.get("destination_source") == "elite_navroute"
                else None
            )
            self._state["route"] = []
            self._state["route_initial_count"] = None
            self._state["route_updated_at"] = e.get("timestamp")
            # Do not erase a manually tracked destination.
            if self._state.get("destination_source") == "elite_navroute":
                self._state["destination"] = None
                self._state["destination_source"] = None
            self._state["cleared_route_destination"] = previous_destination
            self._state["cleared_route_at"] = time.time() if previous_destination else None

    def _normalise_route(self, route) -> list[dict[str, Any]]:
        if not isinstance(route, list):
            return []
        out = []
        for item in route:
            if not isinstance(item, dict):
                continue
            system = item.get("StarSystem")
            if not system:
                continue
            row = {"StarSystem": system}
            if self._valid_pos(item.get("StarPos")):
                row["StarPos"] = list(item["StarPos"])
            if item.get("StarClass"):
                row["StarClass"] = item.get("StarClass")
            out.append(row)
        return out

    def _advance_route(self, current_system):
        if not current_system:
            return
        route = list(self._state.get("route") or [])
        if not route:
            return
        # Drop everything before/current system, leaving current + future route when found.
        idx = None
        for i, item in enumerate(route):
            if self._same_system(item.get("StarSystem"), current_system):
                idx = i
                break
        if idx is not None:
            self._state["route"] = route[idx:]

    def _same_system(self, a, b) -> bool:
        return str(a or "").strip().casefold() == str(b or "").strip().casefold()

    def _valid_pos(self, pos) -> bool:
        return isinstance(pos, (list, tuple)) and len(pos) >= 3

    def _number(self, value) -> float:
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    def _straight_line_remaining(self) -> float | None:
        pos = self._state.get("current_starpos")
        route = self._state.get("route") or []
        if not self._valid_pos(pos) or not route:
            return None
        final_pos = route[-1].get("StarPos")
        if not self._valid_pos(final_pos):
            return None
        try:
            return math.sqrt(sum((float(final_pos[i]) - float(pos[i])) ** 2 for i in range(3)))
        except Exception:
            return None

    def _route_jumps_for(self, route: list[dict[str, Any]]) -> int | None:
        if not route:
            return 0
        current = self._state.get("current_system")
        if current and self._same_system(route[0].get("StarSystem"), current):
            return max(0, len(route) - 1)
        return len(route)

    def _route_jumps_remaining(self) -> int | None:
        route = self._state.get("route") or []
        if not route:
            return 0 if self._state.get("arrived") else None
        return self._route_jumps_for(route)

    def _public_state(self, full=False) -> dict[str, Any]:
        s = deepcopy(self._state)
        s.pop("last_event_key", None)
        s.pop("cleared_route_destination", None)
        s.pop("cleared_route_at", None)
        recent = [float(x) for x in s.get("recent_jumps_ly") or []]
        s["average_jump_this_leg_ly"] = round(
            float(s.get("distance_this_leg_ly") or 0) / int(s.get("jumps_this_leg") or 1), 2
        ) if s.get("jumps_this_leg") else None
        s["recent_average_jump_ly"] = round(sum(recent) / len(recent), 2) if recent else None
        s["route_jumps_remaining"] = self._route_jumps_remaining()
        rem = self._straight_line_remaining()
        s["straight_line_distance_to_route_destination_ly"] = round(rem, 2) if rem is not None else None
        s["distance_this_leg_ly"] = round(float(s.get("distance_this_leg_ly") or 0), 2)
        s["fuel_scooped_tonnes"] = round(float(s.get("fuel_scooped_tonnes") or 0), 2)

        initial = s.get("route_initial_count")
        remaining = s["route_jumps_remaining"]
        if isinstance(initial, int) and initial > 0 and isinstance(remaining, int):
            done = max(0, initial - remaining)
            s["route_progress_percent"] = round(min(100.0, (done / initial) * 100), 1)
        else:
            s["route_progress_percent"] = None

        if not full:
            route = s.pop("route", [])
            if route:
                s["next_route_system"] = route[1]["StarSystem"] if len(route) > 1 else None
            s.pop("recent_jumps_ly", None)
            s.pop("current_starpos", None)
        return s

    def _action_status(self, args: NavigatorStatusArgs):
        with self._lock:
            return json.dumps({
                "ok": True,
                "journey": self._public_state(full=(args.detail == "full")),
                "assistant_instruction": (
                    "These are journey-tracking facts, not a route-planning recommendation. "
                    "route_jumps_remaining is authoritative only when a current Elite NavRoute is present. "
                    "straight_line_distance_to_route_destination_ly is geometric distance, not plotted route length. "
                    "If destination/route is unknown, say so rather than estimating jumps remaining."
                )
            }, ensure_ascii=False)

    def _action_control(self, args: NavigatorControlArgs):
        with self._lock:
            if args.operation == "set_destination":
                dest = (args.destination or "").strip()
                if not dest:
                    return json.dumps({"ok": False, "error": "A destination system is required."})
                self._state["destination"] = dest
                self._state["destination_source"] = "manual"
                self._state["arrived"] = False
                self._state["cleared_route_destination"] = None
                self._state["cleared_route_at"] = None
                self._save()
                return json.dumps({
                    "ok": True,
                    "destination": dest,
                    "assistant_instruction": (
                        "TARS is tracking this named destination. This does not mean an Elite route has been plotted, "
                        "and jumps remaining are unknown until NavRoute data exists."
                    )
                }, ensure_ascii=False)

            if args.operation == "clear_destination":
                self._state["destination"] = None
                self._state["destination_source"] = None
                self._state["route"] = []
                self._state["route_initial_count"] = None
                self._state["arrived"] = False
                self._state["cleared_route_destination"] = None
                self._state["cleared_route_at"] = None
                self._save()
                return json.dumps({"ok": True, "message": "Tracked destination cleared."})

            if args.operation == "reset_leg":
                current = self._state.get("current_system")
                pos = self._state.get("current_starpos")
                dest = self._state.get("destination")
                source = self._state.get("destination_source")
                route = self._state.get("route") or []
                self._state = self._empty_state()
                self._state["leg_started_at"] = datetime.now(timezone.utc).isoformat()
                self._state["start_system"] = current
                self._state["current_system"] = current
                self._state["current_starpos"] = pos
                self._state["destination"] = dest
                self._state["destination_source"] = source
                self._state["route"] = route
                self._state["route_initial_count"] = max(0, len(route) - 1) if route else None
                self._state["journey_callouts"] = []
                self._save()
                return json.dumps({"ok": True, "message": "Current journey leg reset."})

            return json.dumps({"ok": False, "error": "Unsupported operation."})

    def _status_context(self, states):
        with self._lock:
            s = self._public_state(full=False)
            if not s.get("current_system") and not s.get("jumps_this_leg") and not s.get("destination"):
                return []
            bits = []
            if s.get("current_system"):
                bits.append(f"current {s['current_system']}")
            if s.get("destination"):
                bits.append(f"destination {s['destination']}")
            if s.get("route_jumps_remaining") is not None:
                bits.append(f"{s['route_jumps_remaining']} route jumps remaining")
            if s.get("jumps_this_leg"):
                bits.append(f"{s['jumps_this_leg']} jumps this leg")
                bits.append(f"{s['distance_this_leg_ly']:.0f} light-years travelled")
            if s.get("route_progress_percent") is not None:
                bits.append(f"{s['route_progress_percent']:.0f}% of captured route completed")
            return [(
                "TARS Navigator",
                "Journey: " + ", ".join(bits) + ". "
                "Use tars_navigator_status for detail. Navigator tracks progress; native Elite/COVAS owns route plotting."
            )]
