from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

from lib.Logger import log


def _load_base_module():
    path = Path(__file__).with_name("TARSNavigator.py")
    name = "_tars_navigator_base_session_guard"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load base Navigator from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_base_module = _load_base_module()
_BaseNavigator = _base_module.TARSNavigator


class TARSNavigator(_BaseNavigator):
    """Session-regression hardening layer for Navigator 1.1.x.

    Keeps the stable route/state implementation intact while adding:
    - direct-question priority over proactive NavigatorTarget speech
    - quieter milestone hysteresis
    - a clearly-marked last-known route fallback when current NavRoute data vanishes
    """

    def __init__(self, plugin_manifest):
        super().__init__(plugin_manifest)
        self._direct_question_pending_at = 0.0
        self._last_user_activity_at = 0.0

    def _empty_state(self) -> dict[str, Any]:
        state = super()._empty_state()
        state.setdefault("last_valid_route_snapshot", None)
        return state

    def _direct_question_pending(self) -> bool:
        if not self._direct_question_pending_at:
            return False
        return (time.time() - self._direct_question_pending_at) < 120.0

    def _observe_event(self, event, context):
        kind = getattr(event, "kind", "")
        now = time.time()

        if kind in ("user", "user_speaking"):
            self._last_user_activity_at = now
            self._direct_question_pending_at = now
            return

        if kind == "assistant":
            self._direct_question_pending_at = 0.0
            return

        if kind in ("assistant_speaking", "assistant_acting"):
            return

        super()._observe_event(event, context)

    def _should_reply_to_journey_target(self, event):
        if not super()._should_reply_to_journey_target(event):
            return False
        # Do not check COVAS reply_pending here: some versions set it for the
        # proactive event itself before should_reply_check runs. Explicit user
        # activity is the stable way to protect a direct commander question.
        if self._direct_question_pending():
            log("info", "TARS Navigator suppressed proactive milestone: commander reply has priority.")
            return False
        return True

    def _maybe_progress_callout(self):
        remaining = self._route_jumps_remaining()
        initial = self._state.get("route_initial_count")
        if not isinstance(initial, int) or not isinstance(remaining, int):
            return

        # Very short routes need almost no narration. For normal routes, keep only
        # a final-two marker and final jump. Percentage progress is reserved for
        # genuinely long legs and fires once at the midpoint.
        snap = self._journey_snapshot()

        if remaining == 1:
            self._dispatch_journey("final_jump", snap, "route:final_jump")
            return

        if remaining == 2 and initial >= 6:
            self._dispatch_journey("final_jumps", snap, "route:final_jumps")
            return

        if initial < 12 or remaining <= 2:
            return

        done = max(0, initial - remaining)
        pct = (done / initial) * 100.0 if initial else 0.0
        if pct >= 50.0:
            self._dispatch_journey(
                "progress",
                {**snap, "milestone_percent": 50},
                "route:progress:50",
            )

    def _remember_route_snapshot(self):
        route = self._state.get("route") or []
        if not route:
            return
        public = super()._public_state(full=False)
        remaining = public.get("route_jumps_remaining")
        if not isinstance(remaining, int):
            return
        self._state["last_valid_route_snapshot"] = {
            "captured_at": time.time(),
            "destination": public.get("destination"),
            "current_system": public.get("current_system"),
            "route_jumps_remaining": remaining,
            "route_progress_percent": public.get("route_progress_percent"),
            "straight_line_distance_to_route_destination_ly": public.get(
                "straight_line_distance_to_route_destination_ly"
            ),
        }

    def _fresh_route_snapshot(self) -> dict[str, Any] | None:
        snapshot = self._state.get("last_valid_route_snapshot")
        if not isinstance(snapshot, dict):
            return None
        try:
            age = max(0.0, time.time() - float(snapshot.get("captured_at") or 0.0))
        except (TypeError, ValueError):
            return None
        if age > 1800.0:
            return None
        return {**snapshot, "age_seconds": round(age, 1)}

    def _process(self, e: dict[str, Any]):
        name = str(e.get("event", "") or "")
        super()._process(e)

        # An explicit NavRouteClear is authoritative, not a transient status loss.
        # Do not resurrect the route the commander/game deliberately cleared.
        if name == "NavRouteClear":
            self._state["last_valid_route_snapshot"] = None
            return

        if name in ("NavRoute", "FSDJump", "Location", "CarrierJump"):
            self._remember_route_snapshot()

    def _public_state(self, full=False) -> dict[str, Any]:
        state = super()._public_state(full=full)
        # Keep this persistence-only field out of the public action/status payload.
        state.pop("last_valid_route_snapshot", None)

        current_remaining = state.get("route_jumps_remaining")
        snapshot = self._fresh_route_snapshot()

        if current_remaining is None and not state.get("arrived") and snapshot is not None:
            state["route_data_stale"] = True
            state["last_known_route"] = {
                "age_seconds": snapshot.get("age_seconds"),
                "destination": snapshot.get("destination"),
                "current_system_at_capture": snapshot.get("current_system"),
                "route_jumps_remaining": snapshot.get("route_jumps_remaining"),
                "route_progress_percent": snapshot.get("route_progress_percent"),
                "straight_line_distance_to_route_destination_ly": snapshot.get(
                    "straight_line_distance_to_route_destination_ly"
                ),
            }
        else:
            state["route_data_stale"] = False

        return state

    def _action_status(self, args):
        try:
            return super()._action_status(args)
        except Exception as exc:
            # Preserve a useful answer across a transient state/projection failure.
            # Never turn the snapshot into live route data: it remains explicitly
            # last-known and carries its age.
            snapshot = self._fresh_route_snapshot()
            if snapshot is None:
                raise
            log("warn", f"TARS Navigator status fell back to last-known route: {type(exc).__name__}")
            return json.dumps({
                "ok": True,
                "degraded": True,
                "journey": {
                    "current_system": self._state.get("current_system"),
                    "destination": self._state.get("destination") or snapshot.get("destination"),
                    "route_jumps_remaining": None,
                    "route_data_stale": True,
                    "last_known_route": {
                        "age_seconds": snapshot.get("age_seconds"),
                        "destination": snapshot.get("destination"),
                        "current_system_at_capture": snapshot.get("current_system"),
                        "route_jumps_remaining": snapshot.get("route_jumps_remaining"),
                        "route_progress_percent": snapshot.get("route_progress_percent"),
                        "straight_line_distance_to_route_destination_ly": snapshot.get(
                            "straight_line_distance_to_route_destination_ly"
                        ),
                    },
                },
                "assistant_instruction": (
                    "Navigator's live status lookup failed. Report the last-known route only as stale fallback data, "
                    "including its age when useful. Do not present last_known_route.route_jumps_remaining as current."
                ),
            }, ensure_ascii=False)


# Avoid exposing the imported base class as a second plugin candidate.
del _BaseNavigator
