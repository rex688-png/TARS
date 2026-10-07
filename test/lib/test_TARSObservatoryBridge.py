import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.PluginBase import PluginManifest
from plugins.TARSObservatoryBridge import (
    TARS_OBSERVATORY_BRIDGE_MANIFEST,
    TARSObservatoryBridge,
)


class RecordingHelper:
    def __init__(self):
        self.events = []

    def dispatch_event(self, event):
        self.events.append(event)


def _bridge() -> TARSObservatoryBridge:
    plugin = TARSObservatoryBridge(
        PluginManifest(json.dumps(TARS_OBSERVATORY_BRIDGE_MANIFEST))
    )
    plugin.settings = {}
    return plugin


def test_realtime_notification_is_relayed_once():
    bridge = _bridge()
    helper = RecordingHelper()
    bridge._helper = helper
    fact = {
        "event_id": "evt-1",
        "realtime": True,
        "monitor_mode": "realtime",
        "batch": False,
        "fact_type": "notification:BioInsights",
        "source_plugin": "BioInsights",
        "body": "A 2",
    }
    line = (json.dumps(fact) + "\n").encode("utf-8")

    assert bridge._process_line(line) is True
    assert bridge._process_line(line) is True
    assert len(helper.events) == 1
    assert helper.events[0].plugin_event_name == "TARSObservatoryFact"
    assert helper.events[0].plugin_event_content == fact
    assert bridge._status["relayed"] == 1


def test_historical_and_non_notification_records_are_consumed_without_dispatch():
    bridge = _bridge()
    helper = RecordingHelper()
    bridge._helper = helper

    historical = {
        "event_id": "old-1",
        "realtime": False,
        "monitor_mode": "read_all",
        "batch": True,
        "fact_type": "notification:BioInsights",
    }
    non_notification = {
        "event_id": "status-1",
        "realtime": True,
        "monitor_mode": "realtime",
        "batch": False,
        "fact_type": "status:BioInsights",
    }

    assert bridge._process_line((json.dumps(historical) + "\n").encode()) is True
    assert bridge._process_line((json.dumps(non_notification) + "\n").encode()) is True
    assert helper.events == []
    assert bridge._status["ignored_historical"] == 1
    assert bridge._status["ignored_non_notification"] == 1


def test_first_existing_log_attaches_at_eof(tmp_path):
    bridge = _bridge()
    events = tmp_path / "events.jsonl"
    events.write_text('{"old":true}\n', encoding="utf-8")
    bridge._events_path = events
    bridge._state_path = tmp_path / "cursor.json"

    bridge._load_cursor()

    assert bridge._offset == events.stat().st_size
    persisted = json.loads(bridge._state_path.read_text(encoding="utf-8"))
    assert persisted["offset"] == events.stat().st_size


def test_prompt_passes_fact_to_tars_without_adding_values():
    bridge = _bridge()
    fact = {"fact_type": "notification:Evaluator", "value": 123}
    from lib.PluginHelper import PluginEvent

    prompt = bridge._prompt_observatory_fact(
        PluginEvent(plugin_event_name="TARSObservatoryFact", plugin_event_content=fact)
    )

    assert "Live Elite Observatory notification" in prompt
    assert '"value":123' in prompt
