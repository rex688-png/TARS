"""Real StatusParser -> EventManager -> Session plugin -> host/TTS warning replay."""
import importlib.util
import queue
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_speech_arbiter import arbiter, clock
from test_speech_trace import assistant, user, player, StopPlayback
from lib.Event import StatusEvent
from lib.EventManager import EventManager
from lib.PluginHelper import PluginHelper
from lib.StatusParser import StatusParser, parse_status_json


@pytest.fixture
def rig(arbiter, clock, monkeypatch):
    path = Path(__file__).resolve().parents[2] / 'vendor/tars-plugins/plugins/TARSExplorer/TARSExplorerSession.py'
    spec = importlib.util.spec_from_file_location('_rc20_explorer', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    plugin = module.TARSExplorer(None)
    monkeypatch.setitem(plugin._observe_departure_status.__func__.__globals__, 'time',
                        SimpleNamespace(time=lambda: clock.wall, monotonic=lambda: clock.tick))
    host = assistant([], ['Priority response.'])
    host.config['speech_director_mode'] = 'enforce'
    host._speech_arbiter = arbiter
    host.disabled_game_events = []
    host.reply_pending = False
    host._process_active_quests = lambda *args: None
    manager = EventManager.__new__(EventManager)
    manager.incoming = queue.Queue()
    manager._processing_lock = threading.Lock()
    manager.short_term_memory = Mock()
    manager.update_projections = Mock(return_value=[])
    manager.save_projections = Mock()
    manager.pending, manager.processed, manager.projections = [], [], []
    manager.sideeffects = [host.on_event]
    host.event_manager.incoming = manager.incoming
    helper = PluginHelper.__new__(PluginHelper)
    helper._assistant, helper._event_manager = host, manager
    helper._config, helper._prompt_generator = host.config, host.prompt_generator
    plugin._helper = helper
    plugin._system_name = 'Test'
    helper.register_sideeffect(plugin._observe_event)
    helper.register_event('TARSExplorerTarget', plugin._should_reply_to_target, plugin._prompt_noteworthy_target)
    body = plugin._get_body('Test A 5', 5)
    body.body_type, body.planet_class = 'planet', 'Water world'
    parser = StatusParser.__new__(StatusParser)
    parser.current_status = parse_status_json({'Flags': 16777216, 'Flags2': 0})
    parser.status_queue = queue.Queue()
    parser._read_status_file = Mock(return_value={'Flags': 16777216 | 131072, 'Flags2': 524288})
    def charge(extra=None):
        assert parser._process_status_update()
        while not parser.status_queue.empty():
            manager.add_status_event(parser.status_queue.get_nowait())
        if extra:
            manager.incoming.put(extra)
        manager.process()
        for event in manager.processed:
            event.responded_at = None
        host.event_manager.get_short_term_memory.return_value = list(reversed(manager.processed))
        return manager.processed
    return SimpleNamespace(host=host, plugin=plugin, manager=manager, charge=charge)


@pytest.mark.parametrize('mode', ['off', 'observe', 'enforce'])
def test_real_status_route_is_eligible_before_startjump_without_model_latency(rig, mode):
    rig.host.config['speech_director_mode'] = mode
    events = rig.charge()
    assert events[0].status['event'] == 'Status'
    assert any(isinstance(e, StatusEvent) and e.status['event'] == 'FsdCharging' for e in events)
    assert events[-1].plugin_event_content['warning_trigger'] == 'FsdHyperdriveCharging'
    assert rig.host.reply_pending
    rig.host.reply_thread({})
    assert rig.host.llmModel.calls == 0
    rig.host.prompt_generator.generate_prompt.assert_not_called()
    rig.host.tts.say.assert_called_once()
    text = rig.host.event_manager.add_conversation_event.call_args.args[1]
    assert 'A5' in text and 'unfinished DSS mapping' in text
    assert rig.host.tts.say.call_args.kwargs['drop_if']() is False


@pytest.mark.parametrize('priority', ['question', 'safety'])
def test_direct_question_and_enabled_safety_response_keep_priority(rig, priority):
    extra = user() if priority == 'question' else StatusEvent(status={'event': 'LowFuelWarning'})
    rig.host.enabled_game_events = ['LowFuelWarning']
    rig.charge(extra)
    rig.host.reply_thread({})
    assert rig.host.llmModel.calls == 1
    assert rig.host.tts.say.call_args.args[0] == 'Priority response.'


@pytest.mark.parametrize('invalidate', ['cancel', 'depart', 'expire', 'system'])
def test_stale_warning_never_generates_or_queues_late_speech(rig, clock, invalidate):
    rig.charge()
    if invalidate == 'cancel':
        rig.plugin._observe_departure_status({'event': 'Status', 'flags': {}, 'flags2': {}})
    elif invalidate == 'expire':
        clock.wall += 4
    else:
        rig.plugin._consume_game_event({'event': 'StartJump', 'JumpType': 'Hyperspace'} if invalidate == 'depart'
                                      else {'event': 'FSDJump', 'StarSystem': 'Next', 'SystemAddress': 99})
    rig.host.reply_thread({})
    assert rig.host.llmModel.calls == 0
    rig.host.tts.say.assert_not_called()
    rig.host.event_manager.add_conversation_event.assert_not_called()
    assert not rig.host.reply_pending


def test_queued_warning_is_dropped_by_real_tts_if_departure_begins(rig, monkeypatch):
    rig.charge()
    actual, stream = player(monkeypatch, [b'12'])
    def say(*args, **kwargs):
        line = actual.say(*args, **kwargs)
        rig.plugin._consume_game_event({'event': 'StartJump', 'JumpType': 'Hyperspace'})
        with pytest.raises(StopPlayback):
            actual._playback_loop()
        assert line.result.outcome == 'dropped'
        return line
    rig.host.tts.say.side_effect = say
    rig.host.reply_thread({})
    assert rig.host.llmModel.calls == 0
    stream.write.assert_not_called()
    rig.host.event_manager.add_conversation_event.assert_not_called()
