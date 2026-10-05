from __future__ import annotations

import json
import math
import threading
import time
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from lib.PluginBase import PluginBase, PluginManifest
from lib.PluginHelper import PluginHelper, PluginEvent
from lib.Logger import log


# -----------------------------------------------------------------------------
# Action argument models
# -----------------------------------------------------------------------------


class EmptyArgs(BaseModel):
    pass


class BodyArgs(BaseModel):
    body_name: str = Field(
        default="",
        description=(
            "Body name or suffix such as 'A 3', '4', or a full body name. "
            "Leave blank to summarize all relevant bodies."
        ),
    )


# -----------------------------------------------------------------------------
# Internal state
# -----------------------------------------------------------------------------


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _localized(obj: dict, base: str) -> str:
    return _clean(obj.get(f"{base}_Localised") or obj.get(base))


def _is_biological_signal(signal: dict) -> bool:
    text = " ".join(
        _clean(signal.get(k))
        for k in ("Type_Localised", "Type", "Name_Localised", "Name")
    ).casefold()
    return "biological" in text or "biology" in text


def _is_geological_signal(signal: dict) -> bool:
    text = " ".join(
        _clean(signal.get(k))
        for k in ("Type_Localised", "Type", "Name_Localised", "Name")
    ).casefold()
    return "geological" in text or "geology" in text


@dataclass
class OrganicProgress:
    genus: str = ""
    species: str = ""
    variant: str = ""
    scan_type: str = ""
    samples_seen: int = 0
    complete: bool = False


@dataclass
class BodyState:
    body_id: int | None = None
    name: str = ""
    body_type: str = ""
    planet_class: str = ""
    star_type: str = ""
    parent_planet_id: int | None = None
    parent_star_id: int | None = None
    terraform_state: str = ""
    landable: bool | None = None
    atmosphere: str = ""
    atmosphere_type: str = ""
    volcanism: str = ""
    gravity_ms2: float | None = None
    surface_temp_k: float | None = None
    surface_pressure_pa: float | None = None
    distance_ls: float | None = None
    mass_em: float | None = None
    radius_m: float | None = None
    orbital_period_s: float | None = None
    rotation_period_s: float | None = None
    axial_tilt_rad: float | None = None
    eccentricity: float | None = None
    semi_major_axis_m: float | None = None
    tidal_lock: bool | None = None
    rings: list[dict] = field(default_factory=list)
    was_discovered: bool | None = None
    was_mapped: bool | None = None
    biological_signals: int = 0
    geological_signals: int = 0
    dss_mapped: bool = False
    dss_efficiency: bool | None = None
    confirmed_genuses: list[str] = field(default_factory=list)
    organics: dict[str, OrganicProgress] = field(default_factory=dict)

    @property
    def terraformable(self) -> bool:
        t = self.terraform_state.casefold().strip()
        return bool(t and "terraform" in t and "not terraform" not in t)

    @property
    def is_planet(self) -> bool:
        return bool(self.planet_class)

    @property
    def interesting_world_type(self) -> str | None:
        p = self.planet_class.casefold()
        if "earthlike" in p or "earth-like" in p:
            return "Earth-like world"
        if "water world" in p:
            return "Water world"
        if "ammonia world" in p:
            return "Ammonia world"
        return None


# -----------------------------------------------------------------------------
# Plugin
# -----------------------------------------------------------------------------


