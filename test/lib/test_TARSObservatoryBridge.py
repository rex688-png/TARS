import importlib.util
import json
from pathlib import Path
import sys
import types
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lib.PluginBase import PluginManifest


PLUGIN_PATH = (
    REPO_ROOT
    / "vendor"
    / "tars-plugins"
    / "plugins"
    / "TARSObservatoryBridge"
    / "TARSObservatoryBridge.py"
)
SPEC = importlib.util.spec_from_file_location("_tars_observatory_bridge_test", PLUGIN_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
plugin_helper_stub = types.ModuleType("lib.PluginHelper")
plugin_helper_stub.PluginHelper = object


class PluginEvent:
    def __init__(self, *, plugin_event_name, plugin_event_content):
        self.plugin_event_name = plugin_event_name
        self.plugin_event_content = plugin_event_content


plugin_helper_stub.PluginEvent = PluginEvent
with patch.dict(sys.modules, {"lib.PluginHelper": plugin_helper_stub}):
    SPEC.loader.exec_module(MODULE)
TARSObservatoryBridge = MODULE.TARSObservatoryBridge


class RecordingHelper:
    def __init__(self):
        self.events = []

    def dispatch_event(self, event):
        self.events.append(event)


def _bridge():
    plugin = TARSObservatoryBridge(
        PluginManifest(json.dumps(MODULE.TARS_OBSERVATORY_BRIDGE_MANIFEST))
    )
    plugin.settings = {}
    return plugin


def _realtime_fact(event_id: str = "evt-1") -> dict:
    return {
        "event_id": event_id,
        "realtime": True,
        "monitor_mode": "realtime",
        "batch": False,
        "fact_type": "notification:BioInsights",
        "source_plugin": "BioInsights",
        "body": "A 2",
    }


def test_official_plugin_is_vendored_only_once():
    assert PLUGIN_PATH.is_file()
    assert not (REPO_ROOT / "src" / "plugins" / "TARSObservatoryBridge.py").exists()


def test_default_path_uses_local_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert _bridge()._configured_events_path() == (
        tmp_path / "TARS" / "observatory" / "events.jsonl"
    )


def test_realtime_notification_is_relayed_once():
    bridge = _bridge()
    helper = RecordingHelper()
    bridge._helper = helper
    line = (json.dumps(_realtime_fact()) + "\n").encode("utf-8")

    assert bridge._process_line(line) is True
    assert bridge._process_line(line) is True
    assert len(helper.events) == 1
    assert helper.events[0].plugin_event_name == "TARSObservatoryFact"
    assert helper.events[0].plugin_event_content == _realtime_fact()
    assert bridge._status["relayed"] == 1


def test_historical_and_non_notification_records_are_consumed_without_dispatch():
    bridge = _bridge()
    helper = RecordingHelper()
    bridge._helper = helper
    historical = {
        **_realtime_fact("old-1"),
        "realtime": False,
        "monitor_mode": "read_all",
        "batch": True,
    }
    non_notification = {
        **_realtime_fact("status-1"),
        "fact_type": "status:BioInsights",
    }

    assert bridge._process_line((json.dumps(historical) + "\n").encode()) is True
    assert bridge._process_line((json.dumps(non_notification) + "\n").encode()) is True
    assert helper.events == []
    assert bridge._status["ignored_historical"] == 1
    assert bridge._status["ignored_non_notification"] == 1


def test_missing_log_is_nonfatal_and_new_log_is_read_from_start(tmp_path):
    bridge = _bridge()
    helper = RecordingHelper()
    bridge._helper = helper
    bridge._events_path = tmp_path / "observatory" / "events.jsonl"
    bridge._state_path = tmp_path / "cursor.json"
    bridge._running.set()

    bridge._load_cursor()
    bridge._poll_once()
    assert helper.events == []

    bridge._events_path.parent.mkdir()
    bridge._events_path.write_text(json.dumps(_realtime_fact()) + "\n", encoding="utf-8")
    bridge._poll_once()
    assert len(helper.events) == 1


def test_first_existing_log_and_replacement_attach_at_eof(tmp_path):
    bridge = _bridge()
    helper = RecordingHelper()
    bridge._helper = helper
    events = tmp_path / "events.jsonl"
    events.write_text(json.dumps(_realtime_fact("old")) + "\n", encoding="utf-8")
    bridge._events_path = events
    bridge._state_path = tmp_path / "cursor.json"
    bridge._running.set()

    bridge._load_cursor()
    bridge._poll_once()
    assert helper.events == []

    replacement = tmp_path / "replacement.jsonl"
    replacement.write_text(json.dumps(_realtime_fact("rotated-old")) + "\n", encoding="utf-8")
    replacement.replace(events)
    bridge._poll_once()
    assert helper.events == []

    with events.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(_realtime_fact("new")) + "\n")
    bridge._poll_once()
    assert [event.plugin_event_content["event_id"] for event in helper.events] == ["new"]


def test_cursor_and_recent_ids_survive_restart(tmp_path):
    events = tmp_path / "events.jsonl"
    state = tmp_path / "cursor.json"

    first = _bridge()
    first._helper = RecordingHelper()
    first._events_path = events
    first._state_path = state
    first._running.set()
    first._load_cursor()
    events.write_text(json.dumps(_realtime_fact("same")) + "\n", encoding="utf-8")
    first._poll_once()

    second = _bridge()
    second_helper = RecordingHelper()
    second._helper = second_helper
    second._events_path = events
    second._state_path = state
    second._running.set()
    second._load_cursor()
    with events.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(_realtime_fact("same")) + "\n")
    second._poll_once()

    assert second_helper.events == []
    assert second._offset == events.stat().st_size


def test_prompt_is_short_and_fact_preserving():
    prompt = _bridge()._prompt_observatory_fact(
        PluginEvent(
            plugin_event_name="TARSObservatoryFact",
            plugin_event_content={"fact_type": "notification:Evaluator", "value": 123},
        )
    )

    assert "short natural exploration callout" in prompt
    assert "do not invent missing values" in prompt
    assert '"value":123' in prompt


def test_plugin_lifecycle_registers_fact_and_diagnostics_with_missing_feed(monkeypatch, tmp_path):
    from unittest.mock import MagicMock
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    helper = MagicMock()
    helper.get_plugin_data_path.return_value = str(tmp_path / "plugin-data")
    bridge = _bridge()
    try:
        bridge.on_chat_start(helper)
        thread = bridge._thread
        assert thread is not None and thread.is_alive()
        assert helper.register_event.call_args.kwargs["name"] == "TARSObservatoryFact"
        action = helper.register_action.call_args.kwargs
        assert action["name"] == "tars_observatory_diagnostics"
        assert callable(action["method"])
        assert not bridge._events_path.exists()
        helper.dispatch_event.assert_not_called()
    finally:
        bridge.on_chat_stop(helper)
    assert not thread.is_alive()
    assert bridge._status["state"] == "stopped"
    assert (tmp_path / "plugin-data" / "observatory_cursor.json").is_file()
