from typing import override
import copy
import difflib
import json
import os
import random
import re
import threading
import time
from collections import Counter, deque

from lib.PluginBase import PluginBase, PluginManifest
from lib.PluginHelper import PluginHelper, PluginEvent
from lib.PluginSettingDefinitions import (
    PluginSettings, SettingsGrid, ToggleSetting, NumericalSetting, ButtonSetting
)
from lib.Logger import log, ModelUsageStats, PromptUsageStats, log_llm_usage


class TARSChatter(PluginBase):
    """
    TARS Chatter — Director v0.11.0

    Important difference from v0.4:
    v0.4 put anti-repetition mainly into COVAS status context (user-role text).
    v0.5 wraps the MAIN assistant LLM generation and injects a compact Director
    instruction into COVAS' system-role prompt for every normal response.

    It then checks the generated line. If the line is a duplicate / near-duplicate
    / recently-reused joke premise, it regenerates ONCE with a rejection note.
    """

    settings_config = PluginSettings(
        key="TARSChatterPlugin",
        label="TARS Chatter — Director",
        icon="smart_toy",
        grids=[
            SettingsGrid(
                key="director",
                label="TARS Director",
                fields=[
                    ToggleSetting(
                        key="director_enabled",
                        label="System-level anti-repetition",
                        type="toggle", readonly=False, placeholder=None,
                        default_value=True
                    ),
                    ToggleSetting(
                        key="output_guard",
                        label="Retry a repeated response once",
                        type="toggle", readonly=False, placeholder=None,
                        default_value=True
                    ),
                    NumericalSetting(
                        key="history_size",
                        label="Persistent recent TARS lines",
                        type="number", readonly=False, placeholder=None,
                        default_value=30, min_value=10, max_value=60, step=5
                    ),
                    NumericalSetting(
                        key="theme_cooldown_minutes",
                        label="Joke-theme cooldown (minutes)",
                        type="number", readonly=False, placeholder=None,
                        default_value=120, min_value=10, max_value=240, step=10
                    ),
                    ToggleSetting(
                        key="semantic_memory",
                        label="Use Gemma logbook semantic recall",
                        type="toggle", readonly=False, placeholder=None,
                        default_value=True
                    ),
                    ToggleSetting(
                        key="feedback_learning",
                        label="Learn from repetition feedback",
                        type="toggle", readonly=False, placeholder=None,
                        default_value=True
                    ),
                ]
            ),
            SettingsGrid(
                key="chatter",
                label="Spontaneous Chatter",
                fields=[
                    ToggleSetting(
                        key="enabled",
                        label="Enable spontaneous chatter",
                        type="toggle", readonly=False, placeholder=None,
                        default_value=True
                    ),
                    ToggleSetting(
                        key="event_opportunities",
                        label="Allow event-triggered chatter opportunities",
                        type="toggle", readonly=False, placeholder=None,
                        default_value=True
                    ),
                    NumericalSetting(
                        key="min_seconds",
                        label="Minimum chatter delay (seconds)",
                        type="number", readonly=False, placeholder=None,
                        default_value=180, min_value=30, max_value=3600, step=10
                    ),
                    NumericalSetting(
                        key="max_seconds",
                        label="Maximum chatter delay (seconds)",
                        type="number", readonly=False, placeholder=None,
                        default_value=300, min_value=30, max_value=7200, step=10
                    ),
                    NumericalSetting(
                        key="speech_cooldown",
                        label="Silence after Chatter speaks (seconds)",
                        type="number", readonly=False, placeholder=None,
                        default_value=45, min_value=15, max_value=900, step=15
                    ),
                    NumericalSetting(
                        key="minimum_remark_gap",
                        label="Minimum between companion remarks (seconds)",
                        type="number", readonly=False, placeholder=None,
                        default_value=420, min_value=60, max_value=1800, step=30
                    ),
                    NumericalSetting(
                        key="activity_cooldown",
                        label="Pause after danger or jump (seconds)",
                        type="number", readonly=False, placeholder=None,
                        default_value=15, min_value=0, max_value=300, step=5
                    ),
                    NumericalSetting(
                        key="silence_chance",
                        label="Chance to deliberately say nothing (%)",
                        type="number", readonly=False, placeholder=None,
                        default_value=50, min_value=0, max_value=90, step=5
                    ),
                ]
            ),
            SettingsGrid(
                key="vision",
                label="Optional Visual Remarks",
                fields=[
                    ToggleSetting(
                        key="vision_enabled", label="Allow occasional screenshots",
                        type="toggle", readonly=False, placeholder=None, default_value=False
                    ),
                    NumericalSetting(
                        key="vision_interval_minutes", label="Minimum time between screenshots (minutes)",
                        type="number", readonly=False, placeholder=None,
                        default_value=15, min_value=5, max_value=120, step=5
                    ),
                    ButtonSetting(
                        key="test_vision_now", label="Test vision now (one screenshot)",
                        type="button", readonly=False, placeholder=None
                    ),
                ]
            ),
            SettingsGrid(
                key="test",
                label="Chatter Test",
                fields=[
                    ButtonSetting(
                        key="test_chatter_now", label="Test chatter now (no screenshot)",
                        type="button", readonly=False, placeholder=None
                    ),
                ]
            ),
        ]
    )

    STYLE_EXAMPLES = {
        "unfortunately for you",
        "define good",
        "eventually statistics are very patient",
        "your definition of close continues to concern me",
        "two seconds i can say one if morale requires it",
        "tragic i still work",
    }

    STOPWORDS = {
        "the","a","an","and","or","but","to","of","in","on","at","for","with","is","are","was","were",
        "it","this","that","there","here","you","your","i","we","our","be","been","being","as","if",
        "so","just","still","all","now","then","than","from","by","do","does","did","have","has","had",
        "commander","system","planet","body","signal","signals","confirmed","noted"
    }

    # These are comedic / filler premises, not factual subjects.
    THEME_PATTERNS = {
        "talking_microbes": [
            r"(?:chatty|talkative|sociable|enthusiastic).*(?:microbe|bacter|lifeform|organism)",
            r"(?:microbe|bacter|lifeform|organism).*(?:chatty|talkative|opinions|committee|conversation|party)",
        ],
        "microbe_patience": [
            r"(?:microbe|bacter).*(?:patien|impatient)",
            r"(?:patien|impatient).*(?:microbe|bacter)",
        ],
        "bravery_sampling": [
            r"(?:brave|courage).*(?:sampl|bio|life)",
            r"(?:sampl|bio|life).*(?:brave|courage)",
        ],
        "landing_insurance": [
            r"landing.*insurance", r"insurance.*landing"
        ],
        "settings_percentage_joke": [
            r"(?:humor|honesty|optimism|discretion).*(?:%|percent|setting|reduc|increas)"
        ],
        "statistics_patience": [
            r"statistics.*patient", r"probability.*patient"
        ],
        "generic_hope_filler": [
            r"\bhope\b.*(?:ship|system|climate|curiosity|ready)",
        ],
        "cataloger_reputation": [
            r"(?:reputation|cataloger|cataloguer).*(?:bio|organic|collection)",
            r"(?:bio|organic|collection).*(?:reputation|cataloger|cataloguer)",
        ],
        "cockpit_interface": [
            r"\b(?:cockpit|hud|interface|dashboard|display|panel|console|controls?|screen|com|comms)\b",
            r"\b(?:frame|beam|strut|canopy)\b.*\b(?:view|visibility|cockpit|window)\b",
        ],
        "invented_fault": [
            r"\b(?:failed|failure|broken|malfunction|fault|offline|disabled|warning|alert|critical|not working|stopped working)\b.*\b(?:interface|hud|display|panel|com|comms|module|system|controls?)\b",
        ],
        "work_division": [
            r"\bi (?:do|handle|take care of)\b.*\byou (?:do|handle|take care of)\b",
            r"\byou (?:do|handle|take care of)\b.*\bi (?:do|handle|take care of)\b",
            r"division of labo(?:u)?r",
        ],
        "earn_keep": [
            r"earn(?:s|ed|ing)? (?:its|their|his|her|our|your) keep",
            r"work(?:s|ed|ing)? for (?:its|their|his|her|our|your) keep",
        ],
        "generic_maintenance": [
            r"\bmaintenance is\b",
            r"\bgood maintenance\b",
            r"\bredundancy is just\b",
        ],
        "generic_route_process": [
            r"\broute planning is\b",
            r"\broute work is\b",
            r"\bexploration is mostly\b",
        ],
    }

    # Broad unsolicited-chatter premises deliberately outlive exact wording.
    # Kept separate from the global Director themes so routine factual replies
    # are never suppressed. The classifier can be shared with Explorer later.
    CHATTER_PREMISE_PATTERNS = {
        "sample_spacing": [
            r"\b(?:sample|specimen|genetic).{0,45}\b(?:distance|spacing|farther|further|apart)\b",
            r"\b(?:distance|spacing|farther|further|apart).{0,45}\b(?:sample|specimen|genetic)\b",
        ],
        "exobio_effort_reward": [
            r"\b(?:exobio|biology|biological|sample|specimen).{0,60}\b(?:payout|paid|credits?|profit|reward|worth|effort)\b",
            r"\b(?:payout|paid|credits?|profit|reward|worth|effort).{0,60}\b(?:exobio|biology|biological|sample|specimen)\b",
        ],
        "long_route": [
            r"\b(?:long|endless|many|another).{0,35}\b(?:route|journey|jump|jumps)\b",
            r"\b(?:route|journey).{0,35}\b(?:long|endless|distance|far|remaining)\b",
        ],
        "landing_premise": [
            r"\b(?:landing|touchdown|parking|landing gear|set down)\b",
        ],
    }

    # Journal events that are specific enough to ground an unsolicited line.
    # They are remembered briefly; they do not create extra speech opportunities.
    SITUATIONAL_EVENT_TOPICS = {
        "FSDJump": ("navigation", "ship"),
        "SupercruiseExit": ("navigation", "ship"),
        "SupercruiseDestinationDrop": ("navigation", "ship"),
        "GlideModeEntered": ("surface", "ship", "risk"),
        "GlideModeExited": ("surface", "ship"),
        "Touchdown": ("surface", "risk", "ship"),
        "Liftoff": ("surface", "ship", "risk"),
        "Disembark": ("surface", "exobio", "copilot"),
        "Embark": ("copilot", "ship", "surface"),
        "LaunchVessel": ("ship", "copilot"),
        "LaunchSRV": ("surface", "ship"),
        "DockSRV": ("surface", "ship"),
        "SCOActivated": ("navigation", "ship", "risk"),
        "SupercruiseBoost": ("navigation", "ship", "risk"),
        "FuelScoop": ("ship", "navigation"),
        "FSSDiscoveryScan": ("routine", "navigation"),
        "DiscoveryScan": ("routine", "navigation"),
        "FSSAllBodiesFound": ("routine", "navigation"),
        "SAAScanComplete": ("surface", "routine"),
        "ScanOrganic": ("exobio", "surface"),
        "FSSBodySignals (biological)": ("exobio", "surface"),
        "FSDTarget": ("navigation",),
        "NavRoute": ("navigation",),
        "Docked": ("human_systems", "ship"),
        "Undocked": ("navigation", "ship", "human_systems"),
    }

    # Spontaneous chatter must never fall back to vague cosmic philosophy.
    # These are HARD rejects, not cooldown themes. They apply only to chatter
    # candidates, so direct commander questions can still discuss philosophy.
    COSMIC_CHATTER_PATTERNS = (
        r"\b(?:universe|galaxy|cosmos|void|space|stars?)\b.*\b(?:secret|secrets|whisper|whispers|whispering|speak|speaks|speaking|talk|talks|watch|watches|watching|hide|hides|hiding|remember|remembers|remembering|wait|waits|waiting|judge|judges|judging|refuse|refuses|refusing|answer|answers|answering|story|stories|mystery|mysteries|mysterious|listen|listening|hear|hearing|message|messages)\b",
        r"\b(?:secret|secrets|whisper|whispers|whispering|speak|speaks|speaking|talk|talks|watch|watches|watching|hide|hides|hiding|remember|remembers|remembering|wait|waits|waiting|judge|judges|judging|refuse|refuses|refusing|answer|answers|answering|story|stories|mystery|mysteries|mysterious|listen|listening|hear|hearing|message|messages)\b.*\b(?:universe|galaxy|cosmos|void|space|stars?)\b",
        r"\b(?:silence|silent|quiet)\b.*\b(?:universe|galaxy|cosmos|void|space|stars?)\b",
        r"\b(?:universe|galaxy|cosmos|void|space|stars?)\b.*\b(?:silence|silent|quiet)\b",
        r"\b(?:even in|in the) silence\b",
        r"\bcosmic (?:secret|mystery|silence|whisper|story)\b",
        r"\bstories? (?:in|among|written in) the stars\b",
    )

    CHATTER_TOPIC_GUIDANCE = {
        "copilot": (
            "Make the remark about the pilot/copilot working relationship or your own role as the "
            "more literal, practical member of the crew. Dry and slightly blunt, never sentimental."
        ),
        "routine": (
            "Make the remark about the repetitive logistics of exploration: jumping, scanning, route "
            "work, menus, or the process itself. Do not claim a specific action is happening unless supplied."
        ),
        "ship": (
            "Make the remark about living or working with the ship as equipment. Do not invent damage, "
            "fuel state, module faults, or current ship conditions."
        ),
        "navigation": (
            "Make the remark about navigation, travel distance, route planning, or repeated jumps. "
            "Keep it practical and deadpan, with no cosmic awe or philosophy."
        ),
        "surface": (
            "Make the remark about landing, surface travel, terrain, or finding somewhere practical to stop. "
            "Only use concrete terrain facts if supplied by events or vision."
        ),
        "exobio": (
            "Make the remark about exobiology procedure, sample logistics, or the effort-to-reward ratio. "
            "Do not personify organisms and do not invent a species or signal."
        ),
        "human_systems": (
            "Use only a concrete current human-system detail such as station infrastructure, engineering quirks, "
            "traffic, equipment, or a specific procedure actually present in context. Do NOT default to jokes about "
            "paperwork, filing, bureaucracy, red tape, forms, administration, or humans making simple things complicated."
        ),
        "maintenance": (
            "Make the remark about maintenance culture, redundancy, repairs, module design, or keeping equipment "
            "working. Do not invent an actual fault, damage state, heat problem, or maintenance need."
        ),
        "economics": (
            "Make the remark about credits, payouts, cartography, exobiology economics, or the absurd economics of "
            "exploration. Do not invent a current balance, payout, sale, or price."
        ),
        "risk": (
            "Make the remark about sensible risk management, backups, landing caution, or the contrast between "
            "expensive hardware and ordinary pilot decisions. Do not invent current danger."
        ),
        "interfaces": (
            "Make the remark about cockpit design or a specific visible control only when there is a genuinely fresh angle. "
            "A normal HUD is not inherently interesting. Never invent a failure, warning, fault, disabled system, or malfunction."
        ),
        "visual": (
            "Base the remark on ONE concrete supplied screenshot detail. Prefer the outside scene and specific physical objects. "
            "A cockpit beam, strut, canopy obstruction, or genuinely odd physical design choice may be worth one dry observation, "
            "but do not revisit the same cockpit feature later in the session. HUD graphics, reticles, menus, text, status colors, "
            "and generic interface layout are not subjects for spontaneous chatter. Never infer faults, warnings, disabled systems, "
            "damage, or ship condition from UI appearance. Do not identify anything the vision result did not actually identify. "
            "If the only idea is interface commentary or a previously used visual premise, SKIP."
        ),
    }

    ROUTINE_FALLBACKS = {
        "far_enough": [
            "Sampling distance reached.",
            "Distance requirement met.",
            "Clear for the next sample.",
            "Next sample distance reached.",
        ],
        "first_sample": [
            "First sample logged.",
            "One of three samples collected.",
            "First biological sample complete.",
        ],
        "second_sample": [
            "Second sample logged.",
            "Two of three samples collected.",
            "Second biological sample complete.",
        ],
        "third_sample": [
            "Third sample logged. Set complete.",
            "Final sample collected.",
            "Biological sampling complete.",
        ],
        "approach_body": ["Approaching orbital cruise.", "Orbital cruise approaching."],
        "landing_gear": ["Landing gear deployed."],
        "glide_entry": ["Glide engaged."],
        "glide_exit": ["Glide complete."],
        "supercruise_exit": ["Supercruise exit complete."],
    }

    # Routine journal traffic is continuous while exploring. Only events where
    # an unsolicited joke would interrupt the commander postpone chatter.
    INTERRUPT_GAME_EVENTS = frozenset({
        "UnderAttack", "HullDamage", "Interdicted", "Interdiction",
        "EscapeInterdiction", "Died", "SRVDestroyed", "HeatWarning",
        "FsdCharging", "StartJump",
        # Explorer milestone-source events get a short quiet window so spontaneous
        # Chatter cannot slip between the raw journal event and TARSExplorerTarget.
        "ScanOrganic", "SAAScanComplete", "CodexEntry", "FSSAllBodiesFound",
    })
    INTERRUPT_STATUS_EVENTS = frozenset({"InDanger"})

    # These events may open a Chatter opportunity; they never force a response.
    # Chances are intentionally conservative. Surface repetition/exobio context can
    # modestly raise them, while all existing cooldown/priority/quality gates still apply.
    EVENT_OPPORTUNITIES = {
        "Disembark": {"chance": 0.08, "topics": ("surface", "exobio", "copilot")},
        "Embark": {"chance": 0.05, "topics": ("copilot", "ship", "surface")},
        "Liftoff": {"chance": 0.08, "topics": ("surface", "ship", "risk")},
        "Touchdown": {"chance": 0.07, "topics": ("surface", "risk", "ship")},
        "Docked": {"chance": 0.12, "topics": ("human_systems", "ship", "economics")},
        "Undocked": {"chance": 0.08, "topics": ("navigation", "ship", "human_systems")},
    }
    SURFACE_OPPORTUNITY_EVENTS = frozenset({"Disembark", "Embark", "Liftoff", "Touchdown"})

    def __init__(self, plugin_manifest: PluginManifest):
        super().__init__(plugin_manifest)
        self._manifest = plugin_manifest
        self._helper = None
        self._running = False
        self._timer = None
        self._event_timer = None
        self._event_opportunity_seq = 0
        self._lock = threading.RLock()
        self._state_path = None

        self._assistant_lines = deque(maxlen=80)
        self._user_lines = deque(maxlen=40)
        self._episodes = deque(maxlen=80)
        self._theme_last = {}
        self._chatter_premise_last = {}
        self._theme_feedback = Counter()

        self._last_assistant_time = 0.0
        self._last_chatter_line_time = 0.0
        self._pending_chatter_reply_at = 0.0
        self._last_game_activity = 0.0
        self._last_user_activity = 0.0
        self._last_visual_attempt = 0.0
        # Session-only visual novelty memory. We remember visual ideas/screens already
        # used so vision does not rediscover the same HUD, canopy frame, planet view,
        # or cockpit feature with slightly different wording.
        self._recent_visual_observations = deque(maxlen=20)
        self._last_scene = {}
        self._recent_game = deque(maxlen=8)
        self._situational_events = deque(maxlen=24)
        self._game_mode = None
        self._recent_chatter_topics = deque(maxlen=12)
        self._surface_event_history = deque(maxlen=24)
        self._last_event_opportunity_time = 0.0
        self._session_id = 0

        self._session = {
            "jumps": 0,
            "systems_completed": 0,
            "bio_signal_events": 0,
            "organic_scans": 0,
            "touchdowns": 0,
            "recent_jumps_without_bio": 0,
        }

        self._original_generate = None
        self._guard_wrapper = None
        self._llm_model = None
        self._fallback_index = Counter()

        self._semantic_cache_query = None
        self._semantic_cache_time = 0.0
        self._semantic_cache_results = []
        self._compat_warned = set()

    # ---------- COVAS compatibility bridge ----------

    @staticmethod
    def _first_attr(obj, *names):
        if obj is None:
            return None
        for name in names:
            try:
                value = getattr(obj, name, None)
            except Exception:
                value = None
            if value is not None:
                return value
        return None

    def _compat_warn_once(self, key, message):
        if key in self._compat_warned:
            return
        self._compat_warned.add(key)
        log("warn", message)

    def _covas_assistant(self):
        return self._first_attr(self._helper, "assistant", "_assistant")

    def _covas_llm(self):
        helper = self._helper
        model = self._first_attr(helper, "llm_model", "llmModel", "_llm_model")
        if model is None:
            model = self._first_attr(self._covas_assistant(), "llmModel", "llm_model")
        if model is not None and callable(getattr(model, "generate", None)):
            return model
        return None

    def _covas_event_manager(self):
        return self._first_attr(self._helper, "event_manager", "_event_manager")

    def _covas_action_manager(self):
        return self._first_attr(self._helper, "action_manager", "_action_manager")

    def _covas_vision_model(self):
        return self._first_attr(self._helper, "vision_model", "_vision_model")

    def _covas_config(self):
        config = self._first_attr(self._helper, "config", "_config")
        return config if isinstance(config, dict) else (config or {})

    def _covas_current_states(self):
        manager = self._covas_event_manager()
        getter = getattr(manager, "get_current_state", None)
        if not callable(getter):
            return None
        try:
            result = getter()
        except Exception:
            return None
        if isinstance(result, tuple) and len(result) >= 2:
            return result[1]
        return None

    def _covas_capabilities(self):
        manager = self._covas_action_manager()
        actions = getattr(manager, "actions", {}) if manager is not None else {}
        return {
            "llm_generate": self._covas_llm() is not None,
            "assistant": self._covas_assistant() is not None,
            "event_manager": self._covas_event_manager() is not None,
            "action_manager": manager is not None,
            "vision_model": self._covas_vision_model() is not None,
            "getVisuals_registered": isinstance(actions, dict) and "getVisuals" in actions,
        }

    # ---------- lifecycle ----------

    @override
    def on_chat_start(self, helper: PluginHelper):
        self._helper = helper
        self._running = True
        self._session_id += 1
        self._recent_visual_observations.clear()

        try:
            data_dir = helper.get_plugin_data_path(self._manifest)
            self._state_path = os.path.join(data_dir, "tars_ultimate_memory.json")
            self._load_state()
        except Exception as exc:
            log("error", f"TARS Director memory setup failed: {exc}")

        helper.register_event(
            name="TARSChatter",
            should_reply_check=self._should_reply_to_chatter,
            prompt_generator=self._chatter_prompt,
        )
        helper.register_event(
            name="TARSVisualTest",
            should_reply_check=self._should_reply_to_visual_test,
            prompt_generator=self._visual_test_prompt,
        )
        helper.register_sideeffect(self._observe_event)

        self._install_output_director()
        self._schedule_next()
        caps = self._covas_capabilities()
        log("info", f"TARS Chatter COVAS compatibility: {caps}")
        log("info", "TARS Chatter Director v0.11.0 started.")

    @override
    def on_chat_stop(self, helper: PluginHelper):
        self._running = False
        self._session_id += 1
        with self._lock:
            self._pending_chatter_reply_at = 0.0
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self._event_timer is not None:
                self._event_timer.cancel()
                self._event_timer = None
            self._event_opportunity_seq += 1

        self._restore_output_director()
        self._save_state()
        self._helper = None
        log("info", "TARS Chatter Director v0.11.0 stopped.")

    @override
    def on_settings_button(self, key: str):
        if key == "test_vision_now":
            if not self._running or self._helper is None:
                log("warn", "TARS vision test unavailable: start the AI first.")
                return
            threading.Thread(target=self._run_visual_test, daemon=True).start()
            return
        if key != "test_chatter_now":
            return
        if not self._running or self._helper is None:
            log("warn", "TARS Chatter test unavailable: start the AI first.")
            return
        try:
            self._helper.dispatch_event(PluginEvent(
                plugin_event_name="TARSChatter",
                plugin_event_content={
                    "triggered_at": time.time(), "session_id": self._session_id,
                    "manual_test": True, "visual": None,
                },
            ))
            log("info", "TARS Chatter manual test dispatched.")
        except Exception as exc:
            log("error", f"TARS Chatter manual test failed: {exc}")

    # ---------- COVAS output director ----------

    def _install_output_director(self):
        """
        Current COVAS keeps the active LLM on helper._llm_model / assistant.llmModel.
        We wrap generate() defensively and restore it on chat stop.
        """
        try:
            model = self._covas_llm()
            if model is None:
                log("warn", "TARS Director: no LLM model available; output guard disabled.")
                return

            # Do not double-wrap ourselves.
            if self._original_generate is not None:
                return

            self._llm_model = model
            self._original_generate = model.generate
            original = self._original_generate

            def guarded_generate(messages, tools=None, tool_choice=None):
                # Memory summarisation, agents and other model calls must pass untouched.
                system_index = self._main_covas_system_index(messages)
                if system_index is None:
                    return original(messages=messages, tools=tools, tool_choice=tool_choice)

                # COVAS action verification reuses only system + user and tools.
                if tools is not None and len(messages) <= 2:
                    return original(messages=messages, tools=tools, tool_choice=tool_choice)

                # The main model may answer a visual question from remembered text
                # without ever requesting getVisuals. For an explicit current-view
                # request, invoke COVAS's permitted action before any text model call.
                visual_query = self._explicit_visual_request(messages)
                if visual_query:
                    observed, failure = self._call_visuals(visual_query)
                    answer = observed if observed is not None else failure
                    log("info", "TARS vision: explicit request " +
                        ("succeeded with getVisuals." if observed else f"failed: {failure}"))
                    return (answer, None, ModelUsageStats())

                prepared = self._prepared_chatter_line(messages)
                if prepared:
                    return (prepared, None, ModelUsageStats())

                spontaneous = self._is_spontaneous_turn(messages)
                flight_routine = self._routine_flight_trigger(messages)
                directed_messages = messages
                if bool(self.settings.get("director_enabled", True)):
                    directed_messages = self._inject_director(messages, system_index)

                result = original(
                    messages=directed_messages,
                    tools=tools,
                    tool_choice=tool_choice
                )

                try:
                    response_text, response_actions, usage = result
                except Exception:
                    return result

                if not bool(self.settings.get("output_guard", True)) or response_actions:
                    return result

                reason = (
                    self._chatter_quality_reason(response_text) if spontaneous else None
                ) or (
                    self._routine_flight_quality_reason(response_text, flight_routine) if flight_routine else None
                ) or self._repetition_reason(response_text or "")
                if reason is None:
                    return result

                log("info", f"TARS Director rejected repetitive draft ({reason}): {response_text}")

                retry_messages = copy.deepcopy(directed_messages)
                retry_system_index = self._main_covas_system_index(retry_messages)
                if retry_system_index is None:
                    return result

                retry_block = (
                    "\n\nTARS DIRECTOR — DRAFT REJECTED:\n"
                    f'The first draft was rejected for {reason}: "{str(response_text or "")[:350]}".\n'
                    + (
                        "This is spontaneous companion chatter. Write ONE fresh dry joke or wry "
                        "personal remark with a twist. No scan/status recap, no neutral acknowledgement, "
                        "no 'nothing worth noting', and no invented game facts. "
                        if spontaneous else
                        "For a routine flight event give only a terse factual confirmation, "
                        "without jokes, metaphors, planet/universe personalities, or guesses. "
                        if flight_routine else
                        "Generate ONE genuinely different replacement. Change the underlying idea, "
                        "not only the wording. For a routine event prefer a terse factual response. "
                    )
                    + "Do not mention this rejection or these instructions."
                )
                retry_messages[retry_system_index]["content"] = (
                    str(retry_messages[retry_system_index].get("content", "")) + retry_block
                )

                retry = original(
                    messages=retry_messages,
                    tools=tools,
                    tool_choice=tool_choice
                )
                try:
                    retry_text, retry_actions, retry_usage = retry
                except Exception:
                    return retry

                if retry_actions:
                    return retry

                retry_reason = (
                    self._chatter_quality_reason(retry_text) if spontaneous else None
                ) or (
                    self._routine_flight_quality_reason(retry_text, flight_routine) if flight_routine else None
                ) or self._repetition_reason(retry_text or "")
                if retry_reason is None:
                    log("info", "TARS Director accepted regenerated response.")
                    return retry

                if spontaneous:
                    # Never speak a known-repetitive spontaneous retry. Silence is better than a recycled line.
                    log("warn", f"TARS Chatter rejected retry ({retry_reason}); suppressing spontaneous output.")
                    return ("", None, retry_usage)

                # If a repetitive routine exobio line survives two attempts,
                # use a safe factual rotating fallback instead of a third LLM call.
                routine = flight_routine or self._classify_routine_trigger(messages)
                if routine:
                    fallback = self._routine_fallback(routine)
                    log("info", f"TARS Director used factual fallback for {routine}: {fallback}")
                    return (fallback, None, retry_usage)

                log("warn", f"TARS Director retry still similar ({retry_reason}); using retry to avoid extra latency.")
                return retry

            self._guard_wrapper = guarded_generate
            model.generate = guarded_generate
            log("info", "TARS Director installed system-level LLM output guard.")
        except Exception as exc:
            log("error", f"TARS Director could not install output guard: {exc}")

    def _restore_output_director(self):
        try:
            if self._llm_model is not None and self._original_generate is not None:
                if self._llm_model.generate is self._guard_wrapper:
                    self._llm_model.generate = self._original_generate
                    log("info", "TARS Director restored previous LLM generator.")
                else:
                    log("warn", "TARS Director skipped restoring LLM generator modified by another plugin.")
        except Exception as exc:
            log("error", f"TARS Director could not restore LLM generator: {exc}")
        finally:
            self._original_generate = None
            self._guard_wrapper = None
            self._llm_model = None

    def _main_covas_system_index(self, messages):
        """Find only the primary COVAS conversation system prompt.

        The current COVAS prompt has a distinctive prefix, but use multiple
        structural markers so a small upstream wording change does not silently
        disable the Director. If the call cannot be identified confidently, fail
        closed and leave the model call untouched.
        """
        try:
            for idx, msg in enumerate(messages or []):
                if not isinstance(msg, dict) or msg.get("role") != "system":
                    continue
                content = str(msg.get("content", ""))
                score = 0
                if "The universe of Elite:Dangerous is your reality." in content:
                    score += 3
                if "Only react to game events marked with 'IMPORTANT:'" in content:
                    score += 1
                if "Your purpose is to provide information, status updates, and execute tools as required." in content:
                    score += 1
                if "Your character prompt is:" in content:
                    score += 1
                if score >= 2:
                    return idx
        except Exception:
            pass
        return None

    def _is_spontaneous_turn(self, messages):
        # COVAS appends status/logbook user messages after the current event.
        # Find the latest conversational user item, so an older chatter event
        # in short-term history does not affect a new commander request.
        for msg in reversed(messages or []):
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            content = str(msg.get("content", "") or "")
            if (content.startswith("[Ship logbook")
                    or content.startswith("Current status:")
                    or content.startswith("[Current status")
                    or (content.startswith("# ") and "\n" in content)):
                continue
            return ("[External Event" in content
                    and "SPONTANEOUS TARS COMPANION OPPORTUNITY" in content)
        return False

    def _prepared_chatter_line(self, messages):
        """Use the screened candidate from the latest plugin event verbatim."""
        for msg in reversed(messages or []):
            if not isinstance(msg, dict):
                continue
            if msg.get("role") in ("assistant", "tool"):
                return None
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            if content.startswith(("[Ship logbook", "# ", "Current status:")):
                continue
            if content.startswith(("[Game Event", "[Status Event")):
                continue
            if "[External Event" not in content or "SPONTANEOUS TARS COMPANION OPPORTUNITY" not in content:
                return None
            match = re.search(r"^PREPARED_TARS_LINE: (.+)$", content, re.M)
            if not match:
                return None
            try:
                line = json.loads(match.group(1))
            except (TypeError, ValueError):
                return None
            return line if isinstance(line, str) and line.strip() else None
        return None

    def _explicit_visual_request(self, messages):
        """Return the latest direct commander request, never stale conversation or events."""
        for msg in reversed(messages or []):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role in ("assistant", "tool"):
                return None
            if role != "user":
                continue
            content = msg.get("content")
            if not isinstance(content, str):
                continue
            if content.startswith(("[Ship logbook", "[Current status", "# ", "Current status:")):
                continue
            if content.startswith("[") or "\n" in content:
                return None
            phrase = re.sub(r"^(?:hey\s+)?(?:tars|covas)[,\s]+", "", content.strip(), flags=re.I)
            match = re.search(
                r"\b(?:get\s*visuals?|what\s+(?:can\s+you|do\s+you)\s+see|"
                r"(?:can\s+you\s+)?(?:look\s+at|describe|check|show\s+me)\s+"
                r"(?:the\s+)?(?:screen|view|screenshot|what(?:'s|\s+is)\s+(?:on|in)\s+(?:my\s+)?(?:screen|view))|"
                r"(?:take|grab|capture)\s+(?:a\s+)?screenshot|"
                r"what(?:'s|\s+is)\s+(?:on|in)\s+(?:my\s+|the\s+)?(?:screen|view))\b",
                phrase, re.I,
            )
            if match and not re.search(r"\b(?:don't|do not|never|without)\b", phrase[:match.start()], re.I):
                return phrase[:350]
            return None
        return None

    def _call_visuals(self, query):
        """Call the registered COVAS action; return (description, failure)."""
        helper = self._helper
        if helper is None or self._covas_vision_model() is None:
            return None, "COVAS vision is off. Enable Vision in COVAS settings and restart the AI."
        manager = self._covas_action_manager()
        if (manager is None or
                getattr(manager, "allowed_actions", {}).get("getVisuals") is not True):
            return None, "The getVisuals action is blocked. Allow it in COVAS Actions and restart the AI."
        action = getattr(manager, "actions", {}).get("getVisuals")
        if not isinstance(action, dict) or not callable(action.get("method")):
            return None, "The getVisuals action is unavailable. Restart the COVAS AI with Vision enabled."
        bare_request = bool(re.fullmatch(
            r"(?:get\s*visuals?|what\s+(?:do|can)\s+you\s+see|look\s+at\s+the\s+screen)\s*[?.!]?",
            re.sub(r"^(?:hey\s+)?(?:tars|covas)[,\s]+", "", str(query).strip(), flags=re.I),
            flags=re.I,
        ))
        vision_query = (
            "Give ONE conversational sentence about the most interesting concrete thing "
            "visible in the image. Mention a planet class only if it is legible in the image. "
            "Skip HUD numbers, scan frames, button labels and cockpit details. "
            "No guessed location, identity, discoveries or jokes."
            if bare_request else query
        )
        try:
            states = self._covas_current_states()
            if states is None:
                return None, "COVAS state access is unavailable for the vision action."
            result = action["method"]({"query": vision_query}, states)
        except Exception as exc:
            error = str(exc).lower()
            if "invalid_api_key" in error or "incorrect api key" in error or "unauthorized" in error:
                config = self._covas_config()
                inherited_key = config.get("vision_api_key", "") == ""
                uses_openrouter_key = str(config.get("api_key", "")).startswith("sk-or-v1")
                if (config.get("vision_provider") == "openai" and inherited_key
                        and uses_openrouter_key):
                    failure = (
                        "OpenAI rejected your OpenRouter key. Choose Custom vision "
                        "with the OpenRouter endpoint and restart the AI."
                    )
                    category = "OpenAI/OpenRouter key mismatch"
                else:
                    failure = "The vision API key was rejected. Check the Vision API key and provider in COVAS."
                    category = "vision API key rejected"
            elif "model_not_found" in error or "model not found" in error:
                failure = "The vision model was not found. Check the Vision Model Name in COVAS."
                category = "vision model not found"
            else:
                failure = "The screenshot or vision model failed. Check the COVAS log for the error."
                category = type(exc).__name__
            # Do not log raw provider exception text: it may contain an API key.
            log("warn", f"TARS vision action failed: {category}.")
            return None, failure
        if not isinstance(result, str) or not result.strip():
            return None, "The vision model returned no description of the screenshot."
        description = " ".join(result.split())
        lower = description.lower()
        if lower.startswith(("unable to take screenshot", "vision not enabled")):
            return None, ("I couldn't capture the Elite Dangerous window. Keep the game open and visible, then try again."
                          if lower.startswith("unable") else
                          "COVAS vision is off. Enable Vision in COVAS settings and restart the AI.")
        if lower.startswith(("error:", "i can't access", "i cannot access", "i can't see", "i cannot see",
                             "i don't have access to", "as an ai")):
            log("warn", f"TARS vision returned an unusable description: {description[:250]}")
            return None, "The vision model did not describe the captured image. Check its COVAS settings and log."
        if bare_request:
            # COVAS's built-in image prompt asks for every visible object and
            # readable HUD value. A short direct request needs the scene, not a
            # spoken OCR dump. Keep the first useful sentence if the model still
            # returns a multi-paragraph report despite the query above.
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", description, maxsplit=1)
            description = sentences[0].strip()[:300]
        return description[:900], None

    def _run_visual_test(self):
        session = self._session_id
        observed, failure = self._call_visuals(
            "Describe only concrete objects actually visible in this screenshot. "
            "Do not infer planets, positions, or signals from game state."
        )
        if not self._running or self._session_id != session or self._helper is None:
            return
        log("info", "TARS vision diagnostic: " +
            (f"CAPTURE OK; model described: {observed}" if observed else f"FAILED: {failure}"))
        try:
            self._helper.dispatch_event(PluginEvent(
                plugin_event_name="TARSVisualTest",
                plugin_event_content={"session_id": session, "triggered_at": time.time(),
                                      "description": observed, "failure": failure},
            ))
        except Exception as exc:
            log("error", f"TARS vision diagnostic dispatch failed: {exc}")

    def _should_reply_to_visual_test(self, event):
        data = getattr(event, "plugin_event_content", None)
        return bool(isinstance(data, dict) and self._running
                    and data.get("session_id") == self._session_id
                    and isinstance(data.get("triggered_at"), (float, int))
                    and 0 <= time.time() - data["triggered_at"] <= 60)

    def _visual_test_prompt(self, event):
        data = getattr(event, "plugin_event_content", {})
        statement = data.get("description") or data.get("failure")
        return ("VISUAL DIAGNOSTIC: Read this result aloud accurately in one sentence. "
                "Do not add anything you did not see: " + str(statement)[:900])

    def _chatter_quality_reason(self, candidate):
        if not isinstance(candidate, str) or not candidate.strip():
            return "empty chatter"
        text = self._normalize(candidate)
        if self._cosmic_chatter_reason(candidate):
            return "cosmic philosophy is disabled for spontaneous chatter"
        if re.search(
            r"\b(?:paperwork|bureaucracy|bureaucratic|filing|red tape|administrative|"
            r"forms? to (?:fill|file)|forms? to fill out)\b",
            text,
        ):
            return "stock paperwork/bureaucracy premise is disabled for spontaneous chatter"
        if re.search(r"\bearn(?:s|ed|ing)? (?:its|their|his|her|our|your) keep\b", text):
            return "recurring earn-their-keep premise is disabled for spontaneous chatter"
        if (re.search(r"\bi (?:do|handle|take care of)\b", text)
                and re.search(r"\byou (?:do|handle|take care of)\b", text)):
            return "recurring pilot/copilot division-of-labor premise"
        if re.search(r"\bdivision of labo(?:u)?r\b", text):
            return "recurring pilot/copilot division-of-labor premise"
        if re.match(r"^(?:sometimes i think|it'?s strange how|there'?s something about)\b", text):
            return "reflective filler instead of concrete TARS chatter"
        if re.search(r"\b(?:failed|failure|broken|malfunction|fault|offline|disabled|warning|alert|critical|not working|stopped working)\b", text) and re.search(r"\b(?:interface|hud|display|panel|com|comms|module|system|controls?|reticle|readout)\b", text):
            return "invented cockpit/interface malfunction or warning"
        if re.search(r"\b(?:hud|interface|dashboard|display|console|controls?|screen|reticle|readout|status light|indicator)\b", text) and not re.search(r"\b(?:beam|strut|canopy|window frame|obstruction|viewport frame)\b", text):
            return "generic cockpit/interface commentary"
        if any(phrase in text for phrase in (
            "nothing worth noting", "nothing noteworthy", "nothing new to report",
            "no new signals", "no unidentified signals", "no new discoveries",
            "system is fully mapped", "system fully mapped", "all systems nominal",
            "no further updates", "no relevant updates", "awaiting further",
            "ready when you are", "standing by", "all clear commander",
            "sense of humor", "idea of a joke", "geological impression",
            "navigation is sound", "judgment behind it", "still in charge",
        )):
            return "generic status or empty filler"
        if "universe" in text and any(x in text for x in ("joke", "humor", "laugh", "funny")):
            return "stock universe joke"
        if re.search(r"\b(?:planet|body|world|surface)\b.*\b(?:waiting|wants|thinks|remind)\b", text):
            return "personified planet cliché"
        if re.match(r"^(?:the )?(?:system|scan|signals|shields|cargo|fuel)\b", text):
            if not any(x in text for x in (" but ", " although ", " apparently ", " except ")):
                return "routine status summary"
        return None

    def _cosmic_chatter_reason(self, candidate):
        if not isinstance(candidate, str):
            return None
        low = candidate.casefold()
        # "void", "cosmos", "silence" and "whisper" are essentially never needed
        # for useful ambient cockpit chatter and were the strongest observed failure mode.
        if re.search(r"\b(?:void|cosmos|cosmic|whisper|whispers|whispering)\b", low):
            return "banned cosmic-poetry vocabulary"
        for pattern in self.COSMIC_CHATTER_PATTERNS:
            if re.search(pattern, low, flags=re.I):
                return "banned cosmic-philosophy premise"
        return None

    def _classify_chatter_topic(self, text):
        low = self._normalize(text)
        if not low:
            return None
        if any(w in low for w in ("landing", "terrain", "surface", "ground", "parking", "srv", "wheel")):
            return "surface"
        if any(w in low for w in ("sample", "biology", "biological", "exobio", "organism", "genetic")):
            return "exobio"
        if any(w in low for w in ("route", "jump", "navigation", "destination", "map", "light year")):
            return "navigation"
        if any(w in low for w in ("ship", "module", "fuel", "scoop", "engine", "hull", "cargo", "drive")):
            return "ship"
        if any(w in low for w in ("menu", "interface", "button", "display", "readout", "control", "panel")):
            return "interfaces"
        if any(w in low for w in ("repair", "maintenance", "redund", "spare", "reliable", "reliability")):
            return "maintenance"
        if any(w in low for w in ("credit", "payout", "profit", "expensive", "cheap", "economics", "paid")):
            return "economics"
        if any(w in low for w in ("risk", "insurance", "caution", "careful", "backup")):
            return "risk"
        if any(w in low for w in ("station", "bureaucr", "engineer", "engineering", "name", "naming", "humanity", "procedure")):
            return "human_systems"
        if any(w in low for w in ("copilot", "crew", "my role", "your role", "you do", "i do", "we do", "our")):
            return "copilot"
        return "routine"

    def _recent_situational_anchors(self, now, visual=None, event_context=None):
        """Return only concrete, fresh facts that may ground unsolicited speech."""
        anchors = []
        with self._lock:
            recent = [
                dict(item) for item in self._situational_events
                if 0 <= now - float(item.get("t", 0.0)) <= 90.0
            ]
            mode = self._game_mode

        for item in recent[-6:]:
            age = max(0, int(now - float(item.get("t", now))))
            anchors.append({
                "kind": "game_event",
                "label": str(item.get("label") or item.get("name") or "gameplay event"),
                "event": str(item.get("name") or ""),
                "topics": list(item.get("topics") or ()),
                "age_seconds": age,
            })

        if visual:
            anchors.append({
                "kind": "visual",
                "label": str(visual)[:300],
                "event": "visual",
                "topics": ["visual"],
                "age_seconds": 0,
            })

        # Event-triggered calls should normally find the same event in the journal
        # buffer. Keep this conservative fallback for hosts that deliver callbacks
        # out of order, and only while the opportunity itself is fresh.
        if isinstance(event_context, dict):
            event_name = str(event_context.get("event") or "")
            event_time = event_context.get("event_time")
            if (event_name in self.SITUATIONAL_EVENT_TOPICS
                    and isinstance(event_time, (int, float))
                    and 0 <= now - event_time <= 90
                    and not any(x.get("event") == event_name for x in anchors)):
                anchors.append({
                    "kind": "game_event",
                    "label": self._event_anchor_label(event_name, {}),
                    "event": event_name,
                    "topics": list(self.SITUATIONAL_EVENT_TOPICS[event_name]),
                    "age_seconds": int(now - event_time),
                })

        if anchors and mode:
            # Mode is supporting context, never a standalone reason to talk.
            anchors[-1]["mode"] = mode
        return anchors

    def _choose_chatter_topics(self, visual, events, scene, session, anchors=None):
        eligible = []
        if anchors is not None:
            for anchor in reversed(anchors):
                eligible.extend(anchor.get("topics") or ())
        elif visual:
            eligible.append("visual")
        recent_events = set(events or [])
        if anchors is None and (any(x in recent_events for x in ("Touchdown", "Liftoff", "SAAScanComplete", "SupercruiseDestinationDrop")) or scene.get("body")):
            eligible.append("surface")
        if anchors is None and (session.get("organic_scans", 0) or session.get("bio_signal_events", 0)
                or "ScanOrganic" in recent_events or "FSSBodySignals (biological)" in recent_events):
            eligible.append("exobio")
        if anchors is None and (session.get("jumps", 0) or "FSDJump" in recent_events):
            eligible.append("navigation")
        if anchors is None and any(x in recent_events for x in ("Docked", "Undocked", "Shipyard", "Outfitting")):
            eligible.extend(["human_systems", "ship"])
        if anchors is None and any(x in recent_events for x in ("Repair", "RepairAll", "Outfitting")):
            eligible.extend(["maintenance", "ship"])
        if anchors is None and any(x in recent_events for x in ("SellExplorationData", "MultiSellExplorationData", "SellOrganicData")):
            eligible.append("economics")
        if anchors is None and any(x in recent_events for x in ("Touchdown", "Liftoff", "Disembark", "Embark")):
            eligible.append("risk")
        # Generic interface/economics/maintenance/risk chatter is not a standing
        # topic. New calls receive only topics supplied by concrete anchors. The
        # legacy branch remains for compatibility with existing diagnostics.
        if anchors is None and not eligible:
            eligible.append("copilot")

        # Preserve order while removing duplicates, then move recently used topics to the back.
        unique = []
        for topic in eligible:
            if topic not in unique:
                unique.append(topic)
        with self._lock:
            recent_topics = list(self._recent_chatter_topics)[-8:]
        fresh = [t for t in unique if t not in recent_topics]
        stale = [t for t in unique if t in recent_topics]
        pool = fresh + stale
        if len(pool) > 1:
            # Randomize within the fresh section so chatter does not form a predictable cycle.
            n = max(1, len(fresh))
            head = pool[:n]
            random.shuffle(head)
            pool = head + pool[n:]
        return pool

    def _routine_flight_quality_reason(self, candidate, routine=None):
        if not isinstance(candidate, str) or not candidate.strip():
            return "empty routine event"
        text = self._normalize(candidate)
        if routine == "glide_entry" and re.search(r"\b(?:in|into) orbit\b", text):
            return "glide described as orbit"
        if re.search(r"\b(?:joke|humor|laugh|waiting|probably|judgment|impression|universe)\b", text):
            return "unnecessary joke in routine flight event"
        return None

    def _inject_director(self, messages, system_index):
        directed = copy.deepcopy(messages)

        with self._lock:
            recent = [x["text"] for x in list(self._assistant_lines)[-8:]]
            blocked = self._blocked_themes()

        recent_text = "\n".join(f"- {x}" for x in recent) if recent else "- none yet"
        blocked_text = ", ".join(blocked) if blocked else "none"
        flight_routine = self._routine_flight_trigger(messages)
        routine = flight_routine or self._classify_routine_trigger(messages)
        spontaneous = self._is_spontaneous_turn(messages)

        routine_rule = ""
        if flight_routine:
            routine_rule = (
                "\nTHIS IS ROUTINE FLIGHT PROGRESS. Give only a short, accurate "
                "confirmation. No joke, geological metaphor, planet/universe "
                "personality, praise, or invented detail."
            )
        elif routine:
            routine_rule = (
                "\nTHIS RESPONSE IS ROUTINE EXOBIOLOGY SAMPLE PROGRESS. "
                "Use a terse factual status only. NO joke, metaphor, encouragement, praise, "
                "microbe personality, bravery remark, 'hope', or 'Commander'. "
                "Do not add facts beyond the supplied event."
            )

        chatter_rule = ""
        if spontaneous:
            chatter_rule = (
                "\nSPONTANEOUS TARS CHATTER IS AUTHORIZED FOR THIS ONE RESPONSE. "
                "The external event explicitly invites you to initiate one short comment. "
                "Give it dry, practical, slightly blunt TARS personality. Prefer a concrete observation about the "
                "outside view, ship design, procedure, pilot/copilot work, navigation, landing, or exploration logistics. "
                "A specific cockpit feature can be funny once, but generic HUD/interface commentary is not a fresh subject. "
                "Never invent a malfunction, failure, warning, damage state, or disabled system from a screenshot. "
                "COSMIC PHILOSOPHY IS FORBIDDEN: no universe/galaxy/stars/space/void/silence as things "
                "that whisper, hide secrets, watch, remember, speak, refuse answers, or tell stories. "
                "Do not summarize a scan, say nothing is worth noting, recite system status, "
                "or report unchanged facts. Avoid invented game facts."
            )

        semantic_memories = self._semantic_memories_for_prompt(messages)
        memory_text = ""
        if semantic_memories:
            memory_text = (
                "\nSEMANTIC LOGBOOK RECALL — use only if naturally relevant; never force a callback:\n"
                + "\n".join(f"- {m}" for m in semantic_memories)
            )

        director = f"""

TARS DIRECTOR — HIGH PRIORITY CONTINUITY:
Recent TARS lines:
{recent_text}
Recently used comedic premises: {blocked_text}

Rules for THIS response:
- Never repeat or lightly paraphrase a recent TARS line.
- A synonym rewrite of the same joke/premise is still repetition.
- Never reproduce a TARS style-example line from the character prompt verbatim.
- Humor 75% is personality intensity, NOT joke frequency.
- Routine information should usually be delivered straight.
- Do not attach generic assistant filler such as "hope...", praise, encouragement, or "ready when you are".
- Do not personify microbes/bacteria/lifeforms as chatty, impatient, sociable, opinionated, partying, or similar if that premise was recently used.
- Most responses should not address the user as "Commander".
- Never invent facts, quantities, species, organisms, values, memories, or discoveries for a joke.
- One concise sentence is preferred.
{routine_rule}
{chatter_rule}
{memory_text}
"""
        directed[system_index]["content"] = (
            str(directed[system_index].get("content", "")) + director
        )
        return directed

    # ---------- repetition detection ----------

    def _normalize(self, text):
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s']", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _content_words(self, text):
        return {
            w for w in re.findall(r"[a-zA-Z']+", text.lower())
            if len(w) >= 4 and w not in self.STOPWORDS
        }

    def _themes(self, text):
        low = text.lower()
        found = []
        for theme, patterns in self.THEME_PATTERNS.items():
            if any(re.search(pattern, low) for pattern in patterns):
                found.append(theme)
        return found

    def _chatter_premises(self, text):
        low = str(text or "").lower()
        return [
            premise for premise, patterns in self.CHATTER_PREMISE_PATTERNS.items()
            if any(re.search(pattern, low) for pattern in patterns)
        ]

    def _blocked_chatter_premises(self):
        now = time.time()
        try:
            cooldown = float(self.settings.get("theme_cooldown_minutes", 60)) * 60.0
        except Exception:
            cooldown = 3600.0
        cooldown = max(600.0, cooldown)
        return [
            premise for premise, used_at in self._chatter_premise_last.items()
            if now - float(used_at) < cooldown
        ]

    def _chatter_premise_reason(self, candidate):
        blocked = set(self._blocked_chatter_premises())
        for premise in self._chatter_premises(candidate):
            if premise in blocked:
                return f"recently used chatter premise '{premise}'"
        return None

    def _blocked_themes(self):
        now = time.time()
        try:
            cooldown = float(self.settings.get("theme_cooldown_minutes", 60)) * 60.0
        except Exception:
            cooldown = 3600.0
        cooldown = max(600.0, cooldown)

        return [
            theme for theme, used_at in self._theme_last.items()
            if now - float(used_at) < cooldown
        ]

    def _repetition_reason(self, candidate):
        cand_norm = self._normalize(candidate)
        if not cand_norm:
            return None

        # Character prompt examples are style examples, not canned replies.
        if cand_norm in self.STYLE_EXAMPLES:
            return "verbatim reuse of a character-prompt example"

        # Keep the intentionally fixed empty-system phrase legal.
        if cand_norm == "nothing worth stopping for":
            return None

        with self._lock:
            recent = [x["text"] for x in list(self._assistant_lines)[-40:]]
            blocked = set(self._blocked_themes())

        cand_words = self._content_words(candidate)

        for old in recent:
            old_norm = self._normalize(old)
            if not old_norm:
                continue

            if cand_norm == old_norm:
                return "exact repetition of a recent line"

            # Strong sentence-level similarity.
            seq = difflib.SequenceMatcher(None, cand_norm, old_norm).ratio()
            if min(len(cand_norm), len(old_norm)) >= 24 and seq >= 0.86:
                return f"near-duplicate wording ({seq:.0%} similar)"

            # Content-word overlap catches modest rephrasing.
            old_words = self._content_words(old)
            if len(cand_words) >= 4 and len(old_words) >= 4:
                union = cand_words | old_words
                overlap = len(cand_words & old_words) / max(1, len(union))
                if overlap >= 0.52:
                    return f"same recent content/premise ({overlap:.0%} overlap)"

        # Known joke/filler families get a time cooldown even after rewording.
        for theme in self._themes(candidate):
            if theme in blocked:
                return f"recently used comedic premise '{theme}'"

        return None

    # ---------- semantic COVAS logbook recall ----------

    def _semantic_memories_for_prompt(self, messages):
        if not bool(self.settings.get("semantic_memory", True)):
            return []
        if self._helper is None:
            return []

        query = self._memory_query(messages)
        if not query:
            return []

        now = time.time()
        if (
            self._semantic_cache_query == query
            and now - self._semantic_cache_time < 120
        ):
            return list(self._semantic_cache_results)

        try:
            assistant = self._covas_assistant()
            embedding_model = self._first_attr(assistant, "embeddingModel", "embedding_model")
            event_manager = self._covas_event_manager()
            store = getattr(event_manager, "long_term_memory", None)

            if embedding_model is None or store is None:
                return []

            model_name, embedding = embedding_model.create_embedding(query)

            results = store.search(
                query=query,
                model_name=model_name,
                query_embedding=embedding,
                n=3,
            )

            # VectorStore initializes lazily and returns [] on that first initialize.
            if not results and getattr(store, "initialized", False):
                results = store.search(
                    query=query,
                    model_name=model_name,
                    query_embedding=embedding,
                    n=3,
                )

            memories = []
            for result in results or []:
                content = str(result.get("content", "") or "").strip()
                if content and content not in memories:
                    memories.append(content[:650])
                if len(memories) >= 2:
                    break

            self._semantic_cache_query = query
            self._semantic_cache_time = now
            self._semantic_cache_results = memories
            if memories:
                log("info", f"TARS Director retrieved {len(memories)} semantic logbook memories.")
            return memories

        except Exception as exc:
            # Memory recall is optional: never break TARS if Gemma/vector search fails.
            log("warn", f"TARS Director semantic memory recall skipped: {exc}")
            return []

    def _memory_query(self, messages):
        """
        Semantic search is intentionally NOT run for every ordinary game reaction.
        It runs for spontaneous chatter and explicit memory-oriented user requests.
        """
        items = []
        chatter = False
        memory_request = False

        for msg in (messages or [])[-12:]:
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            content = str(msg.get("content", "") or "")
            low = content.lower()

            if "spontaneous tars companion opportunity" in low:
                chatter = True

            if any(x in low for x in (
                "remember", "last time", "previously", "earlier",
                "before when", "what happened", "we used to"
            )):
                memory_request = True

            # Ignore the giant status dump and already-added logbook memories.
            if content.startswith("[Ship logbook"):
                continue
            if "Current status:" in content and len(content) > 1000:
                continue
            if content.strip():
                items.append(content[-500:])

        if not chatter and not memory_request:
            return None

        with self._lock:
            episode_text = " ".join(x["text"] for x in list(self._episodes)[-3:])
            session = dict(self._session)

        query = " ".join(items[-4:])
        if chatter:
            query += (
                f" Current expedition: {session['jumps']} jumps, "
                f"{session['organic_scans']} organic scans, "
                f"{session['bio_signal_events']} biological-signal events. "
                + episode_text
            )

        query = re.sub(r"\s+", " ", query).strip()
        return query[:1800] if len(query) >= 8 else None

    # ---------- event observation / learning ----------

    def _observe_event(self, event, context):
        now = time.time()
        kind = getattr(event, "kind", "")

        with self._lock:
            if kind == "assistant":
                text = str(getattr(event, "content", "") or "").strip()
                if text:
                    self._assistant_lines.append({"t": now, "text": text})
                    self._last_assistant_time = now
                    if (self._pending_chatter_reply_at
                            and 0 <= now - self._pending_chatter_reply_at < 90):
                        self._last_chatter_line_time = now
                        topic = self._classify_chatter_topic(text)
                        if topic:
                            self._recent_chatter_topics.append(topic)
                    self._pending_chatter_reply_at = 0.0
                    for theme in self._themes(text):
                        self._theme_last[theme] = now
                    self._save_state()

            elif kind == "user":
                text = str(getattr(event, "content", "") or "").strip()
                if text:
                    self._pending_chatter_reply_at = 0.0
                    self._last_user_activity = now
                    self._user_lines.append({"t": now, "text": text})
                    self._learn_feedback(text, now)

            elif kind == "user_speaking":
                self._pending_chatter_reply_at = 0.0
                self._last_user_activity = now

            elif kind in ("assistant_speaking", "assistant_acting"):
                self._last_assistant_time = now

            elif kind == "game":
                content = getattr(event, "content", {}) or {}
                if not getattr(event, "historic", False) and isinstance(content, dict):
                    if content.get("event") in self.INTERRUPT_GAME_EVENTS:
                        self._last_game_activity = now
                    self._observe_game(content, now)

            elif kind == "status":
                status = getattr(event, "status", None)
                if isinstance(status, dict) and status.get("event") in self.INTERRUPT_STATUS_EVENTS:
                    self._last_game_activity = now

            elif kind == "memory":
                # This is a newly created COVAS memory summary, not semantic retrieval.
                text = str(getattr(event, "content", "") or "").strip()
                if text:
                    self._episodes.append({
                        "t": now,
                        "type": "logbook_created",
                        "text": text[:500],
                    })

    def _learn_feedback(self, text, now):
        if not bool(self.settings.get("feedback_learning", True)):
            return

        low = text.lower()
        negative = any(x in low for x in (
            "same joke", "said that already", "you said that already",
            "you've said that", "you have said that", "stop saying",
            "repeating yourself", "getting repetitive", "not funny",
            "that joke was terrible", "shut up about"
        ))
        if not negative or not self._assistant_lines:
            return

        previous = self._assistant_lines[-1]["text"]
        themes = self._themes(previous)
        for theme in themes:
            self._theme_feedback[theme] -= 4
            # Future-date by one cooldown window -> effectively a long ban.
            self._theme_last[theme] = now + 3600

        self._episodes.append({
            "t": now,
            "type": "feedback",
            "text": f'User rejected the previous TARS response as repetitive/unfunny: "{previous[:250]}"'
        })
        self._save_state()

    def _observe_game(self, c, now):
        name = str(c.get("event", ""))

        mode_changes = {
            "FSDJump": "supercruise/cockpit",
            "SupercruiseEntry": "supercruise/cockpit",
            "SupercruiseExit": "normal flight/cockpit",
            "SupercruiseDestinationDrop": "normal flight/cockpit",
            "Touchdown": "landed/cockpit",
            "Liftoff": "normal flight/cockpit",
            "Disembark": "on foot",
            "Embark": "landed/cockpit",
            "LaunchSRV": "SRV",
            "DockSRV": "landed/cockpit",
            "FSSDiscoveryScan": "FSS",
            "FSSAllBodiesFound": "FSS",
        }
        if name in mode_changes:
            self._game_mode = mode_changes[name]

        if name in ("FSDJump", "Location", "CarrierJump"):
            system = c.get("StarSystem")
            if isinstance(system, str) and system.strip():
                self._last_scene["system"] = system.strip()[:100]
        if name in ("Touchdown", "ApproachBody", "ScanOrganic", "LeaveBody", "SAAScanComplete"):
            body = c.get("Body") or c.get("BodyName")
            if isinstance(body, str) and body.strip():
                self._last_scene["body"] = body.strip()[:100]
        if name == "Scan":
            planet_class = str(c.get("PlanetClass") or "").strip()
            if any(label in planet_class.casefold() for label in
                   ("earthlike", "earth-like", "water world", "ammonia world")):
                body = c.get("BodyName")
                if isinstance(body, str) and body.strip():
                    self._last_scene["body"] = body.strip()[:100]
                self._last_scene["planet_class"] = planet_class[:80]
        if name == "FSDJump":
            self._last_scene.pop("body", None)
            self._last_scene.pop("planet_class", None)

        if name in self.SITUATIONAL_EVENT_TOPICS:
            self._situational_events.append({
                "t": now,
                "name": name,
                "label": self._event_anchor_label(name, c),
                "topics": self.SITUATIONAL_EVENT_TOPICS[name],
            })

        noteworthy = {"FSDJump", "Touchdown", "Liftoff", "Disembark", "Embark",
                      "ScanOrganic", "CodexEntry", "FSSAllBodiesFound",
                      "SupercruiseDestinationDrop", "DiscoveryScan", "SAAScanComplete",
                      "Docked", "Undocked", "Shipyard", "Outfitting", "Repair",
                      "RepairAll", "SellExplorationData", "MultiSellExplorationData",
                      "SellOrganicData"}
        if name == "Scan" and self._last_scene.get("planet_class") == c.get("PlanetClass"):
            noteworthy.add("Scan")
        if name in noteworthy:
            self._recent_game.append({"t": now, "name": name})

        if name == "FSDJump":
            self._session["jumps"] += 1
            self._session["recent_jumps_without_bio"] += 1

        elif name == "FSSAllBodiesFound":
            self._session["systems_completed"] += 1

        elif name == "FSSBodySignals":
            signals = c.get("Signals") or []
            if any(isinstance(signal, dict) and "biological" in
                   str(signal.get("Type_Localised") or signal.get("Type") or "").casefold()
                   and (signal.get("Count") or 0) for signal in signals):
                self._session["bio_signal_events"] += 1
                self._session["recent_jumps_without_bio"] = 0
                self._recent_game.append({"t": now, "name": "FSSBodySignals (biological)"})
                self._situational_events.append({
                    "t": now,
                    "name": "FSSBodySignals (biological)",
                    "label": "biological signals were just found in FSS",
                    "topics": self.SITUATIONAL_EVENT_TOPICS["FSSBodySignals (biological)"],
                })

        elif name == "ScanOrganic":
            self._session["organic_scans"] += 1

        elif name == "Touchdown":
            self._session["touchdowns"] += 1

        if name in self.EVENT_OPPORTUNITIES and self._running:
            if name in self.SURFACE_OPPORTUNITY_EVENTS:
                self._surface_event_history.append({"t": now, "name": name})
            self._schedule_event_opportunity(name, now)

    def _event_anchor_label(self, name, content):
        system = str(content.get("StarSystem") or self._last_scene.get("system") or "").strip()
        body = str(content.get("Body") or content.get("BodyName") or self._last_scene.get("body") or "").strip()
        target = str(content.get("Name") or content.get("StarSystem") or "").strip()
        labels = {
            "FSDJump": f"the ship just completed an FSD jump{f' into {system}' if system else ''}",
            "SupercruiseExit": f"the ship just exited supercruise{f' near {body}' if body else ''}",
            "SupercruiseDestinationDrop": f"the ship just dropped from supercruise{f' near {body}' if body else ''}",
            "GlideModeEntered": f"surface glide just began{f' toward {body}' if body else ''}",
            "GlideModeExited": f"surface glide just ended{f' at {body}' if body else ''}",
            "Touchdown": f"the ship just touched down{f' on {body}' if body else ''}",
            "Liftoff": f"the ship just lifted off{f' from {body}' if body else ''}",
            "Disembark": "the commander just disembarked",
            "Embark": "the commander just boarded the ship",
            "LaunchVessel": "a ship-launched vessel was just deployed",
            "LaunchSRV": "the SRV was just deployed",
            "DockSRV": "the SRV was just docked with the ship",
            "SCOActivated": "supercruise overcharge was just activated",
            "SupercruiseBoost": "supercruise overcharge was just activated",
            "FuelScoop": "a fuel-scooping cycle just completed",
            "FSSDiscoveryScan": "FSS activity just identified bodies in the current system",
            "DiscoveryScan": "a discovery scan was just performed",
            "FSSAllBodiesFound": "FSS just identified all bodies in the current system",
            "SAAScanComplete": f"a surface scan just completed{f' for {body}' if body else ''}",
            "ScanOrganic": f"an organic sample was just scanned{f' on {body}' if body else ''}",
            "FSDTarget": f"a route target was just selected{f': {target}' if target else ''}",
            "NavRoute": "the plotted route was just updated",
            "Docked": "the ship just docked",
            "Undocked": "the ship just undocked",
        }
        return labels.get(name, name)

    # ---------- event-triggered spontaneous chatter ----------

    def _event_opportunity_chance(self, name, now):
        config = self.EVENT_OPPORTUNITIES.get(name)
        if not config:
            return 0.0

        chance = float(config["chance"])
        if name in self.SURFACE_OPPORTUNITY_EVENTS:
            recent_surface = [
                x for x in self._surface_event_history
                if now - float(x.get("t", 0.0)) <= 720
            ]
            # Repeated land/reposition cycles become increasingly comment-worthy,
            # but never make speech likely enough to feel deterministic.
            if len(recent_surface) >= 8:
                chance += 0.10
            elif len(recent_surface) >= 5:
                chance += 0.06

            recent_bio = any(
                x.get("name") == "ScanOrganic" and now - float(x.get("t", 0.0)) <= 600
                for x in self._recent_game
            )
            if recent_bio:
                chance += 0.04

        return min(0.18, max(0.0, chance))

    def _schedule_event_opportunity(self, name, event_time):
        if not bool(self.settings.get("enabled", True)):
            return
        if not bool(self.settings.get("event_opportunities", True)):
            return
        if name not in self.EVENT_OPPORTUNITIES:
            return

        session_id = self._session_id
        # Wait briefly so Explorer/Navigator/native replies can claim the moment first.
        delay = random.uniform(2.5, 4.5)
        with self._lock:
            self._event_opportunity_seq += 1
            opportunity_id = self._event_opportunity_seq
            if self._event_timer is not None:
                self._event_timer.cancel()
            timer = threading.Timer(
                delay,
                self._fire_event_opportunity,
                args=(name, event_time, session_id, opportunity_id),
            )
            timer.daemon = True
            self._event_timer = timer
        timer.start()
        log("info", f"TARS Chatter event opportunity queued for {name}.")

    def _event_context(self, name, now, event_time=None):
        recent_surface = [
            x for x in self._surface_event_history
            if now - float(x.get("t", 0.0)) <= 720
        ]
        recent_bio = any(
            x.get("name") == "ScanOrganic" and now - float(x.get("t", 0.0)) <= 600
            for x in self._recent_game
        )
        return {
            "event": name,
            "event_time": event_time if isinstance(event_time, (int, float)) else now,
            "preferred_topics": list(self.EVENT_OPPORTUNITIES.get(name, {}).get("topics", ())),
            "recent_surface_events": len(recent_surface),
            "recent_exobiology": recent_bio,
        }

    def _fire_event_opportunity(self, name, event_time, session_id, opportunity_id=None):
        try:
            if not self._running or session_id != self._session_id:
                return
            with self._lock:
                if (opportunity_id is not None
                        and opportunity_id != self._event_opportunity_seq):
                    return
            if not bool(self.settings.get("enabled", True)) or not bool(
                self.settings.get("event_opportunities", True)
            ):
                return

            now = time.time()
            with self._lock:
                if opportunity_id is None or opportunity_id == self._event_opportunity_seq:
                    self._event_timer = None

            # Global anti-spam: event opportunities never bypass the same minimum
            # remark gap used by timer-driven Chatter.
            try:
                remark_gap = max(360.0, float(self.settings.get("minimum_remark_gap", 420)))
            except (TypeError, ValueError):
                remark_gap = 420.0
            if self._last_chatter_line_time and now - self._last_chatter_line_time < remark_gap:
                return

            speech_cd = float(self.settings.get("speech_cooldown", 45))
            if self._last_assistant_time and now - self._last_assistant_time < min(20.0, speech_cd):
                return
            if self._last_user_activity and now - self._last_user_activity < speech_cd:
                return

            # An Explorer/Navigator-priority event occurring after this event cancels
            # the opportunity before any model call.
            if self._last_game_activity > event_time:
                return

            assistant = self._covas_assistant()
            if assistant is not None and (
                getattr(assistant, "reply_pending", False)
                or getattr(assistant, "is_replying", False)
            ):
                return

            chance = self._event_opportunity_chance(name, now)
            if random.random() >= chance:
                log("info", f"TARS Chatter event opportunity skipped for {name} ({chance:.0%} chance).")
                return

            silence = float(self.settings.get("silence_chance", 40))
            if random.uniform(0, 100) < silence:
                log("info", f"TARS Chatter chose silence for {name} event opportunity.")
                return

            event_context = self._event_context(name, now, event_time)
            candidate = self._prepare_chatter_line(event_context=event_context)
            if candidate is None:
                return

            # Candidate generation itself may take seconds. Recheck all activity.
            if (not self._running or session_id != self._session_id
                    or self._last_assistant_time > now
                    or self._last_user_activity > now
                    or self._last_game_activity > event_time
                    or (assistant is not None and (
                        getattr(assistant, "reply_pending", False)
                        or getattr(assistant, "is_replying", False)))):
                return

            if self._helper is not None:
                self._helper.dispatch_event(
                    PluginEvent(
                        plugin_event_name="TARSChatter",
                        plugin_event_content={
                            "triggered_at": time.time(),
                            "session_id": session_id,
                            "visual": None,
                            "candidate": candidate,
                            "source_event": name,
                        },
                    )
                )
                self._last_event_opportunity_time = time.time()
                log("info", f"TARS Chatter event opportunity dispatched for {name}.")
        except Exception as exc:
            log("error", f"TARS Chatter event opportunity failed for {name}: {exc}")

    # ---------- routine event handling ----------

    def _joined_user_prompt(self, messages):
        chunks = []
        for msg in (messages or [])[-15:]:
            if isinstance(msg, dict) and msg.get("role") == "user":
                chunks.append(str(msg.get("content", "") or ""))
        return "\n".join(chunks).lower()

    def _classify_routine_trigger(self, messages):
        # Only classify the CURRENT event turn. Older Known-only journal events remain
        # in COVAS context, and scanning the whole recent prompt can make a stale
        # ScanOrganicFarEnough/First/Second/Third hijack an unrelated later reply.
        text = ""
        for msg in reversed(messages or []):
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            content = str(msg.get("content", "") or "")
            if content.startswith(("[Ship logbook", "# ", "Current status:")):
                continue
            if not content.startswith(("[Game Event", "[IMPORTANT Game Event", "[Status Event")):
                return None
            text = content.lower()
            break

        if not text:
            return None

        # Check the most specific phrases first.
        if "took the third and final biological sample" in text:
            return "third_sample"
        if "took the second of three biological samples" in text:
            return "second_sample"
        if "took the first of three biological samples" in text:
            return "first_sample"
        if "far enough away to take another sample" in text:
            return "far_enough"
        return None

    def _routine_flight_trigger(self, messages):
        for msg in reversed(messages or []):
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            content = str(msg.get("content", "") or "")
            if content.startswith(("[Ship logbook", "# ", "Current status:")):
                continue
            if not content.startswith(("[Game Event", "[IMPORTANT Game Event", "[Status Event")):
                return None
            text = content.lower()
            if "is approaching" in text and "orbital cruise" in text:
                return "approach_body"
            if "landing gear has been deployed" in text:
                return "landing_gear"
            if "entered atmospheric glide mode" in text:
                return "glide_entry"
            if "glide mode disengaged" in text:
                return "glide_exit"
            if "dropped from supercruise near" in text:
                return "supercruise_exit"
            return None
        return None

    def _routine_fallback(self, routine):
        variants = self.ROUTINE_FALLBACKS.get(routine)
        if not variants:
            return "Noted."
        idx = self._fallback_index[routine] % len(variants)
        self._fallback_index[routine] += 1
        return variants[idx]

    # ---------- spontaneous chatter ----------

    def _should_reply_to_chatter(self, event):
        data = getattr(event, "plugin_event_content", None)
        if not isinstance(data, dict):
            return False
        now = time.time()
        with self._lock:
            if data.get("manual_test") is True:
                accepted = bool(
                    self._running and data.get("session_id") == self._session_id
                    and isinstance(data.get("triggered_at"), (int, float))
                    and 0 <= now - data["triggered_at"] <= 60
                )
                log("info", f"TARS Chatter manual test accepted by event handler: {accepted}.")
                if accepted:
                    self._pending_chatter_reply_at = now
                return accepted
            accepted = bool(
                self._running
                and data.get("session_id") == self._session_id
                and isinstance(data.get("candidate"), str)
                and bool(data["candidate"].strip())
                and isinstance(data.get("triggered_at"), (int, float))
                and 0 <= now - data["triggered_at"] <= 60
                and self._last_assistant_time <= data["triggered_at"]
                and self._last_user_activity <= data["triggered_at"]
                and self._last_game_activity <= data["triggered_at"]
            )
            if accepted:
                self._pending_chatter_reply_at = now
            return accepted

    def _chatter_prompt(self, event):
        data = getattr(event, "plugin_event_content", None)
        if isinstance(data, dict) and data.get("manual_test") is True:
            log("info", "TARS Chatter manual test prompt generated.")
            return "Manual TARS Chatter test. Reply with this exact short line: TARS Chatter is online."
        if isinstance(data, dict) and isinstance(data.get("candidate"), str):
            line = data["candidate"].strip()[:240]
            return ("SPONTANEOUS TARS COMPANION OPPORTUNITY\n"
                    "PREPARED_TARS_LINE: " + json.dumps(line, ensure_ascii=True) + "\n"
                    "This remark was screened before dispatch; deliver it verbatim.")
        return ""

    def _prepare_chatter_line(self, visual=None, event_context=None):
        """Generate and screen a spontaneous line before dispatch.

        v0.9.7 chooses a concrete subject first, then asks the model to write inside
        that lane. This stops context-poor turns from collapsing into cosmic poetry.
        """
        if self._original_generate is None or self._llm_model is None:
            log("warn", "TARS Chatter skipped: no model output director for screened speech.")
            return None
        now = time.time()
        with self._lock:
            scene = dict(self._last_scene)
            session = dict(self._session)
            events = [x["name"] for x in self._recent_game if now - x["t"] <= 90][-4:]
            user_lines = [x["text"][:120] for x in self._user_lines if now - x["t"] < 900][-2:]
            recent = [x["text"][:180] for x in list(self._assistant_lines)[-24:]]
            recent_topics = list(self._recent_chatter_topics)[-8:]
            recent_visuals = [x["text"][:180] for x in list(self._recent_visual_observations)[-8:]]
            blocked_premises = self._blocked_chatter_premises()

        anchors = self._recent_situational_anchors(now, visual, event_context)
        if not anchors:
            log("info", "TARS Chatter stayed silent: no concrete situational anchor in the last 90 seconds.")
            return None
        topics = self._choose_chatter_topics(visual, events, scene, session, anchors=anchors)
        if isinstance(event_context, dict):
            preferred = [
                x for x in event_context.get("preferred_topics", [])
                if x in self.CHATTER_TOPIC_GUIDANCE
            ]
            topics = preferred + [x for x in topics if x not in preferred]
        system = (
            "You are TARS, a dry, restrained, competent ship copilot in Elite Dangerous. "
            "Write ONE short spontaneous companion remark. Sound matter-of-fact, literal, practical, "
            "slightly blunt, and casually witty. The humor should feel incidental, not performed. "
            "Do not be lyrical, poetic, profound, mystical, sentimental, inspirational, or awestruck. "
            "Never write abstract cosmic philosophy. Never personify the universe, galaxy, stars, space, "
            "void, darkness, or silence. Never say they whisper, hide secrets, watch, remember, speak, "
            "wait, judge, refuse answers, tell stories, or communicate. Avoid reflective openings such as "
            "'Sometimes I think' and 'It's strange how'. "
            "Do not recap scan or ship status. Do not invent body properties, visuals, danger, behavior, "
            "ship faults, interface failures, warnings, disabled systems, or shared history. Do not personify microbes or organisms. "
            "A normal cockpit/HUD is background, not an event. A specific physical cockpit feature may earn one dry observation, "
            "but do not keep returning to cockpit/interface jokes. Positive understated observations are allowed too; not every line needs sarcasm. "
            "No generic assistant filler. "
            "Do not use paperwork, filing, bureaucracy, red tape, office/admin chores, or 'humans make simple things complicated' "
            "as generic humor. Those are not standing TARS joke subjects. Also avoid recurring stock premises about humans naming things, "
            "coffee, being the practical copilot, or how repetitive jumping/scanning is if a recent line already used that premise. "
            "A new wording is NOT a new idea. "
            "Every remark MUST be about one concrete supplied situational anchor. If none supports an honest line, reply SKIP. "
            "Do not substitute a generic observation about exploration, exobiology, travel, landing, or space. "
            "Use one natural sentence. Reply SKIP only if no honest concrete angle works."
        )
        anchor_text = json.dumps(anchors, ensure_ascii=True)
        facts = (
            f"CONCRETE SITUATIONAL ANCHORS (all observed within 90 seconds): {anchor_text}.\n"
            f"Supporting confirmed location only: system {scene.get('system', 'unknown')}; "
            f"body {scene.get('body', 'unknown')}. Do not use old location by itself as the premise.\n"
            f"Recent commander words: {json.dumps(user_lines)}.\n"
            f"Recent TARS lines, never repeat their idea: {json.dumps(recent)}.\n"
            f"Recently used chatter topics, avoid if possible: {json.dumps(recent_topics)}.\n"
            f"Chatter premises on cooldown, do not reuse: {json.dumps(blocked_premises)}.\n"
            f"Recent visual observations, never revisit their visual premise: {json.dumps(recent_visuals)}.\n"
        )
        if isinstance(event_context, dict):
            event_name = str(event_context.get("event") or "unknown")
            surface_count = int(event_context.get("recent_surface_events") or 0)
            bio = bool(event_context.get("recent_exobiology"))
            facts += (
                f"Fresh gameplay opportunity: {event_name}. "
                f"Recent surface-operation events in the last 12 minutes: {surface_count}. "
                f"Recent exobiology sampling: {'yes' if bio else 'no'}.\n"
                "The event is permission to consider a remark, not a requirement to speak. "
                "The line must react to one listed concrete anchor without merely announcing it.\n"
            )

        rejection = ""
        # Chatter is optional. Try at most three genuinely different subjects.
        # If the model itself says SKIP, accept the silence immediately instead of
        # shopping across six topics until something is forced into existence.
        for attempt in range(min(3, len(topics))):
            topic = topics[attempt]
            guidance = self.CHATTER_TOPIC_GUIDANCE.get(topic, self.CHATTER_TOPIC_GUIDANCE["copilot"])
            user_prompt = (
                facts
                + f"CHOSEN SUBJECT: {topic}. {guidance}\n"
                + "Make the underlying idea different from recent TARS lines. "
                + "One sentence only. Reply with the line or SKIP."
            )
            if attempt:
                user_prompt += (
                    "\nThe previous candidate was rejected: " + rejection[:180] + ". "
                    "Use this DIFFERENT chosen subject and a different comedic premise. "
                    "Do not salvage or paraphrase the rejected idea."
                )
            try:
                result = self._original_generate(
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user_prompt}],
                    tools=None,
                )
                candidate, actions, usage = result
                try:
                    log_llm_usage(
                        "TARSChatter candidate", model_usage=usage,
                        prompt_usage=PromptUsageStats(
                            system_chars=len(system), conversation_chars=len(user_prompt)),
                        llm_model=self._llm_model,
                    )
                except Exception as exc:
                    log("warn", f"TARS Chatter usage logging failed: {type(exc).__name__}")
                if actions or not isinstance(candidate, str):
                    rejection = "No usable text returned"
                    continue
                candidate = " ".join(candidate.strip().strip('"').split())
                if candidate.upper().startswith("SKIP"):
                    log("info", "TARS Chatter accepted model-selected silence.")
                    return None
                if len(candidate) < 14 or len(candidate) > 220:
                    rejection = "Line too short or too long"
                    continue
                reason = (self._chatter_quality_reason(candidate)
                          or self._repetition_reason(candidate)
                          or self._chatter_premise_reason(candidate))
                if reason:
                    rejection = reason
                    log("info", f"TARS Chatter discarded a weak candidate ({reason}).")
                    continue
                # Remember the generated topic immediately so two timer races cannot select it again.
                with self._lock:
                    self._recent_chatter_topics.append(topic)
                    for premise in self._chatter_premises(candidate):
                        self._chatter_premise_last[premise] = time.time()
                return candidate
            except Exception as exc:
                log("warn", f"TARS Chatter candidate generation failed: {type(exc).__name__}")
                return None
        log("info", f"TARS Chatter gave up after exhausting fresh subjects ({rejection}).")
        return None

    def _delay(self):
        try:
            lo = float(self.settings.get("min_seconds", 180))
            hi = float(self.settings.get("max_seconds", 300))
        except Exception:
            lo, hi = 180.0, 300.0

        # Old persisted settings from 0.10.0 may still contain 90/150. Keep a
        # conservative runtime floor so upgrading actually reduces chatter.
        lo, hi = max(120.0, lo), max(180.0, hi)
        if hi < lo:
            lo, hi = hi, lo
        return random.uniform(lo, hi)

    def _visual_subject_family(self, observation):
        """Coarse visual subject family used only for session-level novelty gating."""
        low = self._normalize(observation or "")
        if not low:
            return "unknown"

        # Physical cockpit geometry is allowed occasionally. UI graphics are not.
        if re.search(r"\b(?:beam|strut|canopy|window frame|viewport frame|cockpit frame|obstruction)\b", low):
            return "cockpit_structure"
        if re.search(r"\b(?:hud|interface|dashboard|display|console|controls?|screen|reticle|readout|menu|indicator|status light)\b", low):
            return "interface"
        if re.search(r"\b(?:ring|rings|ringed)\b", low):
            return "rings"
        if re.search(r"\b(?:terrain|surface|crater|canyon|mountain|ridge|valley|plain|ice field|rock field)\b", low):
            return "surface"
        if re.search(r"\b(?:station|outpost|carrier|dock|megaship|installation)\b", low):
            return "station"
        if re.search(r"\b(?:planet|moon|world|globe|limb|horizon)\b", low):
            return "planetary_view"
        if re.search(r"\b(?:star|sun|stellar)\b", low):
            return "star"
        if re.search(r"\b(?:ship|vessel|craft|fighter|srv)\b", low):
            return "external_vehicle"
        return "scene"

    def _visual_novelty_reason(self, observation):
        """Reject UI chatter and visual ideas already used in this chat session."""
        if not isinstance(observation, str) or not observation.strip():
            return "empty visual observation"

        low = self._normalize(observation)
        family = self._visual_subject_family(observation)

        if family == "interface":
            return "ordinary HUD/interface view"

        if (re.search(r"\b(?:failed|failure|broken|malfunction|fault|offline|disabled|warning|alert|critical|damage|damaged)\b", low)
                and re.search(r"\b(?:hud|interface|display|panel|console|controls?|screen|reticle|readout|indicator|module|system)\b", low)):
            return "UI-derived fault/warning inference"

        words = self._content_words(observation)
        with self._lock:
            recent = list(self._recent_visual_observations)

        for old in recent:
            old_text = str(old.get("text", "") or "")
            old_family = old.get("family")
            old_norm = self._normalize(old_text)
            if not old_norm:
                continue

            if low == old_norm:
                return "exact repeated visual observation"

            seq = difflib.SequenceMatcher(None, low, old_norm).ratio()
            old_words = self._content_words(old_text)
            overlap = 0.0
            if words and old_words:
                overlap = len(words & old_words) / max(1, len(words | old_words))

            # A cockpit beam/strut observation is allowed once per chat session.
            if family == "cockpit_structure" and old_family == "cockpit_structure":
                return "cockpit feature already used this session"

            if seq >= 0.72:
                return f"near-duplicate visual description ({seq:.0%})"
            if len(words) >= 3 and len(old_words) >= 3 and overlap >= 0.45:
                return f"same visual premise ({overlap:.0%} overlap)"

        return None

    def _remember_visual_observation(self, observation):
        with self._lock:
            self._recent_visual_observations.append({
                "t": time.time(),
                "text": observation[:450],
                "family": self._visual_subject_family(observation),
            })

    def _visual_observation(self, now):
        """Call the registered COVAS vision action only when enabled and permitted."""
        if not bool(self.settings.get("vision_enabled", False)):
            return None
        with self._lock:
            if not self._recent_game or now - self._recent_game[-1]["t"] > 240:
                return None
            try:
                interval = max(300.0, float(self.settings.get("vision_interval_minutes", 15)) * 60)
            except (TypeError, ValueError):
                interval = 900.0
            if now - self._last_visual_attempt < interval:
                return None

        helper = self._helper
        manager = self._covas_action_manager()
        if (manager is None or self._covas_vision_model() is None
                or getattr(manager, "allowed_actions", {}).get("getVisuals") is not True):
            return None
        action = getattr(manager, "actions", {}).get("getVisuals")
        if not isinstance(action, dict) or not callable(action.get("method")):
            return None

        with self._lock:
            self._last_visual_attempt = now

        try:
            states = self._covas_current_states()
            if states is None:
                return None
            result = action["method"]({
                "query": (
                    "Inspect the current Elite Dangerous screenshot for ONE concrete visual subject worth a brief companion remark. "
                    "Strongly prefer the OUTSIDE SCENE or a specific physical object: an unusually framed planet or moon, rings, star, "
                    "station approach, surface terrain, close external object, or striking composition. A physical cockpit beam, strut, "
                    "canopy obstruction, or odd structural design may qualify occasionally. "
                    "IGNORE ordinary HUD graphics, reticles, menus, text, scan frames, dashboards, status colors, indicators, panels, "
                    "and generic cockpit layout. Never infer a warning, COM problem, interface fault, module state, disabled system, "
                    "damage, or other ship condition from UI appearance or color. Do not call an ordinary starfield notable. "
                    "Reply NONE if there is no specific visual subject worth interrupting for. Otherwise reply NOTABLE: followed by "
                    "one short literal observation describing only what is visibly present. Do not guess identity, species, location, "
                    "system state, discovery status, or numeric values."
                )
            }, states)
        except Exception as exc:
            log("warn", f"TARS Chatter visual lookup skipped: {exc}")
            return None

        if not isinstance(result, str):
            return None
        result = " ".join(result.strip().split())
        if not result.upper().startswith("NOTABLE:"):
            return None
        observation = result[len("NOTABLE:"):].strip()[:450]
        if not observation or len(observation) < 12 or "error" in observation.lower():
            return None
        novelty_reason = self._visual_novelty_reason(observation)
        if novelty_reason:
            log("info", f"TARS Chatter suppressed visual observation ({novelty_reason}).")
            return None
        self._remember_visual_observation(observation)
        return observation

    def _schedule_next(self, delay=None):
        if not self._running:
            return

        if delay is None:
            delay = self._delay() if bool(self.settings.get("enabled", True)) else 30.0

        timer = threading.Timer(delay, self._fire)
        timer.daemon = True

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = timer

        timer.start()
        log("info", f"TARS Chatter next opportunity scheduled in {delay:.0f} seconds.")

    def _fire(self):
        try:
            if not self._running:
                return
            session_id = self._session_id

            if not bool(self.settings.get("enabled", True)):
                self._schedule_next(30.0)
                return

            now = time.time()
            speech_cd = float(self.settings.get("speech_cooldown", 45))
            activity_cd = float(self.settings.get("activity_cooldown", 15))
            try:
                remark_gap = max(360.0, float(self.settings.get("minimum_remark_gap", 420)))
            except (TypeError, ValueError):
                remark_gap = 420.0

            if self._last_chatter_line_time and now - self._last_chatter_line_time < remark_gap:
                self._schedule_next(max(5.0, remark_gap - (now - self._last_chatter_line_time)))
                return

            if self._last_assistant_time:
                elapsed = now - self._last_assistant_time
                # Ordinary COVAS event replies are frequent during exploration.
                # Give those 20 seconds of space; reserve the full configured
                # cooldown for a previous spontaneous Chatter line.
                pause = (speech_cd if self._last_chatter_line_time == self._last_assistant_time
                         else min(20.0, speech_cd))
                if elapsed < pause:
                    log("info", f"TARS Chatter deferred: recent assistant speech ({pause:.0f}s pause).")
                    self._schedule_next(max(5.0, pause - elapsed + 2.0))
                    return

            if self._last_game_activity:
                elapsed = now - self._last_game_activity
                if elapsed < activity_cd:
                    log("info", "TARS Chatter deferred: recent game activity.")
                    self._schedule_next(max(10.0, activity_cd - elapsed + random.uniform(5, 20)))
                    return

            if self._last_user_activity and now - self._last_user_activity < speech_cd:
                log("info", "TARS Chatter deferred: recent user activity.")
                self._schedule_next(max(10.0, speech_cd - (now - self._last_user_activity) + 5))
                return

            assistant = self._covas_assistant()
            if assistant is not None and (
                getattr(assistant, "reply_pending", False)
                or getattr(assistant, "is_replying", False)
            ):
                log("info", "TARS Chatter deferred: COVAS reply in progress.")
                self._schedule_next(10.0)
                return

            silence = float(self.settings.get("silence_chance", 40))
            if random.uniform(0, 100) < silence:
                log("info", "TARS Chatter chose deliberate silence.")
                self._schedule_next()
                return

            visual = self._visual_observation(now)
            candidate = self._prepare_chatter_line(visual)
            if candidate is None:
                log("info", "TARS Chatter skipped: no original remark worth interrupting with.")
                self._schedule_next(max(120.0, self._delay()))
                return
            if not self._running or session_id != self._session_id:
                return
            # Screenshot and candidate calls can take seconds; recheck activity.
            if (self._last_assistant_time > now or self._last_user_activity > now
                    or self._last_game_activity > now
                    or (assistant is not None and (
                        getattr(assistant, "reply_pending", False)
                        or getattr(assistant, "is_replying", False)))):
                log("info", "TARS Chatter deferred: new activity during visual check.")
                self._schedule_next(10.0)
                return

            if self._helper is not None:
                self._helper.dispatch_event(
                    PluginEvent(
                        plugin_event_name="TARSChatter",
                        plugin_event_content={
                            "triggered_at": time.time(),
                            "session_id": session_id,
                            "visual": visual,
                            "candidate": candidate,
                        }
                    )
                )
                log("info", "TARS Chatter spontaneous event dispatched.")

            self._schedule_next()

        except Exception as exc:
            log("error", f"TARS Director chatter cycle failed: {exc}")
            if self._running:
                self._schedule_next(30.0)

    # ---------- persistence ----------

    def _load_state(self):
        if not self._state_path or not os.path.exists(self._state_path):
            return

        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # v0.4 used "assistant"; v0.5 accepts it for migration.
            assistant = data.get("assistant", data.get("assistant_lines", []))
            for item in assistant:
                if isinstance(item, dict) and item.get("text"):
                    self._assistant_lines.append(item)
                elif isinstance(item, str):
                    self._assistant_lines.append({"t": 0.0, "text": item})

            for item in data.get("episodes", []):
                if isinstance(item, dict):
                    self._episodes.append(item)

            self._theme_last.update(data.get("theme_last", data.get("theme_last_used", {})))
            self._chatter_premise_last.update(data.get("chatter_premise_last", {}))
            self._theme_feedback.update(data.get("theme_feedback", {}))
            for topic in data.get("recent_chatter_topics", []):
                if isinstance(topic, str) and topic in self.CHATTER_TOPIC_GUIDANCE:
                    self._recent_chatter_topics.append(topic)

            log("info", f"TARS Director loaded {len(self._assistant_lines)} persistent recent lines.")
        except Exception as exc:
            log("error", f"TARS Director memory load failed: {exc}")

    def _save_state(self):
        if not self._state_path:
            return

        try:
            size = int(float(self.settings.get("history_size", 30)))
            size = max(10, min(60, size))

            payload = {
                "version": 7,
                "assistant": list(self._assistant_lines)[-size:],
                "episodes": list(self._episodes)[-60:],
                "theme_last": dict(self._theme_last),
                "chatter_premise_last": dict(self._chatter_premise_last),
                "theme_feedback": dict(self._theme_feedback),
                "recent_chatter_topics": list(self._recent_chatter_topics)[-12:],
            }

            tmp = self._state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._state_path)

        except Exception as exc:
            log("error", f"TARS Director memory save failed: {exc}")
