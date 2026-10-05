#!/usr/bin/env python3
"""Deterministic, side-effect-isolated TARS baseline evidence.

This tool loads the five real TARS plugin entrypoints from the separate
TARS-Plugins checkout.  It uses the production PluginBase/Event types, the real
projection registry, and the real PromptGenerator.  Dangerous leaf effects are
replaced by recorders: model/network/audio/vision/input are never invoked.

The production plugin files and production persistence paths are not modified.
All plugin persistence is redirected to a temporary directory.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import re
import subprocess
import sys
import tempfile
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch


TARS_ROOT = Path(__file__).resolve().parents[1]
TARS_SRC = TARS_ROOT / "src"
PLUGINS_ROOT = TARS_ROOT.parent / "TARS-Plugins"
PLUGIN_DIRECTORY = PLUGINS_ROOT / "plugins"
TARS_BASELINE = "f0153840016e33c498eafd5ea197963bcf776987"
PLUGINS_BASELINE = "685e16a19d5a5cd83f16297b90ee4c58ba8e11b5"
PLUGIN_NAMES = (
    "TARSExplorer",
    "TARSNavigator",
    "TARSGalaxy",
    "TARSChatter",
    "TARSExpedition",
)
FIXED_TIMESTAMP = "2026-10-05T12:00:00+00:00"


def _git_sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _source_ref(callback: Callable[..., Any]) -> str:
    source = inspect.getsourcefile(callback) or "<unknown>"
    try:
        line = inspect.getsourcelines(callback)[1]
    except (OSError, TypeError):
        line = 0
    path = Path(source).resolve()
    for root, label in ((PLUGINS_ROOT, "TARS-Plugins"), (TARS_ROOT, "TARS")):
        try:
            return f"{label}/{path.relative_to(root).as_posix()}:{line}"
        except ValueError:
            pass
    return f"<external>:{line}"


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if isinstance(value, dict):
        return {str(key): _jsonable(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted((_jsonable(item) for item in value), key=repr)
    if isinstance(value, Path):
        return f"<PATH>/{value.name}"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def adapt_action_callback(callback: Callable[..., Any]) -> tuple[Callable[[Any, dict], Any], int]:
    """Adapt a plugin action once, based on its registered bound signature.

    This is intentionally registration-time inspection.  It never executes a
    callback and retries after TypeError, so a mutating callback runs at most once.
    Production code is not changed by this evidence helper.
    """
    signature = inspect.signature(callback)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    has_varargs = any(
        parameter.kind == inspect.Parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )
    arity = 2 if has_varargs else len(positional)
    if arity == 1:
        return (lambda model, context: callback(model)), 1
    if arity >= 2:
        return (lambda model, context: callback(model, context)), arity
    raise TypeError(f"Unsupported plugin action callback signature: {signature}")


class FakeModel:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate(self, messages, tools=None, tool_choice=None):
        from lib.Logger import ModelUsageStats

        self.calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        return ("TEST_RESPONSE", None, ModelUsageStats())


class FakeAssistant:
    reply_pending = False
    is_replying = False

    def __init__(self) -> None:
        self.should_reply_handlers: list[Callable[..., Any]] = []

    def register_should_reply_handler(self, handler: Callable[..., Any]) -> None:
        self.should_reply_handlers.append(handler)


class FakeEventManager:
    def __init__(self) -> None:
        self.events: list[Any] = []
        self.states: dict[str, Any] = {}

    def get_current_state(self):
        return (self.events, self.states)


class FakeActionManager:
    def __init__(self) -> None:
        self.actions = {
            "getVisuals": {
                "method": lambda args, states: "TEST_VISUAL_OBSERVATION",
                "type": "global",
            }
        }


@dataclass
class Registration:
    name: str
    description: str
    parameters: dict[str, Any]
    action_type: str
    callback: Callable[[Any, dict], Any] = field(repr=False)
    parameter_model: type = field(repr=False, default=object)
    callback_arity: int = 0
    source: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "callback_arity": self.callback_arity,
            "description": self.description,
            "name": self.name,
            "parameters": _jsonable(self.parameters),
            "source": self.source,
        }


class RecordingHelper:
    """Small adapter around the production PluginHelper registration contract."""

    def __init__(self, data_root: Path, prompt_generator=None) -> None:
        self.data_root = data_root
        self.prompt_generator = prompt_generator
        self.actions: list[Registration] = []
        self.events: list[dict[str, Any]] = []
        self.sideeffects: list[Callable[..., Any]] = []
        self.status_generators: list[Callable[..., Any]] = []
        self.dispatched: list[Any] = []
        self._llm_model = FakeModel()
        self.llm_model = self._llm_model
        self._assistant = FakeAssistant()
        self.assistant = self._assistant
        self._event_manager = FakeEventManager()
        self.event_manager = self._event_manager
        self._action_manager = FakeActionManager()
        self.action_manager = self._action_manager
        self._vision_model = None
        self.vision_model = None
        self._config: dict[str, Any] = {}
        self.config = self._config

    def get_plugin_data_path(self, manifest) -> str:
        path = self.data_root / manifest.guid
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def register_action(
        self,
        name,
        description,
        parameters,
        method,
        action_type="ship",
        input_template=None,
    ) -> None:
        callback, arity = adapt_action_callback(method)
        schema = parameters.model_json_schema()
        self.actions.append(
            Registration(
                name=name,
                description=description,
                parameters=schema,
                action_type=action_type,
                callback=callback,
                parameter_model=parameters,
                callback_arity=arity,
                source=_source_ref(method),
            )
        )

    def register_event(self, name, should_reply_check, prompt_generator) -> None:
        self.events.append(
            {
                "name": name,
                "prompt_source": _source_ref(prompt_generator),
                "reply_source": _source_ref(should_reply_check),
            }
        )

    def register_sideeffect(self, sideeffect) -> None:
        self.sideeffects.append(sideeffect)

    def register_status_generator(self, generator) -> None:
        self.status_generators.append(generator)
        if self.prompt_generator is not None:
            self.prompt_generator.register_status_generator(generator)

    def dispatch_event(self, event) -> None:
        self.dispatched.append(event)


def _install_plugin_helper_stub() -> None:
    from lib.Event import PluginEvent

    module = types.ModuleType("lib.PluginHelper")
    module.PluginHelper = RecordingHelper
    module.PluginEvent = PluginEvent
    module.ProjectedStates = dict
    sys.modules["lib.PluginHelper"] = module


def _manifest(plugin_name: str):
    from lib.PluginBase import PluginManifest

    text = (PLUGIN_DIRECTORY / plugin_name / "manifest.json").read_text(encoding="utf-8")
    return PluginManifest(text)


def _load_plugin(plugin_name: str):
    from lib.PluginBase import PluginBase

    manifest = _manifest(plugin_name)
    dotted = f"{plugin_name}.{Path(manifest.entrypoint).stem}"
    module = importlib.import_module(dotted)
    candidates = [
        value
        for value in vars(module).values()
        if isinstance(value, type) and issubclass(value, PluginBase) and value is not PluginBase
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one plugin class in {dotted}, found {len(candidates)}")
    plugin = candidates[0](manifest)
    plugin.settings = {}
    return manifest, plugin, dotted


def _literal_native_tools() -> list[dict[str, Any]]:
    """Read the nested native finder schemas from the real web agent source."""
    source_path = TARS_SRC / "lib" / "actions" / "actions_web.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "web_search_agent":
            for inner in node.body:
                if isinstance(inner, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "tools" for target in inner.targets
                ):
                    tools = ast.literal_eval(inner.value)
                    result = []
                    for tool in tools:
                        function = tool["function"]
                        result.append(
                            {
                                "description": function["description"],
                                "name": function["name"],
                                "parameters": function["parameters"],
                                "registration": "nested web_search_agent tool",
                                "source": "TARS/src/lib/actions/actions_web.py:126",
                            }
                        )
                    return sorted(result, key=lambda item: item["name"])
    raise RuntimeError("Could not locate web_search_agent tools literal")


def _literal_registered_actions() -> list[dict[str, Any]]:
    """Extract literal top-level ActionManager registrations without running effects."""
    results: list[dict[str, Any]] = []
    for relative in (
        Path("lib/actions/Actions.py"),
        Path("lib/actions/actions_web.py"),
        Path("lib/actions/actions_ui.py"),
        Path("lib/actions/actions_genui.py"),
    ):
        source_path = TARS_SRC / relative
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "registerAction" or len(node.args) < 3:
                continue
            try:
                name = ast.literal_eval(node.args[0])
                description = ast.literal_eval(node.args[1])
                parameters = ast.literal_eval(node.args[2])
            except (ValueError, TypeError):
                continue
            if isinstance(name, str) and isinstance(parameters, dict):
                results.append(
                    {
                        "description": description,
                        "name": name,
                        "parameters": parameters,
                        "registration": "ActionManager.registerAction",
                        "source": f"TARS/src/{relative.as_posix()}:{node.lineno}",
                    }
                )
    unique = {item["name"]: item for item in results}
    return [unique[name] for name in sorted(unique)]


def _projection_states():
    from lib.Projections import registerProjections

    class SystemDatabaseStub:
        def get_bodies(self, *args, **kwargs):
            return []

        def get_system(self, *args, **kwargs):
            return None

        def get_system_info(self, *args, **kwargs):
            return None

        def get_stations(self, *args, **kwargs):
            return []

    class ProjectionCollector:
        def __init__(self) -> None:
            self.projections = []

        def register_projection(self, projection) -> None:
            projection.state = projection.get_default_state()
            self.projections.append(projection)

    collector = ProjectionCollector()
    registerProjections(collector, SystemDatabaseStub(), 300, 100000)
    states = {projection.__class__.__name__: projection.state for projection in collector.projections}
    states["CurrentStatus"].flags.InMainShip = True
    states["CurrentStatus"].GuiFocus = "NoFocus"
    states["Location"].StarSystem = "TEST_SYSTEM"
    states["Location"].StarPos = [1.0, 2.0, 3.0]
    return states


def _prompt_fixture(name: str, prompt_generator, states, memory: bool = False) -> list[dict[str, str]]:
    from lib.Event import GameEvent, MemoryEvent

    content: dict[str, Any] = {
        "event": "Location",
        "StarSystem": "TEST_SYSTEM",
        "StarPos": [1.0, 2.0, 3.0],
        "timestamp": FIXED_TIMESTAMP,
    }
    if name == "route":
        content = {
            "event": "NavRoute",
            "Route": [
                {"StarSystem": "TEST_SYSTEM", "StarClass": "K", "Scoopable": True},
                {"StarSystem": "TEST_DESTINATION", "StarClass": "G", "Scoopable": True},
            ],
            "timestamp": FIXED_TIMESTAMP,
        }
    event = GameEvent(content=content, historic=False)
    memories = []
    if memory:
        memories = [
            MemoryEvent(
                content="TEST_CMDR prefers deterministic synthetic evidence.",
                metadata={"time_until": 1760000000.0},
                embedding=[],
            )
        ]
    messages, _usage = prompt_generator.generate_prompt([event], states, [], memories)
    normalized = _jsonable(messages)
    # PromptGenerator intentionally emits current display times. Freeze only
    # those fields; all domain content remains the real generator output.
    for message in normalized:
        if isinstance(message.get("content"), str):
            message["content"] = re.sub(
                r"player_time: \d{4}-\d{2}-\d{2} \d{2}:\d{2}",
                "player_time: 2026-10-05 12:00",
                message["content"],
            )
            message["content"] = re.sub(
                r"elite_time: \d{4}-\d{2}-\d{2} \d{2}:\d{2}",
                "elite_time: 3312-10-05 12:00",
                message["content"],
            )
    return normalized


def build_baseline() -> dict[str, Any]:
    if _git_sha(TARS_ROOT) != TARS_BASELINE:
        raise RuntimeError("TARS checkout differs from the pinned baseline")
    if _git_sha(PLUGINS_ROOT) != PLUGINS_BASELINE:
        raise RuntimeError("TARS-Plugins checkout differs from the pinned baseline")

    sys.path.insert(0, str(TARS_SRC))
    sys.path.insert(0, str(PLUGIN_DIRECTORY))

    import pysqlite3
    import sqlite_vec
    from lib.Database import set_connection_for_testing

    connection = pysqlite3.connect(":memory:")
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    set_connection_for_testing(connection)
    _install_plugin_helper_stub()

    from lib.Event import GameEvent
    from lib.PromptGenerator import PromptGenerator

    class SystemDatabaseStub:
        def get_bodies(self, *args, **kwargs):
            return []

        def get_system(self, *args, **kwargs):
            return None

        def get_system_info(self, *args, **kwargs):
            return None

        def get_stations(self, *args, **kwargs):
            return []

    character_prompt = (PLUGINS_ROOT / "prompt" / "prompt.txt").read_text(encoding="utf-8")
    prompt_generator = PromptGenerator(
        "TEST_CMDR", character_prompt, [], SystemDatabaseStub()
    )

    plugin_rows: list[dict[str, Any]] = []
    reached_modules: set[str] = set()
    prompt_fixtures: dict[str, Any] = {}
    scenario_trace: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="tars-baseline-") as temporary:
        isolated_root = Path(temporary)
        with patch("pathlib.Path.home", return_value=isolated_root), patch.dict(
            "os.environ", {"USERPROFILE": str(isolated_root)}, clear=False
        ):
            for plugin_name in PLUGIN_NAMES:
                before = set(sys.modules)
                manifest, plugin, dotted = _load_plugin(plugin_name)
                helper = RecordingHelper(isolated_root / "plugin_data", prompt_generator)
                plugin.on_chat_start(helper)

                event_payloads = [
                    {
                        "event": "Location",
                        "StarSystem": "TEST_SYSTEM",
                        "SystemAddress": 1001,
                        "StarPos": [1.0, 2.0, 3.0],
                        "timestamp": FIXED_TIMESTAMP,
                    }
                ]
                if plugin_name == "TARSExplorer":
                    event_payloads.append(
                        {
                            "event": "Scan",
                            "BodyName": "TEST_SYSTEM A 1",
                            "BodyID": 1,
                            "SystemAddress": 1001,
                            "PlanetClass": "Water world",
                            "timestamp": FIXED_TIMESTAMP,
                        }
                    )
                if plugin_name == "TARSNavigator":
                    event_payloads.append(
                        {
                            "event": "NavRoute",
                            "Route": [
                                {"StarSystem": "TEST_SYSTEM", "StarPos": [1, 2, 3]},
                                {"StarSystem": "TEST_DESTINATION", "StarPos": [4, 5, 6]},
                            ],
                            "timestamp": FIXED_TIMESTAMP,
                        }
                    )
                for payload in event_payloads:
                    event = GameEvent(content=payload, historic=False)
                    for sideeffect in helper.sideeffects:
                        sideeffect(event, {})

                invoked_action = None
                preferred = {
                    "TARSExplorer": "tars_explorer_status",
                    "TARSNavigator": "tars_navigator_status",
                    # Galaxy query actions are network-backed; registration and
                    # live-location observation are exercised, invocation is not.
                    "TARSGalaxy": None,
                    "TARSExpedition": "tars_expedition_status",
                }.get(plugin_name)
                for registration in helper.actions:
                    if registration.name == preferred:
                        registration.callback(registration.parameter_model(), {})
                        invoked_action = registration.name
                        break

                chatter_contract = None
                if plugin_name == "TARSChatter":
                    messages = [
                        {
                            "role": "system",
                            "content": "The universe of Elite:Dangerous is your reality. Your character prompt is: TARS",
                        },
                        {"role": "user", "content": "Report status for TEST_CMDR."},
                    ]
                    result = helper._llm_model.generate(messages=messages, tools=None, tool_choice=None)
                    chatter_contract = {
                        "actions_is_none": result[1] is None,
                        "result_length": len(result),
                        "text_type": type(result[0]).__name__,
                        "usage_type": type(result[2]).__name__,
                    }
                    prompt_fixtures["chatter_directed"] = _jsonable(
                        helper._llm_model.calls[-1]["messages"]
                    )

                plugin.on_chat_stop(helper)
                reached = {
                    name
                    for name in set(sys.modules) - before
                    if name.startswith(("TARS", "_tars_"))
                }
                reached.add(dotted)
                reached_modules.update(reached)
                plugin_rows.append(
                    {
                        "actions": [item.public() for item in sorted(helper.actions, key=lambda x: x.name)],
                        "chatter_contract": chatter_contract,
                        "entrypoint": manifest.entrypoint,
                        "events": sorted(helper.events, key=lambda item: item["name"]),
                        "guid": manifest.guid,
                        "module": dotted,
                        "name": manifest.name,
                        "sideeffects": sorted(_source_ref(item) for item in helper.sideeffects),
                        "status_generators": sorted(
                            _source_ref(item) for item in helper.status_generators
                        ),
                        "version": manifest.version,
                    }
                )
                scenario_trace.append(
                    {
                        "events": [payload["event"] for payload in event_payloads],
                        "invoked_action": invoked_action,
                        "plugin": plugin_name,
                        "result": "reached under scripted synthetic scenario",
                    }
                )

        states = _projection_states()
        prompt_fixtures["normal_ship"] = _prompt_fixture(
            "normal", prompt_generator, states
        )
        prompt_fixtures["active_route"] = _prompt_fixture(
            "route", prompt_generator, states
        )
        prompt_fixtures["memory_context"] = _prompt_fixture(
            "memory", prompt_generator, states, memory=True
        )

    return {
        "metadata": {
            "baseline_date": "2026-10-05",
            "harness_registration_order": list(PLUGIN_NAMES),
            "plugin_loading_mechanism": (
                "separate checkout; real manifest entrypoints imported as dotted modules from "
                "<WORKSPACE>/TARS-Plugins/plugins; isolated RecordingHelper mirrors registration contract"
            ),
            "runtime_order_note": (
                "PluginManager external discovery uses unsorted os.listdir; runtime order is "
                "filesystem-dependent, while snapshot object collections are stable-sorted"
            ),
            "tars_branch": "main baseline (cloud task branch derived from local work checkout)",
            "tars_plugins_branch": "main baseline (read-only local work checkout)",
            "tars_plugins_sha": _git_sha(PLUGINS_ROOT),
            "tars_sha": _git_sha(TARS_ROOT),
        },
        "native_host": {
            "nested_web_agent_tools": _literal_native_tools(),
            "registered_literal_actions": _literal_registered_actions(),
            "registration_conditions": {
                "ActionManager.getToolsList": [
                    "active game mode/action type",
                    "tools_var and uses_actions",
                    "uses_web_actions",
                    "uses_ui_actions",
                    "allowed action permission flags",
                    "in-station state for in_station actions",
                ],
                "register_actions": [
                    "getVisuals only when a vision model exists",
                    "remember_memories only when an embedding model exists",
                    "generate_ui only when overlay_show_hud is enabled",
                ],
            },
        },
        "plugins": sorted(plugin_rows, key=lambda item: item["name"]),
        "prompt_fixtures": prompt_fixtures,
        "runtime_trace": {
            "imported_plugin_modules_reached": sorted(reached_modules),
            "scenario_a": "real plugin entrypoints loaded and lifecycle registrations captured",
            "scenario_b": scenario_trace,
            "scope_note": "reached under these scenarios; not a complete dependency list",
        },
    }


def write_snapshots(baseline: dict[str, Any], snapshot_root: Path) -> None:
    snapshot_root.mkdir(parents=True, exist_ok=True)
    tool_schema = {
        "metadata": baseline["metadata"],
        "native_host": baseline["native_host"],
        "plugins": [
            {"actions": plugin["actions"], "name": plugin["name"]}
            for plugin in baseline["plugins"]
        ],
    }
    files = {
        "tool_schema.json": tool_schema,
        "prompt_normal_ship.json": baseline["prompt_fixtures"]["normal_ship"],
        "prompt_active_route.json": baseline["prompt_fixtures"]["active_route"],
        "prompt_memory_context.json": baseline["prompt_fixtures"]["memory_context"],
        "prompt_chatter_directed.json": baseline["prompt_fixtures"]["chatter_directed"],
    }
    for name, value in files.items():
        (snapshot_root / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-snapshots", action="store_true")
    args = parser.parse_args()
    baseline = build_baseline()
    rendered = json.dumps(baseline, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    if args.write_snapshots:
        write_snapshots(baseline, TARS_ROOT / "tests" / "snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
