from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS = ROOT / "tests" / "snapshots"


def _load_dump_module():
    spec = importlib.util.spec_from_file_location(
        "tars_baseline_dump", ROOT / "tools" / "tars_baseline_dump.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dump_module():
    return _load_dump_module()


@pytest.fixture(scope="module")
def plugins_checkout(dump_module):
    if not dump_module.PLUGINS_ROOT.is_dir() or not (
        dump_module.PLUGINS_ROOT / ".git"
    ).exists():
        pytest.skip(
            "requires the separate pinned TARS-Plugins checkout; it is not available"
        )
    try:
        sha = dump_module._git_sha(dump_module.PLUGINS_ROOT)
    except (OSError, subprocess.CalledProcessError) as exc:
        pytest.fail(f"TARS-Plugins path exists but is not a readable Git checkout: {exc}")
    assert sha == dump_module.PLUGINS_BASELINE, (
        "external TARS-Plugins checkout must be at the pinned baseline "
        f"{dump_module.PLUGINS_BASELINE}, found {sha}"
    )
    return dump_module.PLUGINS_ROOT


@pytest.fixture(scope="module")
def baseline(dump_module, plugins_checkout):
    # Real plugins log heavily; their output is not part of the deterministic evidence.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return dump_module.build_baseline()


def _snapshot(name: str):
    return json.loads((SNAPSHOTS / name).read_text(encoding="utf-8"))


def test_tool_schema_snapshot_is_deterministic(baseline):
    expected = _snapshot("tool_schema.json")
    actual = {
        "metadata": baseline["metadata"],
        "native_host": baseline["native_host"],
        "plugins": [
            {"actions": plugin["actions"], "name": plugin["name"]}
            for plugin in baseline["plugins"]
        ],
    }
    assert actual == expected


@pytest.mark.parametrize(
    ("scenario", "snapshot"),
    [
        ("normal_ship", "prompt_normal_ship.json"),
        ("active_route", "prompt_active_route.json"),
        ("memory_context", "prompt_memory_context.json"),
        ("chatter_directed", "prompt_chatter_directed.json"),
    ],
)
def test_prompt_snapshot_is_deterministic(baseline, scenario, snapshot):
    assert baseline["prompt_fixtures"][scenario] == _snapshot(snapshot)


def test_prompt_fixtures_preserve_high_value_context(baseline):
    prompts = baseline["prompt_fixtures"]
    route_text = json.dumps(prompts["active_route"])
    memory_text = json.dumps(prompts["memory_context"])
    chatter_text = json.dumps(prompts["chatter_directed"], ensure_ascii=False)
    assert "TEST_DESTINATION" in route_text
    assert "deterministic synthetic evidence" in memory_text
    assert "TARS DIRECTOR — HIGH PRIORITY CONTINUITY" in chatter_text
    assert prompts["normal_ship"][0]["role"] == "system"
    assert prompts["normal_ship"][-1]["role"] == "user"
    status = next(
        message["content"]
        for message in prompts["active_route"]
        if "# TARS Navigator" in message["content"]
    )
    assert status.index("# Location") < status.index("# TARS Navigator")


def test_navigator_and_expedition_six_one_argument_callbacks_are_captured(baseline):
    plugins = {plugin["name"]: plugin for plugin in baseline["plugins"]}
    navigator = plugins["TARS Navigator"]["actions"]
    expedition = plugins["TARS Expedition"]["actions"]
    assert len(navigator) == 2
    assert len(expedition) == 4
    assert {action["callback_arity"] for action in navigator + expedition} == {1}


def test_callback_adapter_calls_one_argument_callback_once(dump_module):
    calls = []

    def callback(model):
        calls.append(model)
        return "ok"

    adapted, arity = dump_module.adapt_action_callback(callback)
    assert adapted("MODEL", {"ignored": True}) == "ok"
    assert arity == 1
    assert calls == ["MODEL"]


def test_callback_adapter_calls_two_argument_callback_once(dump_module):
    calls = []

    def callback(model, context):
        calls.append((model, context))
        return "ok"

    adapted, arity = dump_module.adapt_action_callback(callback)
    assert adapted("MODEL", {"key": "value"}) == "ok"
    assert arity == 2
    assert calls == [("MODEL", {"key": "value"})]


def test_callback_adapter_does_not_retry_callback_type_error(dump_module):
    calls = []

    def callback(model):
        calls.append(model)
        raise TypeError("raised inside mutating callback")

    adapted, _ = dump_module.adapt_action_callback(callback)
    with pytest.raises(TypeError, match="raised inside mutating callback"):
        adapted("MODEL", {})
    assert calls == ["MODEL"]


def test_chatter_generate_contract_is_text_actions_usage_tuple(baseline):
    chatter = next(
        plugin for plugin in baseline["plugins"] if plugin["name"].startswith("TARS Chatter")
    )
    assert chatter["chatter_contract"] == {
        "actions_is_none": True,
        "result_length": 3,
        "text_type": "str",
        "usage_type": "ModelUsageStats",
    }


def test_native_finder_schema_tripwires(dump_module):
    tools = {tool["name"]: tool for tool in dump_module._literal_native_tools()}
    assert {
        "system_finder",
        "station_finder",
        "body_finder",
        "engineer_finder",
        "blueprint_finder",
        "material_finder",
    } <= tools.keys()
    station = tools["station_finder"]["parameters"]["properties"]
    assert station["reference_system"]["type"] == "string"
    assert station["material_trader"]["type"] == "array"


def test_baseline_commits_are_pinned(baseline, dump_module):
    assert baseline["metadata"]["tars_sha"] == "f0153840016e33c498eafd5ea197963bcf776987"
    assert baseline["metadata"]["tars_plugins_sha"] == "685e16a19d5a5cd83f16297b90ee4c58ba8e11b5"
    assert dump_module._git_is_ancestor(dump_module.TARS_ROOT, dump_module.TARS_BASELINE)
