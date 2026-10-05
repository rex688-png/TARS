from __future__ import annotations

import copy
import importlib.util
import random
import re
import sys
import time
from pathlib import Path

from lib.Logger import ModelUsageStats, log


def _load_base_module():
    path = Path(__file__).with_name("TARSChatter.py")
    name = "_tars_chatter_base_session_guard"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load base Chatter from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_base_module = _load_base_module()
_BaseChatter = _base_module.TARSChatter


class TARSChatter(_BaseChatter):
    """Full-session hardening layer for TARS Chatter/Director.

    Adds long-session premise suppression, docked/idle pacing, direct-question
    priority, routine event silence, stronger station/service certainty rules and
    one safe retry for transient failures on direct commander requests.
    """

    ROUTE_CONFIRMATION_PATTERNS = (
        r"\b(?:route planner|nav(?:igation)? computer|navigation|route map|galaxy map)\b.*\b(?:confirm|confirmed|knows|located|settled|sorted|found)\b",
        r"\b(?:confirm|confirmed|confirmation|located|settled|sorted)\b.*\b(?:route|planner|navigation|map|location|station|system|destination)\b",
        r"\b(?:station|system|destination|location)\b.*\b(?:is|now)\s+(?:confirmed|settled|located)\b",
    )

    # Dock/undock may still inspire a rare contextual line, but no longer at the
    # relatively high rates used before the long-session audit.
    EVENT_OPPORTUNITIES = {
        **_BaseChatter.EVENT_OPPORTUNITIES,
        "Docked": {"chance": 0.04, "topics": ("human_systems", "ship", "economics")},
        "Undocked": {"chance": 0.03, "topics": ("navigation", "ship", "human_systems")},
    }

    MEMORY_SUMMARY_MARKER = (
        "summarizes events and conversation into short concise notes for long-term memory storage"
    )

    def __init__(self, plugin_manifest):
        super().__init__(plugin_manifest)
        self._session_docked = False
        self._last_any_game_event_at = 0.0
        self._direct_question_pending_at = 0.0
        self._route_confirmation_last_at = 0.0
        self._commander_correction_seen_at = 0.0
        # Session-only diagnostic copy. It is intentionally NOT injected into the
        # system prompt; the model gets only the generic correction-priority rule.
        self._recent_commander_correction = ""

    def _assistant_busy(self) -> bool:
        assistant = self._covas_assistant()
        return bool(
            assistant is not None
            and (
                getattr(assistant, "reply_pending", False)
                or getattr(assistant, "is_replying", False)
            )
        )

    def _direct_question_pending(self) -> bool:
        return bool(
            self._direct_question_pending_at
            and time.time() - self._direct_question_pending_at < 120.0
        )

    @classmethod
    def _route_confirmation_premise(cls, text: str) -> bool:
        low = str(text or "").casefold()
        return any(re.search(pattern, low, flags=re.I) for pattern in cls.ROUTE_CONFIRMATION_PATTERNS)

    @staticmethod
    def _looks_like_correction(text: str) -> bool:
        low = str(text or "").strip().casefold()
        if not low or low.startswith("["):
            return False
        markers = (
            "turns out", "actually it", "actually, it", "neither of them",
            "that's wrong", "thats wrong", "you got that wrong", "not there",
            "it was in ", "it's in ", "its in ", "no, it ", "no it ",
            "wrong station", "wrong system", "wrong broker", "wrong trader",
        )
        return any(marker in low for marker in markers)

    def _observe_event(self, event, context):
        kind = getattr(event, "kind", "")
        content = getattr(event, "content", None)
        now = time.time()

        if kind in ("user", "user_speaking"):
            self._direct_question_pending_at = now
            if kind == "user" and isinstance(content, str) and self._looks_like_correction(content):
                self._commander_correction_seen_at = now
                self._recent_commander_correction = " ".join(content.split())[:500]
        elif kind == "assistant":
            self._direct_question_pending_at = 0.0
            if self._route_confirmation_premise(str(content or "")):
                self._route_confirmation_last_at = now
        elif kind == "game" and not getattr(event, "historic", False):
            self._last_any_game_event_at = now
            if isinstance(content, dict):
                name = str(content.get("event", "") or "")
                if name == "Docked":
                    self._session_docked = True
                elif name in ("Undocked", "FSDJump", "StartJump"):
                    self._session_docked = False

        super()._observe_event(event, context)

    def _chatter_quality_reason(self, candidate):
        reason = super()._chatter_quality_reason(candidate)
        if reason:
            return reason
        if self._route_confirmation_premise(candidate):
            if self._route_confirmation_last_at and time.time() - self._route_confirmation_last_at < 4 * 3600:
                return "route/location confirmation premise already used this session"
        return None

    def _delay(self):
        base = super()._delay()
        now = time.time()

        # While parked, silence is more natural than inventing a new observation
        # every few minutes. Idle flight also gets a larger interval when nothing
        # meaningful has happened for ten minutes.
        if self._session_docked:
            return max(base, random.uniform(900.0, 1500.0))
        if self._last_any_game_event_at and now - self._last_any_game_event_at > 600.0:
            return max(base, random.uniform(720.0, 1200.0))
        return base

    def _should_reply_to_chatter(self, event):
        # Do not check reply_pending here: some COVAS versions mark the event reply
        # pending before should_reply_check runs, which would make Chatter suppress
        # its own event. Explicit commander activity is the reliable priority lock.
        if self._direct_question_pending():
            log("info", "TARS Chatter suppressed: commander reply has priority.")
            return False
        return super()._should_reply_to_chatter(event)

    def _inject_director(self, messages, system_index):
        directed = super()._inject_director(messages, system_index)
        idx = self._main_covas_system_index(directed)
        if idx is None:
            return directed

        correction_rule = ""
        if self._commander_correction_seen_at and time.time() - self._commander_correction_seen_at < 6 * 3600:
            correction_rule = (
                "\nA factual commander correction occurred during this session. "
                "Treat the latest direct commander statement in the conversation as higher priority than older memory; "
                "do not revive the superseded station/service/location claim without fresh tool evidence.\n"
            )

        regression_rules = """

TARS FULL-SESSION ACCURACY GUARD:
- A direct commander correction immediately invalidates the earlier conflicting station, service, location or route conclusion. Do not repeat the superseded result as confirmed, even if an older memory says otherwise.
- Never promote an unverified candidate station/service into a confirmed one without fresh action evidence that explicitly contains the required service and subtype.
- Material Trader subtype and Technology Broker subtype must be explicit. Economy, station type, or an earlier generic result is not proof.
- A distance returned by a station/service search belongs to that search origin at that time. If the ship has moved to another system, re-query or recompute before quoting the old distance as current.
- Direct commander questions outrank Explorer, Navigator and Chatter ambient events. Finish the asked-for answer before any unsolicited milestone or companion remark.
- Routine docking, undocking, mass-lock and bare InDanger state changes are not worth narration unless there is a concrete actionable hazard or the commander asked about them.
"""
        directed[idx]["content"] = str(directed[idx].get("content", "")) + regression_rules + correction_rule
        return directed

    def _latest_meaningful_user_content(self, messages) -> str:
        for msg in reversed(messages or []):
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            content = str(msg.get("content", "") or "").strip()
            if not content:
                continue
            if content.startswith(("[Ship logbook", "# ", "Current status:", "[Current status")):
                continue
            return content
        return ""

    def _is_direct_user_turn(self, messages) -> bool:
        content = self._latest_meaningful_user_content(messages)
        if not content:
            return False
        return not content.startswith((
            "[Game Event",
            "[IMPORTANT Game Event",
            "[Status Event",
            "[External Event",
        ))

    def _is_memory_summary_call(self, messages) -> bool:
        if not isinstance(messages, list) or len(messages) < 2:
            return False
        system = messages[0] if isinstance(messages[0], dict) else {}
        user = messages[1] if isinstance(messages[1], dict) else {}
        system_text = str(system.get("content", "") or "").casefold()
        user_text = str(user.get("content", "") or "").casefold()
        return (
            system.get("role") == "system"
            and self.MEMORY_SUMMARY_MARKER in system_text
            and user.get("role") == "user"
            and "<conversation>" in user_text
            and "long-term memory storage" in user_text
        )

    def _harden_memory_summary(self, messages):
        """Add conflict-resolution rules only to COVAS long-term summarization.

        Current COVAS summarizes in a background thread after assistant replies. The
        source conversation already contains the correction; this guard only tells
        the summarizer how to resolve contradictions. It never copies raw commander
        text into a system prompt and leaves agents/action verification untouched.
        """
        if not self._is_memory_summary_call(messages):
            return messages
        if not self._commander_correction_seen_at:
            return messages
        if time.time() - self._commander_correction_seen_at >= 6 * 3600:
            return messages

        hardened = copy.deepcopy(messages)
        hardened[0]["content"] = str(hardened[0].get("content", "")) + (
            "\nWhen the conversation contains conflicting factual claims, preserve only the latest explicit "
            "commander correction or later live game fact. Do not store an earlier superseded station, service, "
            "location, route, docking-state, or similar claim as confirmed. If the later evidence is only a "
            "correction and no independent verification exists, record the correction as the commander's latest "
            "information rather than upgrading it to external confirmation."
        )
        return hardened

    def _routine_noise_kind(self, messages) -> str | None:
        content = self._latest_meaningful_user_content(messages)
        if not content:
            return None
        low = content.casefold()

        if content.startswith("[Status Event") and "indanger" in low:
            actionable = (
                "under attack", "hull damage", "heat warning", "overheat",
                "interdict", "taking damage", "collision", "shields failing",
                "canopy", "oxygen"
            )
            if not any(term in low for term in actionable):
                return "bare InDanger status"

        if content.startswith(("[Game Event", "[IMPORTANT Game Event")):
            routine_terms = (
                "docking request", "docking requested", "docking granted",
                "docking permission", "docked at", "has docked", "undocked from",
                "has undocked", "mass lock", "masslocked", "mass lock escaped",
            )
            if any(term in low for term in routine_terms):
                return "routine docking/mass-lock event"

        return None

    @staticmethod
    def _transient_llm_error(exc: Exception) -> bool:
        text = str(exc or "").casefold()
        markers = (
            "unknown error", "timeout", "timed out", "temporarily unavailable",
            "connection reset", "connection error", "server error", "bad gateway",
            "service unavailable", "internal server error", "502", "503", "504",
        )
        return any(marker in text for marker in markers)

    def _install_output_director(self):
        super()._install_output_director()
        model = self._llm_model
        if model is None or self._guard_wrapper is None:
            return

        inner = model.generate

        def resilient_generate(messages, tools=None, tool_choice=None):
            # The model object is also used for memory summaries/agents. Only the
            # main COVAS conversation is eligible for speech suppression or retry.
            is_main_turn = self._main_covas_system_index(messages) is not None
            is_memory_summary = self._is_memory_summary_call(messages)
            call_messages = self._harden_memory_summary(messages) if is_memory_summary else messages

            if is_main_turn:
                noise = self._routine_noise_kind(messages)
                if noise:
                    log("info", f"TARS Director suppressed {noise}.")
                    return ("", None, ModelUsageStats())

            try:
                return inner(messages=call_messages, tools=tools, tool_choice=tool_choice)
            except Exception as exc:
                if is_main_turn and self._is_direct_user_turn(messages) and self._transient_llm_error(exc):
                    log("warn", "TARS Director retrying one transient LLM failure for a direct request.")
                    time.sleep(0.15)
                    return inner(messages=call_messages, tools=tools, tool_choice=tool_choice)
                raise

        # Base restore logic checks _guard_wrapper identity, so make the resilient
        # wrapper the installed guard while preserving _original_generate.
        self._guard_wrapper = resilient_generate
        model.generate = resilient_generate
        log("info", "TARS Chatter full-session guard installed.")


# Avoid exposing the imported base class as another plugin candidate.
del _BaseChatter
