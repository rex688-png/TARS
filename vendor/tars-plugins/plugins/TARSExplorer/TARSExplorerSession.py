from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

from lib.Logger import log


def _load_base_module():
    path = Path(__file__).with_name("TARSExplorer.py")
    name = "_tars_explorer_base_session_guard"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load base Explorer from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_base_module = _load_base_module()
_BaseExplorer = _base_module.TARSExplorer


class TARSExplorer(_BaseExplorer):
    """Session-level speech hardening for Explorer 1.4.x."""

    def __init__(self, plugin_manifest):
        super().__init__(plugin_manifest)
        self._direct_question_pending_at = 0.0
        self._zero_planet_signatures: set[tuple[int, int]] = set()

    def _direct_question_pending(self) -> bool:
        return bool(
            self._direct_question_pending_at
            and time.time() - self._direct_question_pending_at < 120.0
        )

    def _observe_event(self, event, context):
        kind = getattr(event, "kind", "")
        now = time.time()

        if kind in ("user", "user_speaking"):
            self._direct_question_pending_at = now
            return
        if kind == "assistant":
            self._direct_question_pending_at = 0.0
            return
        if kind in ("assistant_speaking", "assistant_acting"):
            return

        super()._observe_event(event, context)

    def _should_reply_to_target(self, event):
        if not super()._should_reply_to_target(event):
            return False
        # Some COVAS builds mark a plugin-event reply pending before this hook is
        # evaluated. Only explicit commander activity is safe as a priority lock.
        if self._direct_question_pending():
            log("info", "TARS Explorer suppressed proactive callout: commander reply has priority.")
            return False
        return True

    def _system_completion_worthy(self, payload: dict) -> bool:
        if not super()._system_completion_worthy(payload):
            return False

        composition = payload.get("system_composition") if isinstance(payload, dict) else None
        if not isinstance(composition, dict) or not composition.get("zero_planets_confirmed"):
            return True

        # Empty/star-only systems are useful to acknowledge occasionally, but the
        # same observation becomes noise quickly. Allow at most two distinct
        # star/belt compositions per COVAS session, and never repeat a signature.
        signature = (
            int(composition.get("stars") or 0),
            int(composition.get("belt_clusters") or 0),
        )
        if signature in self._zero_planet_signatures:
            log("info", f"TARS Explorer suppressed repeated zero-planet composition {signature}.")
            return False
        if len(self._zero_planet_signatures) >= 2:
            log("info", "TARS Explorer suppressed additional zero-planet wrap-up for session novelty.")
            return False

        self._zero_planet_signatures.add(signature)
        return True


# Avoid exposing the imported base class as another plugin candidate.
del _BaseExplorer