class TARSExplorer(PluginBase):
    """Live, deterministic exploration copilot for COVAS NEXT."""

    EXPLORER_STYLE_GUARD = (
        "STYLE: lead with the useful factual observation. Humor is optional, never required. "
        "A plain concise line is better than a forced punchline. Do not use mystery/mysterious, "
        "pretending to be mysterious, one less mystery, main character, wants/wanting attention, "
        "invitation, refuses/refusing, ambitious, misbehaving, trying hard, or similar stock "
        "anthropomorphic endings. Do not describe planets, stars, rings, scans or systems as if "
        "they have motives, attitudes, intentions, vanity, stubbornness or personalities. "
        "Do not use paperwork/bureaucracy as generic humor. Do not use recurring work/payoff idioms "
        "such as 'earn their keep', 'work for their keep', 'earn the right to complain', or equivalent "
        "phrasing that turns bodies, rocks, boots or equipment into workers earning value. If no fresh "
        "grounded joke follows directly from a supplied fact, omit the joke."
    )

    settings_config = {
        "key": "TARSExplorer",
        "label": "TARS Explorer",
        "icon": "wrench",
        "grids": [
            {
                "key": "about",
                "label": "TARS Explorer",
                "fields": [
                    {
                        "key": "about_text",
                        "label": "Exploration copilot",
                        "type": "paragraph",
                        "readonly": True,
                        "placeholder": None,
                        "content": (
                            "TARS Explorer builds live exploration state from Elite journal events. "
                            "It answers system-summary, priority, body, biology and completion questions. "
                            "Version 1.4.9 keeps high-value discovery callouts while suppressing low-value physical trivia, duplicate body narration, and premature FSS wrap-ups."
                        ),
                    },
                    {
                        "key": "automatic_callouts",
                        "label": "Automatic noteworthy target callouts",
                        "type": "toggle",
                        "readonly": False,
                        "placeholder": None,
                        "default_value": True,
                    },
                    {
                        "key": "biology_callouts",
                        "label": "Call out biology-rich bodies",
                        "type": "toggle",
                        "readonly": False,
                        "placeholder": None,
                        "default_value": True,
                    },
                    {
                        "key": "minimum_bio_signals",
                        "label": "Minimum biological signals for automatic callout",
                        "type": "number",
                        "readonly": False,
                        "placeholder": None,
                        "default_value": 3,
                        "min_value": 1,
                        "max_value": 10,
                        "step": 1,
                    }
                ],
            }
        ],
    }

    def __init__(self, plugin_manifest: PluginManifest):
        super().__init__(plugin_manifest)
        self._helper: PluginHelper | None = None
        self._session_id: int = 0
        self._system_name: str = ""
        self._system_address: int | None = None
        self._star_pos: tuple[float, float, float] | None = None
        self._expected_bodies: int | None = None
        self._fss_complete: bool = False
        self._bodies: dict[str, BodyState] = {}
        self._body_id_to_key: dict[int, str] = {}
        self._new_codex_entries: list[dict] = []
        self._announced_callouts: set[str] = set()
        self._announced_body_keys: set[str] = set()
        self._last_body_callout_at: dict[str, float] = {}
        self._last_any_callout_at: float | None = None
        self._current_body_name: str = ""
        self._current_body_id: int | None = None
        self._body_context_state: str = ""
        self._callout_decisions: list[dict] = []
        # Cross-body novelty memory for this system. Protected valuable-world callouts
        # bypass this completely; it only suppresses repeated non-core observations.
        self._novelty_idea_counts: dict[str, int] = {}
        # Elite/COVAS can deliver FSSAllBodiesFound before the final same-second
        # Scan events. Debounce the wrap-up briefly so its composition is built
        # from the complete event batch instead of whichever bodies arrived first.
        self._fss_completion_timer: threading.Timer | None = None
        self._fss_completion_generation: int = 0

    def on_chat_start(self, helper: PluginHelper):
        self._helper = helper
        self._session_id += 1
        self._prime_from_history()
        helper.register_sideeffect(self._observe_event)

        helper.register_event(
            name="TARSExplorerTarget",
            should_reply_check=self._should_reply_to_target,
            prompt_generator=self._prompt_noteworthy_target,
        )

        helper.register_action(
            name="tars_explorer_system_summary",
            description=(
                "Give an accurate exploration-focused summary of the commander's CURRENT Elite Dangerous system. "
                "Use this for 'what's interesting in this system?', 'anything interesting here?', "
                "'what is worth checking here?', 'what did I find?', 'summarize this system', "
                "'anything notable?', 'is this system worth it?', or similar exploration questions. "
                "Prefer this over generic conversation for current-system exploration analysis."
            ),
            parameters=EmptyArgs,
            method=self._action_system_summary,
            action_type="global",
        )

        helper.register_action(
            name="tars_explorer_priority_targets",
            description=(
                "Rank the commander's CURRENT system exploration targets using known journal facts. "
                "Use for 'what should I map?', 'what should I scan?', 'where should I land?', "
                "'what should I bother with?', 'what are the priority targets?', or 'what next?'."
            ),
            parameters=EmptyArgs,
            method=self._action_priority_targets,
            action_type="global",
        )

        helper.register_action(
            name="tars_explorer_body_info",
            description=(
                "Return detailed known exploration facts for a body in the current system. "
                "Use for 'tell me about A 3', 'is planet 4 terraformable?', 'what is on A 6?', "
                "or other questions about one specific body."
            ),
            parameters=BodyArgs,
            method=self._action_body_info,
            action_type="global",
        )

        helper.register_action(
            name="tars_explorer_biology",
            description=(
                "Return exobiology status for the current system or a named body: biological signal counts, "
                "DSS-confirmed genera, sampled species/variants and remaining confirmed genera. "
                "Use for 'what bios are here?', 'what bios are on A 3?', 'what am I missing biologically?', "
                "or 'have I finished the bios?'. Do not invent BioInsights predictions that are not returned."
            ),
            parameters=BodyArgs,
            method=self._action_biology,
            action_type="global",
        )

        helper.register_action(
            name="tars_explorer_progress",
            description=(
                "Report current-system exploration completion. Use for 'am I finished here?', "
                "'what am I missing?', 'is the system scanned?', 'have I mapped everything worth mapping?', "
                "or 'can I leave this system?'. Distinguish FSS identification from DSS mapping."
            ),
            parameters=EmptyArgs,
            method=self._action_progress,
            action_type="global",
        )

        helper.register_action(
            name="tars_explorer_diagnostics",
            description=(
                "Diagnose TARS Explorer state and recent automatic callout decisions. ALWAYS use this action when the commander asks "
                "why Explorer did not react, why a Water World/Earth-like/Ammonia world/terraformable or other scan was not called out, "
                "whether Explorer saw the last scan, or asks to check Explorer diagnostics. Return the recorded decision reason; never invent one."
            ),
            parameters=EmptyArgs,
            method=self._action_diagnostics,
            action_type="global",
        )

        log("info", f"TARS Explorer 1.4.9 started. Current system: {self._system_name or 'unresolved'}")

    def on_chat_stop(self, helper: PluginHelper):
        self._cancel_fss_completion()
        self._session_id += 1
        self._helper = None

    # ------------------------------------------------------------------
    # Serialization / helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _json(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

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

    def _reset_system(
        self,
        name: str,
        address: int | None = None,
        star_pos: tuple[float, float, float] | None = None,
    ):
        changed = bool(name) and (
            name.casefold() != self._system_name.casefold()
            or (address is not None and self._system_address is not None and address != self._system_address)
        )
        if changed:
            self._cancel_fss_completion()
            self._expected_bodies = None
            self._fss_complete = False
            self._bodies = {}
            self._body_id_to_key = {}
            # System name/address changes define a hard boundary. Do not let
            # omitted metadata on the new-system event inherit the previous
            # system's address or coordinates.
            self._system_address = None
            self._star_pos = None
            self._new_codex_entries = []
            self._announced_callouts = set()
            self._announced_body_keys = set()
            self._last_body_callout_at = {}
            self._last_any_callout_at = None
            self._current_body_name = ""
            self._current_body_id = None
            self._body_context_state = ""
            self._callout_decisions = []
            self._novelty_idea_counts = {}
        if name:
            self._system_name = name
        if address is not None:
            self._system_address = address
        if star_pos is not None:
            self._star_pos = star_pos

    def _cancel_fss_completion(self):
        self._fss_completion_generation += 1
        timer = self._fss_completion_timer
        self._fss_completion_timer = None
        if timer is not None:
            timer.cancel()

    def _schedule_fss_completion(self):
        """Debounce the FSS wrap-up until trailing Scan events are consumed."""
        self._cancel_fss_completion()
        generation = self._fss_completion_generation
        session_id = self._session_id
        system_name = self._system_name
        system_address = self._system_address

        def flush():
            if (
                generation != self._fss_completion_generation
                or session_id != self._session_id
                or system_name != self._system_name
                or system_address != self._system_address
            ):
                return
            self._fss_completion_timer = None
            self._flush_fss_completion()

        timer = threading.Timer(0.75, flush)
        timer.daemon = True
        self._fss_completion_timer = timer
        timer.start()

    def _flush_fss_completion(self):
        """Dispatch one completed-system summary from the latest accumulated state."""
        self._cancel_fss_completion()
        payload = self._system_completion_payload()
        recent = (
            self._last_any_callout_at is not None
            and (time.monotonic() - self._last_any_callout_at) < 12.0
        )
        if not recent and self._system_completion_worthy(payload):
            self._dispatch_milestone("system_complete", payload, "fss_all_bodies_found")

    @staticmethod
    def _extract_star_pos(content: dict) -> tuple[float, float, float] | None:
        pos = content.get("StarPos")
        if not isinstance(pos, (list, tuple)) or len(pos) < 3:
            return None
        values = tuple(_safe_float(v) for v in pos[:3])
        if any(v is None for v in values):
            return None
        return values  # type: ignore[return-value]

    @staticmethod
    def _body_key(name: str, body_id: int | None) -> str:
        if body_id is not None:
            return f"id:{body_id}"
        return f"name:{name.casefold()}"

    def _find_body_key_by_name(self, name: str) -> str | None:
        wanted = _clean(name).casefold()
        if not wanted:
            return None
        for key, body in self._bodies.items():
            if _clean(body.name).casefold() == wanted:
                return key
        return None

    def _migrate_body_tracking_key(self, old_key: str, new_key: str):
        if not old_key or old_key == new_key:
            return

        if old_key in self._announced_body_keys:
            self._announced_body_keys.discard(old_key)
            self._announced_body_keys.add(new_key)

        if old_key in self._last_body_callout_at:
            previous = self._last_body_callout_at.pop(old_key)
            current = self._last_body_callout_at.get(new_key)
            self._last_body_callout_at[new_key] = (
                max(previous, current) if current is not None else previous
            )

        if self._announced_callouts:
            migrated = set()
            for item in self._announced_callouts:
                migrated.add(item.replace(old_key, new_key) if old_key in item else item)
            self._announced_callouts = migrated

    @staticmethod
    def _merge_organic_progress(target: OrganicProgress, source: OrganicProgress):
        if not target.genus and source.genus:
            target.genus = source.genus
        if not target.species and source.species:
            target.species = source.species
        if not target.variant and source.variant:
            target.variant = source.variant
        if not target.scan_type and source.scan_type:
            target.scan_type = source.scan_type
        target.samples_seen = max(target.samples_seen, source.samples_seen)
        target.complete = target.complete or source.complete

    def _merge_body_state(self, target: BodyState, source: BodyState):
        """Merge two records proven to represent the same physical body."""
        if target.body_id is None and source.body_id is not None:
            target.body_id = source.body_id
        if not target.name and source.name:
            target.name = source.name

        string_fields = (
            "body_type", "planet_class", "star_type", "terraform_state",
            "atmosphere", "atmosphere_type", "volcanism",
        )
        for attr in string_fields:
            if not getattr(target, attr) and getattr(source, attr):
                setattr(target, attr, getattr(source, attr))

        optional_fields = (
            "parent_planet_id", "parent_star_id", "landable", "gravity_ms2",
            "surface_temp_k", "surface_pressure_pa", "distance_ls", "mass_em",
            "radius_m", "orbital_period_s", "rotation_period_s", "axial_tilt_rad",
            "eccentricity", "semi_major_axis_m", "tidal_lock", "was_discovered",
            "was_mapped", "dss_efficiency",
        )
        for attr in optional_fields:
            if getattr(target, attr) is None and getattr(source, attr) is not None:
                setattr(target, attr, getattr(source, attr))

        if not target.rings and source.rings:
            target.rings = list(source.rings)

        target.biological_signals = max(target.biological_signals, source.biological_signals)
        target.geological_signals = max(target.geological_signals, source.geological_signals)
        target.dss_mapped = target.dss_mapped or source.dss_mapped

        for genus in source.confirmed_genuses:
            if genus not in target.confirmed_genuses:
                target.confirmed_genuses.append(genus)

        for key, progress in source.organics.items():
            existing = target.organics.get(key)
            if existing is None:
                target.organics[key] = progress
            else:
                self._merge_organic_progress(existing, progress)

    def _get_body(self, name: str = "", body_id: int | None = None) -> BodyState:
        name = _clean(name)
        id_key = f"id:{body_id}" if body_id is not None else None
        mapped_id_key = self._body_id_to_key.get(body_id) if body_id is not None else None

        body_by_id = None
        actual_id_key = None
        if mapped_id_key and mapped_id_key in self._bodies:
            actual_id_key = mapped_id_key
            body_by_id = self._bodies[mapped_id_key]
        elif id_key and id_key in self._bodies:
            actual_id_key = id_key
            body_by_id = self._bodies[id_key]

        name_key = self._find_body_key_by_name(name) if name else None
        body_by_name = self._bodies.get(name_key) if name_key else None

        if body_by_id is not None:
            body = body_by_id
            canonical_key = id_key or actual_id_key or self._body_key(body.name, body.body_id)

            if actual_id_key and actual_id_key != canonical_key:
                self._bodies.pop(actual_id_key, None)
                self._bodies[canonical_key] = body
                self._migrate_body_tracking_key(actual_id_key, canonical_key)

            if body_by_name is not None and body_by_name is not body:
                self._merge_body_state(body, body_by_name)
                if name_key:
                    self._bodies.pop(name_key, None)
                    self._migrate_body_tracking_key(name_key, canonical_key)

            self._bodies[canonical_key] = body

        elif body_id is not None and body_by_name is not None:
            # A name-only event created the record first. Promote that exact same
            # object to the stable BodyID key so no facts or callout history split.
            body = body_by_name
            old_key = name_key or self._body_key(body.name, None)
            canonical_key = id_key
            self._bodies.pop(old_key, None)
            self._bodies[canonical_key] = body
            self._migrate_body_tracking_key(old_key, canonical_key)

        elif body_id is not None:
            canonical_key = id_key
            body = BodyState(body_id=body_id, name=name)
            self._bodies[canonical_key] = body

        elif body_by_name is not None:
            body = body_by_name
            canonical_key = name_key or self._body_key(name, None)

        else:
            canonical_key = self._body_key(name, None)
            body = BodyState(body_id=None, name=name)
            self._bodies[canonical_key] = body

        if body_id is not None:
            body.body_id = body_id
            self._body_id_to_key[body_id] = canonical_key
        if name:
            body.name = name

        return body

    def _belongs_to_current_system(self, content: dict) -> bool:
        addr = _safe_int(content.get("SystemAddress"))
        if self._system_address is not None and addr is not None:
            return addr == self._system_address
        sys_name = _clean(content.get("SystemName") or content.get("StarSystem"))
        if sys_name and self._system_name:
            return sys_name.casefold() == self._system_name.casefold()
        return True

    # ------------------------------------------------------------------
    # Selective automatic callouts
    # ------------------------------------------------------------------

    def _auto_callouts_enabled(self) -> bool:
        return bool(self.settings.get("automatic_callouts", True))

    def _biology_callouts_enabled(self) -> bool:
        return bool(self.settings.get("biology_callouts", True))

    def _minimum_bio_signals(self) -> int:
        try:
            return max(1, min(10, int(self.settings.get("minimum_bio_signals", 3))))
        except (TypeError, ValueError):
            return 3

    def _automatic_value_reasons(self, body: BodyState) -> list[str]:
        """Reasons strong enough to interrupt the commander automatically.

        This deliberately excludes physical-curiosity trivia such as axial tilt,
        short orbital periods, ordinary rings, or merely unusual rotation. Those
        facts remain available through Explorer actions, but they do not justify
        unsolicited speech during a long route.
        """
        reasons: list[str] = []
        if body.interesting_world_type:
            reasons.append(body.interesting_world_type)
        if body.terraformable:
            reasons.append("terraformable")
        if body.confirmed_genuses:
            reasons.append("DSS-confirmed biology: " + ", ".join(body.confirmed_genuses))
        elif body.landable is True and body.biological_signals >= self._minimum_bio_signals():
            reasons.append(
                f"{body.biological_signals} biological signal"
                f"{'s' if body.biological_signals != 1 else ''}"
            )
        return list(dict.fromkeys(reasons))

    @staticmethod
    def _system_completion_worthy(payload: dict) -> bool:
        composition = payload.get("system_composition") if isinstance(payload, dict) else {}
        return bool(
            payload.get("earth_like_worlds")
            or payload.get("water_worlds")
            or payload.get("ammonia_worlds")
            or payload.get("terraformable_bodies")
            or payload.get("bodies_with_biology")
            or (isinstance(composition, dict) and composition.get("zero_planets_confirmed"))
        )

    def _should_reply_to_target(self, event: PluginEvent) -> bool:
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
        guarded_address = _safe_int(guard.get("system_address"))
        if guarded_address is not None and self._system_address is not None:
            if guarded_address != self._system_address:
                return False
        else:
            guarded_system = _clean(guard.get("system"))
            if guarded_system and self._system_name and guarded_system.casefold() != self._system_name.casefold():
                return False
        return True

    def _guarded_event_data(self, payload: dict) -> dict:
        data = dict(payload)
        data["_guard"] = {
            "session_id": self._session_id,
            "triggered_at": time.time(),
            "system": self._system_name or None,
            "system_address": self._system_address,
        }
        return data

    def _prompt_noteworthy_target(self, event: PluginEvent) -> str:
        raw = event.plugin_event_content if isinstance(event.plugin_event_content, dict) else {}
        data = {k: v for k, v in raw.items() if k != "_guard"}
        if data.get("test"):
            return "Say exactly: Explorer automatic target callouts are working."
        kind = data.get("callout_kind")
        if kind == "organic_complete":
            return (
                "TARS Explorer has recorded completion of an exobiology organism from live Elite journal data. "
                "Give one very brief natural acknowledgement now. Do not mention plugins or internal events. "
                "Use only the supplied facts. Name the organism when supplied. Do not add value estimates unless supplied. "
                + self.EXPLORER_STYLE_GUARD + " "
                + f"Completion facts: {json.dumps(data, ensure_ascii=False)}"
            )
        if kind == "system_complete":
            return (
                "The commander has just completed FSS identification of every body in the current system. "
                "Give one short TARS-like system wrap-up using only player-facing supplied facts: concise, dry and observant, with light sarcasm only when natural. Prioritize genuinely useful discoveries or remaining targets. "
                "Never say internal bookkeeping words such as announced, unannounced, score, threshold, category, detector or cooldown. "
                "Do not repeat a body/fact that Explorer already called out unless needed to make the summary useful. "
                "FSS complete means all bodies identified, NOT all bodies DSS mapped. NEVER describe FSS completion as mapped, fully mapped, mapping complete, or all mapped. Use identified, found, or FSS complete instead. Vary wording between systems and avoid canned phrases. "
                "Use system_composition when supplied: distinguish stars, planets, moons and belt clusters instead of treating body_count as planets. "
                "If zero_planets_confirmed is true, you may naturally point out that the system has no planets or moons and FSS needs no further work; a dry TARS remark is welcome, but do not force the same joke repeatedly. "
                "If the system is ordinary, either give a very short natural line or stay silent; never invent significance or call the system physically unusual merely because bodies are cold, tidally locked, thin-atmosphered, or otherwise normal for their class. Avoid cosmic poetry. "
                + self.EXPLORER_STYLE_GUARD + " "
                + f"System facts: {json.dumps(data, ensure_ascii=False)}"
            )
        if kind == "dss_complete":
            return (
                "A worthwhile body has just finished DSS mapping. Give one short factual acknowledgement using only supplied facts. "
                "Do not repeat the earlier discovery description; focus on mapping completion, efficiency, or newly confirmed biology. "
                + self.EXPLORER_STYLE_GUARD + " "
                + f"Mapping facts: {json.dumps(data, ensure_ascii=False)}"
            )
        if kind == "codex_new":
            return (
                "A genuinely new Codex entry was recorded. Give one brief factual acknowledgement using only supplied facts. "
                "Do not embellish or estimate value. "
                + self.EXPLORER_STYLE_GUARD + " "
                + f"Codex facts: {json.dumps(data, ensure_ascii=False)}"
            )
        if kind == "approach_noteworthy":
            return (
                "The commander is approaching a previously identified noteworthy body. Give one short useful approach reminder only from supplied facts. "
                "Do not merely say that the ship is approaching it, and do not repeat old wording. Focus on what makes the destination useful. "
                + self.EXPLORER_STYLE_GUARD + " "
                + f"Approach facts: {json.dumps(data, ensure_ascii=False)}"
            )
        if kind == "unfinished_target":
            return (
                "The commander is leaving a system with a genuinely important exploration target unfinished. "
                "Give one short useful warning using only supplied facts. Do not scold, and do not invent value. "
                "If the omission is already obvious from the conversation, silence is acceptable. "
                + self.EXPLORER_STYLE_GUARD + " "
                + f"Unfinished target facts: {json.dumps(data, ensure_ascii=False)}"
            )
        if kind == "biology_body_complete":
            return (
                "Explorer has enough journal evidence that all DSS-confirmed genera on this body have completed Analyse scans. "
                "Give one brief natural completion line. Do not claim all possible biology is complete beyond the confirmed genera. "
                + self.EXPLORER_STYLE_GUARD + " "
                + f"Biology completion facts: {json.dumps(data, ensure_ascii=False)}"
            )
        return (
            "TARS Explorer has identified a genuinely worthwhile exploration observation from live Elite journal data. "
            "Speak like TARS: concise, dry, observant and occasionally sarcastic, but never force a joke. Facts are sacred. "
            "Prefer an observation over a report. Do not mention plugins, internal events, classifications or why a detector fired. "
            "Use only the supplied facts. Use the short body label; do not repeat the full procedural system name unless needed for clarity. "
            "Never say 'matters for', 'noteworthy because', 'stands out for', 'of interest', 'physically unusual', 'unannounced', scores or thresholds. "
            "Use speech-friendly rounded quantities. Temperatures supplied for speech are Celsius; do not convert them back to Kelvin. "
            "If biological signals are listed, call them biological signals, not species. Do not say the system is fully mapped. No cosmic poetry. "
            + self.EXPLORER_STYLE_GUARD + " "
            + f"Target facts: {json.dumps(data, ensure_ascii=False)}"
        )

    def _body_callout_cooldown(self, body_key: str, now: float | None = None) -> str | None:
        previous = self._last_body_callout_at.get(body_key)
        if previous is None:
            return None
        current = time.monotonic() if now is None else now
        elapsed = current - previous
        if elapsed < 45.0:
            return f"suppressed: same-body cooldown ({elapsed:.1f}s)"
        return None

    def _dispatch_target_callout(self, body: BodyState, callout_kind: str, reasons: list[str]) -> str:
        if self._helper is None:
            return "suppressed: helper unavailable"
        if not self._auto_callouts_enabled():
            return "suppressed: automatic callouts disabled"
        body_key = self._body_key(body.name, body.body_id)
        key = f"{body_key}:{callout_kind}"
        if key in self._announced_callouts:
            return "suppressed: already announced"

        # Avoid back-to-back target narration when Scan and signal events for the
        # same body arrive within a few seconds. Do not mark the later category as
        # announced, so a later journal update can still surface genuinely new facts.
        now = time.monotonic()
        if callout_kind in ("scan_value", "biology"):
            cooldown = self._body_callout_cooldown(body_key, now)
            if cooldown:
                return cooldown

        self._announced_callouts.add(key)
        self._announced_body_keys.add(body_key)
        self._last_body_callout_at[body_key] = now
        payload = {
            "system": self._system_name or None,
            "body": self._display_name(body),
            "planet_class": body.planet_class or None,
            "terraformable": body.terraformable,
            "landable": body.landable,
            "distance_from_arrival_ls": body.distance_ls,
            "biological_signals": body.biological_signals,
            "confirmed_genuses": body.confirmed_genuses,
            "exceptional_properties": self._exceptional_reasons(body),
            "reasons": reasons,
            "callout_kind": callout_kind,
        }
        try:
            self._helper.dispatch_event(PluginEvent(
                plugin_event_name="TARSExplorerTarget",
                plugin_event_content=self._guarded_event_data(payload),
            ))
            self._last_any_callout_at = time.monotonic()
            log("info", f"TARS Explorer callout dispatched for {self._display_name(body)}: {', '.join(reasons)}")
            return "dispatched"
        except Exception as exc:
            self._announced_callouts.discard(key)
            log("warn", f"TARS Explorer callout dispatch failed: {exc}")
            return f"dispatch failed: {type(exc).__name__}: {exc}"

    def _dispatch_body_milestone(
        self,
        body: BodyState,
        callout_kind: str,
        payload: dict,
        dedupe_key: str,
    ) -> str:
        """Dispatch a body-specific milestone without talking over a fresh body callout.

        DSS completion and scan/biology events can arrive only seconds apart for the
        same body. Treat them as one conversational opportunity unless enough time
        has passed for genuinely new information to deserve another remark.
        """
        if self._helper is None:
            return "suppressed: helper unavailable"
        if not self._auto_callouts_enabled():
            return "suppressed: automatic callouts disabled"

        body_key = self._body_key(body.name, body.body_id)
        key = f"milestone:{dedupe_key}"
        if key in self._announced_callouts:
            return "suppressed: already announced"

        now = time.monotonic()
        cooldown = self._body_callout_cooldown(body_key, now)
        if cooldown:
            return cooldown

        data = dict(payload)
        data["callout_kind"] = callout_kind
        data.setdefault("system", self._system_name or None)
        self._announced_callouts.add(key)
        try:
            self._helper.dispatch_event(PluginEvent(
                plugin_event_name="TARSExplorerTarget",
                plugin_event_content=self._guarded_event_data(data),
            ))
            self._announced_body_keys.add(body_key)
            self._last_body_callout_at[body_key] = now
            self._last_any_callout_at = time.monotonic()
            log("info", f"TARS Explorer body milestone dispatched: {callout_kind}")
            return "dispatched"
        except Exception as exc:
            self._announced_callouts.discard(key)
            log("warn", f"TARS Explorer body milestone dispatch failed: {exc}")
            return f"dispatch failed: {type(exc).__name__}: {exc}"

    def _dispatch_milestone(self, callout_kind: str, payload: dict, dedupe_key: str):
        if self._helper is None or not self._auto_callouts_enabled():
            return
        key = f"milestone:{dedupe_key}"
        if key in self._announced_callouts:
            return
        self._announced_callouts.add(key)
        data = dict(payload)
        data["callout_kind"] = callout_kind
        data.setdefault("system", self._system_name or None)
        try:
            self._helper.dispatch_event(PluginEvent(
                plugin_event_name="TARSExplorerTarget",
                plugin_event_content=self._guarded_event_data(data),
            ))
            self._last_any_callout_at = time.monotonic()
            log("info", f"TARS Explorer milestone dispatched: {callout_kind}")
        except Exception as exc:
            self._announced_callouts.discard(key)
            log("warn", f"TARS Explorer milestone dispatch failed: {exc}")

    def _system_completion_payload(self) -> dict:
        planets = self._planet_bodies()
        composition = self._system_composition()
        notable = [b for b in planets if self._interesting_reasons(b)]
        notable.sort(key=lambda b: self._priority_score(b), reverse=True)

        # Only expose player-facing facts. Announcement state, detector categories,
        # scores and suppression metadata belong in diagnostics, never speech.
        remaining = []
        for b in notable:
            key = self._body_key(b.name, b.body_id)
            if key in self._announced_body_keys:
                continue
            reasons = self._interesting_reasons(b)
            if reasons:
                remaining.append({
                    "body": self._display_name(b),
                    "reasons": reasons,
                    "mapped": b.dss_mapped,
                })
            if len(remaining) >= 5:
                break

        dss_mapped = sum(1 for b in planets if b.dss_mapped)
        return {
            "body_count": self._expected_bodies or len(self._bodies),
            "system_composition": composition,
            "fss_complete": self._fss_complete,
            "dss_mapped_bodies": dss_mapped,
            "all_planetary_bodies_dss_mapped": bool(planets) and dss_mapped == len(planets),
            "earth_like_worlds": sum(1 for b in planets if b.interesting_world_type == "Earth-like world"),
            "water_worlds": sum(1 for b in planets if b.interesting_world_type == "Water world"),
            "ammonia_worlds": sum(1 for b in planets if b.interesting_world_type == "Ammonia world"),
            "terraformable_bodies": sum(1 for b in planets if b.terraformable),
            "bodies_with_biology": sum(1 for b in planets if b.biological_signals > 0),
            "total_biological_signals": sum(b.biological_signals for b in planets),
            "remaining_noteworthy_targets": remaining,
        }

    def _record_callout_decision(self, body: BodyState, category: str, expected: bool, outcome: str, reasons: list[str] | None = None):
        self._callout_decisions.append({
            "body": self._display_name(body),
            "full_name": body.name or None,
            "planet_class": body.planet_class or None,
            "category": category,
            "expected_callout": expected,
            "outcome": outcome,
            "reasons": list(reasons or []),
        })
        self._callout_decisions = self._callout_decisions[-20:]

    @staticmethod
    def _novelty_idea(reason: str) -> str:
        """Normalize a player-facing reason into a stable idea family.

        The point is to suppress repetition of the same observation across sibling
        bodies, not merely identical wording or identical numeric values.
        """
        r = _clean(reason).casefold()
        if not r:
            return ""
        if "ring" in r:
            return "rings"
        if "gravity" in r or "high-g" in r or "low gravity" in r:
            return "gravity_extreme"
        if "temperature" in r or "hot surface" in r or "hot gas giant" in r:
            return "temperature_extreme"
        if "massive" in r or "earth masses" in r:
            return "mass_extreme"
        if "large terrestrial" in r or "km radius" in r:
            return "size_extreme"
        if "short orbit" in r:
            return "short_orbit"
        if "fast rotation" in r:
            return "fast_rotation"
        if "eccentric orbit" in r:
            return "eccentric_orbit"
        if "axial tilt" in r:
            return "axial_tilt"
        if "dense atmosphere" in r:
            return "dense_atmosphere"
        if "water-based life" in r:
            return "water_life_giant"
        if "ammonia-based life" in r:
            return "ammonia_life_giant"
        if "helium-rich gas giant" in r:
            return "helium_rich_giant"
        if "water giant" in r:
            return "water_giant"
        # Remove volatile numbers so "8.2 g" and "9.1 g" remain the same idea.
        return re.sub(r"\d+(?:[.,]\d+)?", "#", r)

    def _novel_exceptional_reasons(self, reasons: list[str]) -> tuple[list[str], list[str]]:
        """Return (fresh reasons, repeated ideas) for non-core callouts.

        First occurrence of an idea in a system is fresh. A later body must bring at
        least one new idea to earn another exceptional callout. Repeated details can
        still accompany that fresh idea so the resulting remark has useful context.
        """
        ideas = [self._novelty_idea(r) for r in reasons]
        fresh_ideas = {idea for idea in ideas if idea and self._novelty_idea_counts.get(idea, 0) == 0}
        repeated = sorted({idea for idea in ideas if idea and idea not in fresh_ideas})
        if not fresh_ideas:
            return [], repeated
        return list(reasons), repeated

    def _remember_novelty_reasons(self, reasons: list[str]):
        for reason in reasons:
            idea = self._novelty_idea(reason)
            if idea:
                self._novelty_idea_counts[idea] = self._novelty_idea_counts.get(idea, 0) + 1

    def _maybe_dispatch_noteworthy(self, body: BodyState, rebuilding: bool = False):
        # Core valuable worlds are deliberately independent from exceptional-body scoring.
        # A Water World/ELW/AW/terraformable must never disappear because a heuristic changes.
        core_reasons: list[str] = []
        if body.interesting_world_type:
            core_reasons.append(body.interesting_world_type)
        if body.terraformable:
            core_reasons.append("terraformable")

        if rebuilding:
            self._record_callout_decision(body, "scan", bool(core_reasons), "suppressed: history reconstruction", core_reasons)
            return
        if not self._auto_callouts_enabled():
            self._record_callout_decision(body, "scan", bool(core_reasons), "suppressed: automatic callouts disabled", core_reasons)
            return
        if not body.is_planet:
            self._record_callout_decision(body, "scan", False, "not a planet/body with PlanetClass", [])
            return

        exceptional = self._exceptional_reasons(body)
        primary_dispatched = False

        if core_reasons:
            # ELW / Water World / Ammonia / terraformable are protected. Novelty
            # suppression must never silence these; exceptional context may ride along.
            scan_reasons = core_reasons + exceptional
            if body.biological_signals > 0:
                scan_reasons.append(f"{body.biological_signals} biological signal{'s' if body.biological_signals != 1 else ''}")
            outcome = self._dispatch_target_callout(body, "core_value", scan_reasons)
            if outcome == "dispatched":
                primary_dispatched = True
                self._remember_novelty_reasons(exceptional)
            self._record_callout_decision(body, "core_value", True, outcome, scan_reasons)

        elif exceptional:
            novel_reasons, repeated_ideas = self._novel_exceptional_reasons(exceptional)
            if novel_reasons:
                scan_reasons = list(novel_reasons)
                if body.biological_signals > 0:
                    scan_reasons.append(f"{body.biological_signals} biological signal{'s' if body.biological_signals != 1 else ''}")
                outcome = self._dispatch_target_callout(body, "scan_value", scan_reasons)
                if outcome == "dispatched":
                    primary_dispatched = True
                    self._remember_novelty_reasons(exceptional)
                self._record_callout_decision(body, "scan_value", True, outcome, scan_reasons)
            else:
                ideas = ", ".join(repeated_ideas) if repeated_ideas else "same observation"
                self._record_callout_decision(
                    body, "scan_value", False,
                    f"suppressed: repeated system-level idea ({ideas})",
                    exceptional,
                )
        else:
            self._record_callout_decision(body, "scan", False, "no noteworthy scan criteria matched", [])

        if (not primary_dispatched and self._biology_callouts_enabled() and body.landable is True and
                body.biological_signals >= self._minimum_bio_signals()):
            bio_reason = [f"{body.biological_signals} biological signal{'s' if body.biological_signals != 1 else ''}"]
            if body.confirmed_genuses:
                bio_reason.append("confirmed genera: " + ", ".join(body.confirmed_genuses))
            outcome = self._dispatch_target_callout(body, "biology", bio_reason)
            self._record_callout_decision(body, "biology", True, outcome, bio_reason)

    # ------------------------------------------------------------------
    # Startup reconstruction
    # ------------------------------------------------------------------

    def _prime_from_history(self):
        if self._helper is None:
            return
        try:
            manager = getattr(self._helper, "_event_manager", None)
            if manager is None:
                return
            events, states = manager.get_current_state()

            # Find most recent concrete location event first.
            game_events = [
                e for e in (events or [])
                if getattr(e, "kind", None) == "game" and isinstance(getattr(e, "content", None), dict)
            ]
            location_idx = -1
            for idx in range(len(game_events) - 1, -1, -1):
                content = game_events[idx].content
                if content.get("event") in ("FSDJump", "Location", "CarrierJump"):
                    name = _clean(content.get("StarSystem") or content.get("SystemName"))
                    if name:
                        self._reset_system(
                            name,
                            _safe_int(content.get("SystemAddress")),
                            self._extract_star_pos(content),
                        )
                        location_idx = idx
                        break

            # If no event gave location, search projected state conservatively.
            if not self._system_name:
                self._prime_location_from_state(states)

            # Rebuild only the current-system slice after the last location event.
            start = max(0, location_idx)
            for event in game_events[start:]:
                content = event.content
                if content.get("event") in ("FSDJump", "Location", "CarrierJump"):
                    name = _clean(content.get("StarSystem") or content.get("SystemName"))
                    if name and self._system_name and name.casefold() != self._system_name.casefold():
                        continue
                self._consume_game_event(content, rebuilding=True)

            log(
                "info",
                f"TARS Explorer reconstructed {len(self._bodies)} bodies in {self._system_name or 'unknown system'}",
            )
        except Exception as exc:
            log("warn", f"TARS Explorer history reconstruction failed: {exc}")

    def _prime_location_from_state(self, states: Any):
        best: tuple[int, str, int | None, tuple[float, float, float] | None] | None = None

        def walk(node: Any, path: tuple[str, ...] = ()):
            nonlocal best
            node = self._as_dict(node)
            if isinstance(node, dict):
                addr = None
                star_pos = None
                for k, v in node.items():
                    nk = str(k).replace("_", "").casefold()
                    if nk in ("systemaddress", "staraddress"):
                        addr = _safe_int(v)
                    elif nk == "starpos" and isinstance(v, (list, tuple)) and len(v) >= 3:
                        vals = tuple(_safe_float(x) for x in v[:3])
                        if not any(x is None for x in vals):
                            star_pos = vals  # type: ignore[assignment]
                for k, v in node.items():
                    nk = str(k).replace("_", "").casefold()
                    name = _clean(v) if isinstance(v, str) else ""
                    score = 0
                    if nk in ("starsystem", "currentsystem", "currentstarsystem"):
                        score = 100
                    elif nk in ("systemname", "starsystemname"):
                        score = 50
                    path_text = "/".join(path + (str(k),)).casefold()
                    if any(x in path_text for x in ("route", "target", "destination", "waypoint")):
                        score -= 120
                    if score > 0 and name:
                        candidate = (score, name, addr, star_pos)
                        if best is None or candidate[0] > best[0]:
                            best = candidate
                    nested = self._as_dict(v)
                    if isinstance(nested, (dict, list, tuple)):
                        walk(nested, path + (str(k),))
            elif isinstance(node, (list, tuple)):
                for i, item in enumerate(node):
                    walk(item, path + (str(i),))

        walk(states)
        if best:
            _, name, address, pos = best
            self._reset_system(name, address, pos)

    # ------------------------------------------------------------------
    # Journal ingestion
    # ------------------------------------------------------------------

    def _observe_event(self, event: Any, context: dict):
        if getattr(event, "kind", None) != "game":
            return
        content = getattr(event, "content", None)
        if not isinstance(content, dict):
            return
        self._consume_game_event(content, rebuilding=False)

    def _consume_game_event(self, content: dict, rebuilding: bool = False):
        event = content.get("event")

        if event == "StartJump":
            # If COVAS exposes StartJump, this is the last sensible moment for an
            # unfinished-target reminder. Never emit an old-system warning after FSDJump.
            if not rebuilding and _clean(content.get("JumpType")).casefold() == "hyperspace":
                unfinished = self._unfinished_targets()
                if unfinished:
                    self._dispatch_milestone(
                        "unfinished_target",
                        {"departing_system": self._system_name, "targets": unfinished[:3]},
                        f"departure:{self._system_name}",
                    )
            return

        if event in ("FSDJump", "Location", "CarrierJump"):
            name = _clean(content.get("StarSystem") or content.get("SystemName"))
            if name:
                self._reset_system(
                    name,
                    _safe_int(content.get("SystemAddress")),
                    self._extract_star_pos(content),
                )
            return

        if not self._belongs_to_current_system(content):
            return

        if event == "ApproachBody":
            self._current_body_name = _clean(content.get("Body") or content.get("BodyName"))
            self._current_body_id = _safe_int(content.get("BodyID"))
            self._body_context_state = "approaching"
            if self._current_body_name or self._current_body_id is not None:
                body = self._get_body(self._current_body_name, self._current_body_id)
                reasons = self._automatic_value_reasons(body)
                if not rebuilding and reasons:
                    self._dispatch_milestone(
                        "approach_noteworthy",
                        {
                            "body": self._display_name(body),
                            "reasons": reasons,
                            "mapped": body.dss_mapped,
                            "biological_signals": body.biological_signals,
                            "confirmed_genuses": body.confirmed_genuses,
                        },
                        f"approach:{self._body_key(body.name, body.body_id)}",
                    )
            return

        if event == "LeaveBody":
            self._current_body_name = ""
            self._current_body_id = None
            self._body_context_state = ""
            return

        if event in ("FSSDiscoveryScan", "DiscoveryScan"):
            count = _safe_int(content.get("BodyCount") or content.get("Bodies"))
            if count is not None:
                self._expected_bodies = max(self._expected_bodies or 0, count)
            # Honk/body count is state only. Body count alone is never a speech opportunity.
            return

        if event == "FSSAllBodiesFound":
            self._fss_complete = True
            count = _safe_int(content.get("Count"))
            if count is not None:
                self._expected_bodies = count
            if not rebuilding:
                # The journal/COVAS event stream may still contain same-second Scan
                # events. Let that batch settle before building the summary.
                self._schedule_fss_completion()
            return

        if event == "Scan":
            body = self._consume_scan(content)
            self._maybe_dispatch_noteworthy(body, rebuilding=rebuilding)
            if not rebuilding and self._fss_complete and self._fss_completion_timer is not None:
                # Extend the quiet window for every trailing Scan. When the known
                # record count reaches FSS's expected count, no timer wait is needed.
                if self._expected_bodies is not None and len(self._bodies) >= self._expected_bodies:
                    self._flush_fss_completion()
                else:
                    self._schedule_fss_completion()
            return

        if event == "FSSBodySignals":
            body = self._get_body(_clean(content.get("BodyName")), _safe_int(content.get("BodyID")))
            bio = 0
            geo = 0
            for signal in content.get("Signals") or []:
                if not isinstance(signal, dict):
                    continue
                count = _safe_int(signal.get("Count")) or 0
                if _is_biological_signal(signal):
                    bio += count
                if _is_geological_signal(signal):
                    geo += count
            body.biological_signals = max(body.biological_signals, bio)
            body.geological_signals = max(body.geological_signals, geo)
            return

        # COVAS may expose this derived exploration event separately. FSSBodySignals
        # remains the authoritative journal payload for counts; keep this silent.
        if event == "FSSBiologicalSignals":
            return

        if event == "SAAScanComplete":
            body = self._get_body(_clean(content.get("BodyName")), _safe_int(content.get("BodyID")))
            body.dss_mapped = True
            probes = _safe_int(content.get("ProbesUsed"))
            target = _safe_int(content.get("EfficiencyTarget"))
            if probes is not None and target is not None and target > 0:
                body.dss_efficiency = probes <= target
            if not rebuilding:
                reasons = self._automatic_value_reasons(body)
                if reasons:
                    outcome = self._dispatch_body_milestone(
                        body,
                        "dss_complete",
                        {
                            "body": self._display_name(body),
                            "reasons": reasons,
                            "efficiency_bonus_met": body.dss_efficiency,
                            "biological_signals": body.biological_signals,
                            "confirmed_genuses": body.confirmed_genuses,
                        },
                        f"dss:{self._body_key(body.name, body.body_id)}",
                    )
                    self._record_callout_decision(body, "dss_complete", True, outcome, reasons)
                else:
                    self._record_callout_decision(
                        body, "dss_complete", False,
                        "suppressed: mapped body has no high-value or biology reason", []
                    )
            return

        if event == "SAASignalsFound":
            body = self._get_body(_clean(content.get("BodyName")), _safe_int(content.get("BodyID")))
            for signal in content.get("Signals") or []:
                if not isinstance(signal, dict):
                    continue
                count = _safe_int(signal.get("Count")) or 0
                if _is_biological_signal(signal):
                    body.biological_signals = max(body.biological_signals, count)
                if _is_geological_signal(signal):
                    body.geological_signals = max(body.geological_signals, count)
            genuses: list[str] = []
            for genus in content.get("Genuses") or []:
                if not isinstance(genus, dict):
                    continue
                name = _localized(genus, "Genus")
                if name and name not in genuses:
                    genuses.append(name)
            if genuses:
                body.confirmed_genuses = genuses
            return

        if event == "ScanOrganic":
            body_id = _safe_int(content.get("Body"))
            body = self._get_body("", body_id)
            genus = _localized(content, "Genus")
            species = _localized(content, "Species")
            variant = _localized(content, "Variant")
            scan_type = _clean(content.get("ScanType"))
            key = (genus or species or variant or f"body:{body_id}").casefold()
            progress = body.organics.get(key) or OrganicProgress(genus=genus)
            if genus:
                progress.genus = genus
            if species:
                progress.species = species
            if variant:
                progress.variant = variant
            progress.scan_type = scan_type
            progress.samples_seen += 1
            if scan_type.casefold() == "analyse":
                progress.complete = True
            body.organics[key] = progress
            if scan_type.casefold() == "analyse" and not rebuilding:
                organism = variant or species or genus or "organism"
                self._dispatch_target_callout(body, "organic_complete", [f"{organism} sampling complete"])
                if body.confirmed_genuses:
                    completed = {p.genus.casefold() for p in body.organics.values() if p.complete and p.genus}
                    missing = [g for g in body.confirmed_genuses if g.casefold() not in completed]
                    if not missing:
                        self._dispatch_milestone(
                            "biology_body_complete",
                            {"body": self._display_name(body), "confirmed_genuses": body.confirmed_genuses},
                            f"biology-complete:{self._body_key(body.name, body.body_id)}",
                        )
            return

        if event == "CodexEntry" and bool(content.get("IsNewEntry")):
            entry = {
                "name": _clean(content.get("Name_Localised") or content.get("Name")),
                "subcategory": _clean(content.get("SubCategory_Localised") or content.get("SubCategory")),
                "category": _clean(content.get("Category_Localised") or content.get("Category")),
                "body_id": _safe_int(content.get("BodyID")),
            }
            self._new_codex_entries.append(entry)
            self._new_codex_entries = self._new_codex_entries[-20:]
            if not rebuilding:
                self._dispatch_milestone("codex_new", entry, f"codex:{entry['name']}:{entry['body_id']}")

    def _consume_scan(self, content: dict) -> BodyState:
        name = _clean(content.get("BodyName"))
        body_id = _safe_int(content.get("BodyID"))
        body = self._get_body(name, body_id)
        body.body_type = _clean(content.get("BodyType"))
        body.planet_class = _clean(content.get("PlanetClass"))
        body.star_type = _clean(content.get("StarType"))
        body.parent_planet_id = None
        body.parent_star_id = None
        for parent in content.get("Parents") or []:
            if not isinstance(parent, dict):
                continue
            if "Planet" in parent:
                body.parent_planet_id = _safe_int(parent.get("Planet"))
            if "Star" in parent:
                body.parent_star_id = _safe_int(parent.get("Star"))
        body.terraform_state = _clean(content.get("TerraformState"))
        if "Landable" in content:
            body.landable = bool(content.get("Landable"))
        body.atmosphere = _clean(content.get("Atmosphere"))
        body.atmosphere_type = _clean(content.get("AtmosphereType"))
        body.volcanism = _clean(content.get("Volcanism"))
        body.gravity_ms2 = _safe_float(content.get("SurfaceGravity"))
        body.surface_temp_k = _safe_float(content.get("SurfaceTemperature"))
        body.surface_pressure_pa = _safe_float(content.get("SurfacePressure"))
        body.distance_ls = _safe_float(content.get("DistanceFromArrivalLS"))
        body.mass_em = _safe_float(content.get("MassEM"))
        body.radius_m = _safe_float(content.get("Radius"))
        body.orbital_period_s = _safe_float(content.get("OrbitalPeriod"))
        body.rotation_period_s = _safe_float(content.get("RotationPeriod"))
        body.axial_tilt_rad = _safe_float(content.get("AxialTilt"))
        body.eccentricity = _safe_float(content.get("Eccentricity"))
        body.semi_major_axis_m = _safe_float(content.get("SemiMajorAxis"))
        if "TidalLock" in content:
            body.tidal_lock = bool(content.get("TidalLock"))
        rings = content.get("Rings")
        if isinstance(rings, list):
            body.rings = [r for r in rings if isinstance(r, dict)]
        if "WasDiscovered" in content:
            body.was_discovered = bool(content.get("WasDiscovered"))
        if "WasMapped" in content:
            body.was_mapped = bool(content.get("WasMapped"))
        return body

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _planet_bodies(self) -> list[BodyState]:
        return [b for b in self._bodies.values() if b.is_planet]

    def _star_bodies(self) -> list[BodyState]:
        return [b for b in self._bodies.values() if bool(b.star_type)]

    def _belt_bodies(self) -> list[BodyState]:
        return [
            b for b in self._bodies.values()
            if not b.is_planet
            and not b.star_type
            and "belt cluster" in (b.name or "").casefold()
        ]

    def _system_composition(self) -> dict:
        planetary_bodies = self._planet_bodies()
        moons = [b for b in planetary_bodies if b.parent_planet_id is not None]
        planets = [b for b in planetary_bodies if b.parent_planet_id is None]
        stars = self._star_bodies()
        belts = self._belt_bodies()

        # Absence is only authoritative after FSSAllBodiesFound. Before that these
        # values mean "known so far" and must never be used to claim zero planets.
        confirmed = bool(self._fss_complete)
        unresolved = None
        if self._expected_bodies is not None:
            unresolved = max(0, self._expected_bodies - len(self._bodies))

        zero_planets = confirmed and not planets and not moons
        return {
            "stars": len(stars),
            "planets": len(planets),
            "moons": len(moons),
            "belt_clusters": len(belts),
            "known_body_records": len(self._bodies),
            "expected_bodies": self._expected_bodies,
            "unresolved_body_count": unresolved,
            "composition_confirmed": confirmed,
            "zero_planets_confirmed": zero_planets,
            "fss_complete": self._fss_complete,
            "fss_required": not confirmed,
        }

    def _display_name(self, body: BodyState) -> str:
        if body.name:
            if self._system_name and body.name.casefold().startswith(self._system_name.casefold()):
                suffix = body.name[len(self._system_name):].strip()
                return suffix or body.name
            return body.name
        return f"Body {body.body_id}" if body.body_id is not None else "Unknown body"

    def _interesting_reasons(self, body: BodyState) -> list[str]:
        reasons: list[str] = []
        special = body.interesting_world_type
        if special:
            reasons.append(special)
        if body.terraformable:
            reasons.append("terraformable")
        if body.biological_signals > 0:
            reasons.append(f"{body.biological_signals} biological signal{'s' if body.biological_signals != 1 else ''}")
        if body.confirmed_genuses:
            reasons.append("DSS-confirmed biology: " + ", ".join(body.confirmed_genuses))
        reasons.extend(self._exceptional_reasons(body))
        return list(dict.fromkeys(reasons))

    def _exceptional_reasons(self, body: BodyState) -> list[str]:
        """Conservative, body-family-aware, journal-only explorer-interest heuristics.

        A property must be genuinely interesting for this kind of body. Common cold,
        thin atmospheres, tidal lock and a single biological signal are modifiers,
        never standalone exceptional triggers.
        """
        reasons: list[str] = []
        modifiers: list[str] = []
        pc = body.planet_class.casefold().strip()
        g = body.gravity_ms2 / 9.80665 if body.gravity_ms2 is not None else None
        radius_km = body.radius_m / 1000.0 if body.radius_m is not None else None
        gas_giant = "gas giant" in pc or "water giant" in pc
        terrestrial = (not gas_giant) and any(x in pc for x in (
            "rocky", "metal rich", "high metal content", "earthlike", "earth-like",
            "water world", "ammonia world", "icy body"
        ))
        life_giant = any("gas giant with " + x in pc for x in (
            "water based life", "water-based life", "ammonia based life", "ammonia-based life"
        ))

        # Strong standalone class triggers. Describe them without claiming numeric rarity.
        if "gas giant with water based life" in pc or "gas giant with water-based life" in pc:
            reasons.append("gas giant with water-based life")
        if "gas giant with ammonia based life" in pc or "gas giant with ammonia-based life" in pc:
            reasons.append("gas giant with ammonia-based life")
        if "helium rich gas giant" in pc or "helium-rich gas giant" in pc:
            reasons.append("helium-rich gas giant")
        if "water giant" in pc:
            reasons.append("water giant")

        # Gravity: operationally important on landables. Gas giants need truly giant-specific extremes.
        if g is not None:
            if body.landable is True and g >= 2.0:
                reasons.append(f"{'very high-G' if g >= 2.5 else 'high-G'} landable: {g:.1f} g")
            elif gas_giant and g >= 20.0:
                reasons.append(f"exceptionally strong gravity for this gas giant: {g:.1f} g")
            elif terrestrial and g >= 4.0:
                reasons.append(f"extreme surface gravity: {g:.1f} g")
            elif body.landable is True and g <= 0.03:
                reasons.append(f"very low gravity landable: {g:.2f} g")

        # Temperature: no global 'cold' trigger. Very cold outer-system bodies are routine.
        # Only unusually hot visitable worlds, or truly extreme giants, speak by temperature alone.
        if body.surface_temp_k is not None:
            c = body.surface_temp_k - 273.15
            if body.landable is True and body.surface_temp_k >= 1000:
                reasons.append(f"extremely hot surface: about {c:.0f} degrees Celsius")
            elif gas_giant and body.surface_temp_k >= 2500:
                reasons.append(f"exceptionally hot gas giant: about {c:.0f} degrees Celsius")

        # Size/mass are terrestrial-class-relative. Moderate size alone on a
        # non-landable icy/rocky body is not worth interrupting for; use the old
        # thresholds on landables, but require a much stronger extreme elsewhere.
        if terrestrial and body.mass_em is not None:
            mass_limit = 5.0 if body.landable is True else 8.0
            if body.mass_em >= mass_limit:
                reasons.append(f"very massive terrestrial-class body: {body.mass_em:.1f} Earth masses")
        if terrestrial and radius_km is not None:
            radius_limit = 12000 if body.landable is True else 15000
            if radius_km >= radius_limit:
                reasons.append(f"very large terrestrial-class body: about {radius_km:,.0f} km radius")

        # Orbital curiosities remain available in body details, but ordinary short
        # periods, fast rotation and axial tilt are not worth interrupting a route.
        # Only an extreme eccentric orbit remains a standalone automatic curiosity.
        if body.eccentricity is not None and body.eccentricity >= 0.95:
            reasons.append(f"extremely eccentric orbit: {body.eccentricity:.2f}")

        # Rings are class-aware. Terrestrial rings and rings on life-bearing giants are useful facts.
        if body.rings and terrestrial:
            reasons.append("has a ring system")
        elif body.rings and life_giant:
            reasons.append("has a ring system")
        if len(body.rings) >= 2:
            # Multiple rings enrich an already-interesting giant, but ordinary
            # gas giants do not get an automatic callout merely for having two.
            if terrestrial or life_giant or reasons:
                reasons.append(f"has {len(body.rings)} ring systems")
        elif len(body.rings) == 1 and body.radius_m and body.radius_m > 0:
            outer = _safe_float(body.rings[0].get("OuterRad"))
            ratio = outer / body.radius_m if outer else None
            if ratio and ratio >= (15 if terrestrial else 25):
                reasons.append(f"exceptionally broad rings extending roughly {ratio:.0f} body radii")

        # Atmosphere pressure is never interesting merely because it is tiny. Dense pressure
        # is only a strong fact on a landable terrestrial-class body.
        if terrestrial and body.landable is True and body.surface_pressure_pa is not None:
            atm = body.surface_pressure_pa / 101325.0
            if atm >= 10:
                reasons.append(f"very dense atmosphere: roughly {atm:.0f} atmospheres")

        # Modifiers enrich a real callout but cannot create one.
        if body.tidal_lock is True and reasons and not gas_giant:
            modifiers.append("tidally locked")
        if body.biological_signals == 1 and reasons:
            modifiers.append("1 biological signal")

        return list(dict.fromkeys(reasons + modifiers))

    def _system_character(self) -> list[str]:
        planets = self._planet_bodies()
        tags: list[str] = []
        if sum(1 for b in planets if b.biological_signals > 0) >= 3:
            tags.append("biology-heavy")
        if sum(1 for b in planets if b.terraformable) >= 3:
            tags.append("terraformable-heavy")
        if sum(1 for b in planets if self._exceptional_reasons(b)) >= 2:
            tags.append("physically unusual")
        if any(b.interesting_world_type for b in planets):
            tags.append("contains high-interest world classes")
        if not tags:
            tags.append("ordinary from currently known exploration facts")
        return tags

    def _relative_highlights(self) -> list[str]:
        planets = self._planet_bodies()
        out: list[str] = []
        with_g = [b for b in planets if b.gravity_ms2 is not None]
        if len(with_g) >= 3:
            b=max(with_g,key=lambda x:x.gravity_ms2 or 0); g=(b.gravity_ms2 or 0)/9.80665
            if g >= 1.5: out.append(f"{self._display_name(b)} has the strongest known gravity in this system at {g:.2f} g")
        with_t=[b for b in planets if b.surface_temp_k is not None]
        if len(with_t) >= 3:
            hot=max(with_t,key=lambda x:x.surface_temp_k or 0)
            if (hot.surface_temp_k or 0)>=700: out.append(f"{self._display_name(hot)} is the hottest known planet/moon here at {hot.surface_temp_k:.0f} K")
        with_bio=[b for b in planets if b.biological_signals>0]
        if len(with_bio)>=2:
            best=max(with_bio,key=lambda x:x.biological_signals)
            out.append(f"{self._display_name(best)} has the most biological signals here: {best.biological_signals}")
        return out[:3]

    def _unfinished_targets(self) -> list[dict]:
        targets=[]
        for b in self._planet_bodies():
            important = bool(b.interesting_world_type or b.terraformable or b.biological_signals >= self._minimum_bio_signals() or self._exceptional_reasons(b))
            if not important: continue
            reasons=[]
            if (b.interesting_world_type or b.terraformable) and not b.dss_mapped and b.was_mapped is not True:
                reasons.append("not DSS mapped this visit")
            if b.confirmed_genuses:
                completed={p.genus.casefold() for p in b.organics.values() if p.complete and p.genus}
                missing=[g for g in b.confirmed_genuses if g.casefold() not in completed]
                if missing: reasons.append("confirmed biology not fully sampled: " + ", ".join(missing))
            if reasons:
                targets.append({"body":self._display_name(b),"why_noteworthy":self._interesting_reasons(b),"unfinished":reasons})
        return targets

    def _priority_score(self, body: BodyState) -> float:
        score = 0.0
        kind = (body.interesting_world_type or "").casefold()
        if "earth-like" in kind:
            score += 120
        elif "water world" in kind:
            score += 100
        elif "ammonia world" in kind:
            score += 95
        if body.terraformable:
            score += 45
        if body.biological_signals:
            score += 20 + min(body.biological_signals, 8) * 8
        if body.confirmed_genuses:
            score += len(body.confirmed_genuses) * 6
            if any("stratum" in g.casefold() for g in body.confirmed_genuses):
                score += 18
        if body.landable and body.biological_signals:
            score += 5
        score += min(40, len(self._exceptional_reasons(body)) * 12)
        if body.dss_mapped:
            score -= 8
        return score

    def _body_payload(self, body: BodyState) -> dict:
        sampled = []
        for progress in body.organics.values():
            sampled.append({
                "genus": progress.genus or None,
                "species": progress.species or None,
                "variant": progress.variant or None,
                "scan_type": progress.scan_type or None,
                "complete": progress.complete,
            })
        return {
            "body": self._display_name(body),
            "full_name": body.name or None,
            "body_id": body.body_id,
            "planet_class": body.planet_class or None,
            "terraformable": body.terraformable,
            "terraform_state": body.terraform_state or None,
            "landable": body.landable,
            "atmosphere": body.atmosphere or body.atmosphere_type or None,
            "volcanism": body.volcanism or None,
            "gravity_g": (round(body.gravity_ms2 / 9.80665, 3) if body.gravity_ms2 is not None else None),
            "surface_temperature_k": body.surface_temp_k,
            "surface_pressure_pa": body.surface_pressure_pa,
            "mass_earths": body.mass_em,
            "radius_km": (round(body.radius_m / 1000.0, 1) if body.radius_m is not None else None),
            "orbital_period_hours": (round(body.orbital_period_s / 3600.0, 3) if body.orbital_period_s else None),
            "rotation_period_hours": (round(abs(body.rotation_period_s) / 3600.0, 3) if body.rotation_period_s else None),
            "eccentricity": body.eccentricity,
            "axial_tilt_degrees": (round(math.degrees(body.axial_tilt_rad), 2) if body.axial_tilt_rad is not None else None),
            "tidal_lock": body.tidal_lock,
            "rings": body.rings,
            "exceptional_properties": self._exceptional_reasons(body),
            "distance_from_arrival_ls": body.distance_ls,
            "was_discovered_before_scan": body.was_discovered,
            "was_mapped_before_scan": body.was_mapped,
            "biological_signals": body.biological_signals,
            "geological_signals": body.geological_signals,
            "dss_mapped_this_session": body.dss_mapped,
            "dss_efficiency_bonus_met": body.dss_efficiency,
            "confirmed_genuses": body.confirmed_genuses,
            "organic_scans": sampled,
            "noteworthy_reasons": self._interesting_reasons(body),
        }

    def _resolve_body(self, requested: str) -> BodyState | None:
        q = _clean(requested).casefold()
        if not q:
            if self._current_body_name or self._current_body_id is not None:
                return self._get_body(self._current_body_name, self._current_body_id)
            return None
        exact = []
        suffix = []
        contains = []
        for body in self._bodies.values():
            name = _clean(body.name).casefold()
            display = self._display_name(body).casefold()
            if q in (name, display):
                exact.append(body)
            elif display.endswith(q) or name.endswith(q):
                suffix.append(body)
            elif q in display or q in name:
                contains.append(body)
        for group in (exact, suffix, contains):
            if len(group) == 1:
                return group[0]
        return exact[0] if exact else suffix[0] if suffix else contains[0] if contains else None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _action_system_summary(self, args: EmptyArgs, context: dict) -> str:
        if not self._system_name:
            return self._json({
                "ok": False,
                "error_code": "CURRENT_SYSTEM_UNKNOWN",
                "message": "TARS Explorer cannot determine the current system.",
                "assistant_instruction": "Say the current system could not be resolved. Do not guess.",
            })

        planets = self._planet_bodies()
        notable = [b for b in planets if self._interesting_reasons(b)]
        notable.sort(key=lambda b: self._priority_score(b), reverse=True)

        counts = {
            "known_planets_or_moons": len(planets),
            "earth_like_worlds": sum(1 for b in planets if b.interesting_world_type == "Earth-like world"),
            "water_worlds": sum(1 for b in planets if b.interesting_world_type == "Water world"),
            "ammonia_worlds": sum(1 for b in planets if b.interesting_world_type == "Ammonia world"),
            "terraformable_bodies": sum(1 for b in planets if b.terraformable),
            "bodies_with_biological_signals": sum(1 for b in planets if b.biological_signals > 0),
            "total_biological_signals": sum(b.biological_signals for b in planets),
            "dss_mapped_bodies": sum(1 for b in planets if b.dss_mapped),
        }

        return self._json({
            "ok": True,
            "system": self._system_name,
            "system_address": self._system_address,
            "coordinates": self._star_pos,
            "fss_complete": self._fss_complete,
            "expected_bodies": self._expected_bodies,
            "known_body_records": len(self._bodies),
            "counts": counts,
            "noteworthy_bodies": [self._body_payload(b) for b in notable[:20]],
            "current_body_context": {
                "body": self._current_body_name or None,
                "body_id": self._current_body_id,
                "state": self._body_context_state or None,
            },
            "new_codex_entries_this_system": self._new_codex_entries,
            "system_character": self._system_character(),
            "relative_highlights": self._relative_highlights(),
            "unfinished_targets": self._unfinished_targets(),
            "assistant_instruction": (
                "Answer from these facts only. Lead with high-value/noteworthy worlds and biology. "
                "Water worlds, Earth-like worlds, ammonia worlds and terraformables must not be omitted when present. "
                "FSS complete means all bodies were identified; it does NOT mean they were DSS mapped. Use system_composition to distinguish stars, planets, moons and belt clusters; before composition_confirmed, counts are known-so-far only. "
                "If the journal state is incomplete, say 'known so far' rather than inventing missing facts."
            ),
        })

    def _action_priority_targets(self, args: EmptyArgs, context: dict) -> str:
        ranked = [b for b in self._planet_bodies() if self._priority_score(b) > 0]
        ranked.sort(key=lambda b: self._priority_score(b), reverse=True)
        targets = []
        for body in ranked[:15]:
            targets.append({
                "body": self._display_name(body),
                "priority_reasons": self._interesting_reasons(body),
                "mapped": body.dss_mapped,
                "biology_confirmed": body.confirmed_genuses,
                "biological_signals": body.biological_signals,
            })
        return self._json({
            "ok": True,
            "system": self._system_name or None,
            "fss_complete": self._fss_complete,
            "targets": targets,
            "assistant_instruction": (
                "Recommend targets in the returned order, but explain the concrete reasons rather than quoting an internal score. "
                "For already DSS-mapped bodies, say they are mapped. For biology, distinguish signal count from DSS-confirmed genera."
            ),
        })

    def _action_body_info(self, args: BodyArgs, context: dict) -> str:
        body = self._resolve_body(args.body_name)
        if body is None:
            return self._json({
                "ok": False,
                "error_code": "BODY_NOT_FOUND",
                "system": self._system_name or None,
                "requested": args.body_name,
                "known_bodies": [self._display_name(b) for b in self._planet_bodies()[:60]],
                "assistant_instruction": "Say that body is not present in the current Explorer journal state. Do not guess.",
            })
        return self._json({
            "ok": True,
            "system": self._system_name,
            "body": self._body_payload(body),
            "assistant_instruction": "Use these journal-derived facts only. Missing fields are unknown, not absent.",
        })

    def _action_biology(self, args: BodyArgs, context: dict) -> str:
        bodies: list[BodyState]
        if _clean(args.body_name):
            body = self._resolve_body(args.body_name)
            if body is None:
                return self._json({
                    "ok": False,
                    "error_code": "BODY_NOT_FOUND",
                    "requested": args.body_name,
                    "assistant_instruction": "Say that Explorer has no journal state for that body. Do not guess biology.",
                })
            bodies = [body]
        else:
            bodies = [b for b in self._planet_bodies() if b.biological_signals > 0 or b.confirmed_genuses or b.organics]
            bodies.sort(key=lambda b: (b.biological_signals, len(b.confirmed_genuses)), reverse=True)

        payload = []
        for body in bodies:
            completed_genera = {
                p.genus.casefold() for p in body.organics.values() if p.complete and p.genus
            }
            remaining = [
                g for g in body.confirmed_genuses
                if g.casefold() not in completed_genera
            ]
            payload.append({
                "body": self._display_name(body),
                "biological_signals": body.biological_signals,
                "dss_mapped": body.dss_mapped,
                "confirmed_genuses": body.confirmed_genuses,
                "sampled": [
                    {
                        "genus": p.genus or None,
                        "species": p.species or None,
                        "variant": p.variant or None,
                        "complete": p.complete,
                    }
                    for p in body.organics.values()
                ],
                "confirmed_genuses_not_yet_completed": remaining,
                "prediction_status": (
                    "confirmed_genus_data_available" if body.confirmed_genuses
                    else "signals_only_no_reliable_species_prediction"
                ),
            })

        return self._json({
            "ok": True,
            "system": self._system_name or None,
            "bodies": payload,
            "bioinsights_direct_bridge": False,
            "bioinsights_note": (
                "BioInsights does not currently expose a supported COVAS-facing data API. "
                "This build uses Elite journal facts directly and never fabricates BioInsights predictions."
            ),
            "assistant_instruction": (
                "If DSS-confirmed genera are present, call them confirmed. If only signal counts are present, "
                "do not invent genus/species predictions. Explain sampled vs remaining confirmed genera when known."
            ),
        })

    def _action_progress(self, args: EmptyArgs, context: dict) -> str:
        planets = self._planet_bodies()
        priority = [b for b in planets if self._priority_score(b) > 0]
        unmapped_priority = [b for b in priority if not b.dss_mapped]
        bio_bodies = [b for b in planets if b.biological_signals > 0]
        bio_remaining = []
        for body in bio_bodies:
            completed = {p.genus.casefold() for p in body.organics.values() if p.complete and p.genus}
            remaining = [g for g in body.confirmed_genuses if g.casefold() not in completed]
            if remaining:
                bio_remaining.append({"body": self._display_name(body), "remaining_confirmed_genuses": remaining})
            elif body.biological_signals > 0 and not body.confirmed_genuses:
                bio_remaining.append({
                    "body": self._display_name(body),
                    "remaining_confirmed_genuses": None,
                    "status": "biology signals detected but DSS genus list not yet known",
                })

        return self._json({
            "ok": True,
            "system": self._system_name or None,
            "fss_complete": self._fss_complete,
            "expected_bodies": self._expected_bodies,
            "known_body_records": len(self._bodies),
            "unmapped_noteworthy_targets": [
                {"body": self._display_name(b), "reasons": self._interesting_reasons(b)}
                for b in unmapped_priority[:20]
            ],
            "biology_remaining": bio_remaining,
            "assistant_instruction": (
                "Never equate FSS complete with fully mapped. State separately whether all bodies are identified, "
                "whether noteworthy targets remain unmapped, and whether confirmed biology remains unsampled."
            ),
        })

    def _action_diagnostics(self, args: EmptyArgs, context: dict) -> str:
        planets = self._planet_bodies()
        return self._json({
            "ok": bool(self._system_name),
            "plugin": "TARS Explorer",
            "version": "1.4.4",
            "system": self._system_name or None,
            "system_address": self._system_address,
            "coordinates": self._star_pos,
            "expected_bodies": self._expected_bodies,
            "known_body_records": len(self._bodies),
            "known_planets_or_moons": len(planets),
            "fss_complete": self._fss_complete,
            "bodies_with_biology": sum(1 for b in planets if b.biological_signals > 0),
            "bodies_with_dss_confirmed_genera": sum(1 for b in planets if b.confirmed_genuses),
            "organic_species_records": sum(len(b.organics) for b in planets),
            "automatic_callouts_enabled": self._auto_callouts_enabled(),
            "biology_callouts_enabled": self._biology_callouts_enabled(),
            "minimum_bio_signals": self._minimum_bio_signals(),
            "automatic_callouts_dispatched_this_system": len(self._announced_callouts),
            "recent_callout_decisions": self._callout_decisions[-10:],
            "last_callout_decision": self._callout_decisions[-1] if self._callout_decisions else None,
            "current_body_context": {
                "body": self._current_body_name or None,
                "body_id": self._current_body_id,
                "state": self._body_context_state or None,
            },
            "assistant_instruction": (
                "Report the current system, whether live journal state is populated, automatic callout settings, and recent_callout_decisions. "
                "If asked why a scan was not called out, quote the matching recorded outcome/reason. Never invent a suppression reason. "
                "Do not call FSS completion 'fully mapped'."
            ),
        })
