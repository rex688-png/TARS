"""Real host paths with deterministic models, queues and audio writes; no API calls."""
import importlib.util
import json
import queue
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from lib import SpeechTrace as trace
from lib.Assistant import Assistant
from lib.Event import ConversationEvent, PluginEvent
from lib.EventManager import EventManager
from lib.Logger import ModelUsageStats, PromptUsageStats
from lib.Models import LLMError, LLMModel
from lib.PluginHelper import PluginHelper
from lib.TTS import TTS, TTSLine
import lib.TTS as tts_module


@pytest.fixture
def records(monkeypatch, caplog):
    monkeypatch.setattr(trace, 'enabled', True)
    caplog.set_level('INFO', logger='tars.speech')
    return lambda: [r.speech_trace for r in caplog.records if hasattr(r, 'speech_trace')]


class FakeLLM(LLMModel):
    def __init__(self, responses):
        super().__init__('fake')
        self.responses = iter(responses)
        self.calls = 0

    def generate(self, messages, tools=None, tool_choice=None):
        self.calls += 1
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value, None, ModelUsageStats()


def assistant(events, responses):
    obj = Assistant.__new__(Assistant)
    obj.config = dict(characters=[{}], active_character_index=0, tools_var=False,
                      game_actions_var=False, web_search_actions_var=False,
                      ui_actions_var=False, use_action_cache_var=False)
    obj.event_manager = Mock()
    obj.event_manager.get_short_term_memory.return_value = list(reversed(events))
    obj.event_manager.get_latest_memories.return_value = []
    obj.llmModel = FakeLLM(responses)
    obj.prompt_generator = Mock()
    obj.prompt_generator.generate_prompt.return_value = ([], PromptUsageStats())
    obj._get_tts_postprocessing_layers = lambda states: []
    obj.pending = list(events)
    obj.enabled_game_events = []
    obj.registered_should_reply_handlers = []
    obj.is_replying = False
    obj.tts = Mock()

    def say(*args, **kwargs):
        line = TTSLine()
        line.mark_speaking()
        line.mark_completed()
        return line
    obj.tts.say.side_effect = say
    return obj


def user():
    return ConversationEvent(kind='user', content='PRIVATE user question', responded_at=None)


def test_direct_question_selection_and_reply_do_not_change(records):
    obj = assistant([user()], ['PRIVATE answer'])
    assert obj.should_reply({}) is True
    obj.reply_thread({})
    assert obj.llmModel.calls == 1
    obj.tts.say.assert_called_once()
    obj.event_manager.add_assistant_complete_event.assert_called_once()
    stages = [r['stage'] for r in records()]
    assert 'reply_selected' in stages and 'generation_returned' in stages
    assert 'line_completed' in stages
    assert all(r.get('playback_success') != 'success' for r in records())
    assert 'PRIVATE' not in json.dumps(records())


@pytest.mark.parametrize('response,stage', [('', 'response_discarded'),
                                         (LLMError('PRIVATE failure'), 'generation_failed')])
def test_empty_and_failed_generation_never_queue_speech(records, response, stage):
    obj = assistant([user()], [response])
    obj.reply_thread({})
    obj.tts.say.assert_not_called()
    assert stage in [r['stage'] for r in records()]
    assert not obj.is_replying
    assert 'PRIVATE' not in json.dumps(records())


def test_unidentified_sources_fail_open_without_commander_location_guessing(records, monkeypatch):
    monkeypatch.setattr('lib.ResponsePresentation.monotonic', lambda: 100.0)
    obj = assistant([], ['A unique finding.', 'A unique finding.'])
    state = {'Location': {'StarSystem': 'PRIVATE system', 'Body': 'PRIVATE body'}}
    for name in ('TARSExplorerTarget', 'TARSObservatoryFact'):
        event = PluginEvent(plugin_event_name=name, plugin_event_content={'private': 'PRIVATE'}, responded_at=None)
        obj.event_manager.get_short_term_memory.return_value = [event]
        obj.reply_thread(state)
    assert obj.llmModel.calls == 2
    assert obj.tts.say.call_count == 2  # Text alone cannot prove the same source body/fact.
    assert not any(r.get('reason') == 'exploration_deduplication' for r in records())
    assert {r.get('trigger') for r in records()} >= {'TARSExplorerTarget', 'TARSObservatoryFact'}
    assert 'PRIVATE' not in json.dumps(records())


class StopPlayback(BaseException):
    pass


def player(monkeypatch, chunks):
    obj = TTS.__new__(TTS)
    obj.read_queue = queue.Queue()
    obj.is_aborted = False
    obj._is_playing = False
    obj.prebuffer_size = 4
    obj.sample_size = 2
    obj.frames_per_buffer = 1024
    obj.output_format = 8
    obj.output_volume_multiplier = 1.0
    obj.voice = 'fake'
    obj.tts_model = SimpleNamespace(synthesize=lambda *args: iter(chunks))
    obj._get_effective_postprocessing_config = lambda *args: None
    obj._get_output_device_index = lambda: None
    stream = Mock()
    stream.get_write_available.return_value = 0
    obj.p = Mock()
    obj.p.open.return_value = stream
    monkeypatch.setattr(tts_module, 'sleep', lambda _: (_ for _ in ()).throw(StopPlayback()))
    return obj, stream


@pytest.mark.parametrize('mode', ['normal', 'interrupt', 'drop', 'failure', 'empty', 'synthesis_failure'])
def test_real_playback_outcomes_and_legacy_completion(records, monkeypatch, mode):
    obj, stream = player(monkeypatch, [] if mode == 'empty' else [b'12', b'34', b'56'])
    if mode == 'interrupt':
        stream.write.side_effect = lambda *a, **k: obj.abort()
    if mode == 'failure':
        stream.write.side_effect = IOError('PRIVATE device failure')
    if mode == 'synthesis_failure':
        obj.tts_model.synthesize = Mock(side_effect=ValueError('PRIVATE synthesis failure'))
    token = trace.current.set('test-turn')
    try:
        line = obj.say('PRIVATE answer', drop_if=lambda: mode == 'drop')
    finally:
        trace.current.reset(token)
    with pytest.raises(IOError if mode == 'failure' else StopPlayback):
        obj._playback_loop()
    observations = records()
    stages = [r['stage'] for r in observations]
    assert 'tts_queued' in stages
    if mode == 'normal':
        assert stream.write.call_count == 3
        assert stages.count('playback_started') == 1
    elif mode == 'interrupt':
        assert stream.write.call_count == 1
        assert any(r.get('outcome') == 'cancelled' for r in observations)
    elif mode == 'failure':
        assert not line.is_completed() and obj.read_queue.qsize() == 1
        assert 'playback_failed' in stages and 'playback_started' not in stages
    elif mode == 'drop':
        assert line.is_completed() and not line.wait_for_speaking()
        assert 'playback_discarded' in stages and 'playback_started' not in stages
    else:
        assert line.is_completed() and 'playback_started' not in stages
        if mode == 'synthesis_failure':
            assert 'synthesis_failed' in stages
    assert all(r.get('playback_success') != 'success' for r in observations)
    assert all(r['trace_id'] == 'test-turn' for r in observations if r['stage'] != 'playback_abort_requested')
    assert 'PRIVATE' not in json.dumps(observations)


def test_abort_queued_line_is_completion_without_playback(records):
    obj = TTS.__new__(TTS)
    obj.read_queue = queue.Queue()
    line = obj.say('PRIVATE queued speech')
    obj.abort()
    assert line.is_completed() and not line.wait_for_speaking()
    assert 'playback_cancelled' in [r['stage'] for r in records()]
    assert 'playback_started' not in [r['stage'] for r in records()]


def test_disabled_tracing_and_broken_sink_do_not_affect_model(monkeypatch, records):
    monkeypatch.setattr(trace, 'enabled', False)
    model = FakeLLM(['same', 'same'])
    assert model.generate([])[0] == 'same'
    assert records() == []
    monkeypatch.setattr(trace, 'enabled', True)
    monkeypatch.setattr(trace._logger, 'info', Mock(side_effect=RuntimeError('broken sink')))
    assert model.generate([])[0] == 'same'
    assert model.calls == 2


def chatter():
    path = Path(__file__).resolve().parents[2] / 'vendor/tars-plugins/plugins/TARSChatter/TARSChatterSession.py'
    spec = importlib.util.spec_from_file_location('_speech_trace_real_chatter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TARSChatter(None)


def test_real_chatter_generates_three_candidates_before_one_dispatch(records, monkeypatch):
    plugin = chatter()
    model = FakeLLM(['short', 'short', 'The landing gear has had a busier afternoon than we have.'])
    plugin._llm_model = model
    plugin._original_generate = model.generate
    monkeypatch.setattr(plugin, '_recent_situational_anchors', lambda *args: [{'event': 'Touchdown'}])
    monkeypatch.setattr(plugin, '_choose_chatter_topics', lambda *a, **k: ['ship', 'navigation', 'copilot'])
    # Real candidate screening, loop and model calls; no wall-clock scheduling.
    candidate = plugin._prepare_chatter_line()
    assert candidate and model.calls == 3
    helper = PluginHelper.__new__(PluginHelper)
    helper._event_manager = SimpleNamespace(incoming=queue.Queue())
    helper.dispatch_event(PluginEvent(plugin_event_name='TARSChatter', plugin_event_content={'candidate': candidate}))
    observations = records()
    assert sum(r['stage'] == 'generation_started' and r['path'] == 'chatter_candidate' for r in observations) == 3
    assert sum(r['stage'] == 'plugin_dispatched' for r in observations) == 1
    assert helper._event_manager.incoming.qsize() == 1
    assert candidate not in json.dumps(observations)


def test_real_chatter_output_guard_regenerates_without_new_host_requests(records, monkeypatch):
    plugin = chatter()
    model = FakeLLM(['PRIVATE rejected draft', 'PRIVATE accepted draft'])
    plugin._helper = SimpleNamespace(_llm_model=model)
    monkeypatch.setattr(plugin, '_main_covas_system_index', lambda messages: 0)
    monkeypatch.setattr(plugin, '_explicit_visual_request', lambda messages: None)
    monkeypatch.setattr(plugin, '_prepared_chatter_line', lambda messages: None)
    monkeypatch.setattr(plugin, '_routine_noise_kind', lambda messages: None)
    monkeypatch.setattr(plugin, '_is_spontaneous_turn', lambda messages: True)
    monkeypatch.setattr(plugin, '_routine_flight_trigger', lambda messages: None)
    monkeypatch.setattr(plugin, '_inject_director', lambda messages, index: messages)
    monkeypatch.setattr(plugin, '_chatter_quality_reason', lambda text: 'test_reason' if 'rejected' in text else None)
    monkeypatch.setattr(plugin, '_repetition_reason', lambda text: None)
    plugin._install_output_director()
    token = trace.current.set('direct-turn')
    try:
        result = model.generate([{'role': 'system', 'content': 'PRIVATE'}, {'role': 'user', 'content': 'PRIVATE'}])
    finally:
        trace.current.reset(token)
        plugin._restore_output_director()
    assert result[0] == 'PRIVATE accepted draft' and model.calls == 2
    observations = records()
    assert sum(r['stage'] == 'generation_started' and r['path'] == 'chatter_guard' for r in observations) == 2
    assert any(r.get('reason') == 'output_guard' for r in observations)
    assert 'PRIVATE' not in json.dumps(observations)


def test_known_chatter_silence_logs_become_fixed_codes(records):
    from lib.Logger import log
    log('info', 'TARS Chatter discarded a weak candidate (PRIVATE detail).')
    log('info', 'TARS Chatter accepted model-selected silence.')
    assert [r['reason'] for r in records()] == ['quality_check', 'model_skip']
    assert 'PRIVATE' not in json.dumps(records())


def test_dispatch_processing_and_reload_share_identity_without_suppressing_duplicates(records):
    manager = EventManager.__new__(EventManager)
    manager.incoming = queue.Queue()
    manager._processing_lock = threading.Lock()
    manager.short_term_memory = Mock()
    manager.projections = []
    manager.pending = []
    manager.processed = []
    manager.update_projections = Mock(return_value=[])
    manager.save_projections = Mock()
    manager.trigger_sideeffects = Mock()
    helper = PluginHelper.__new__(PluginHelper)
    helper._event_manager = manager
    events = [PluginEvent(plugin_event_name='TARSNavigatorTarget',
                          timestamp=f'2026-10-21T12:00:0{i}+00:00',
                          plugin_event_content={'private': 'PRIVATE'}) for i in range(2)]
    for event in events:
        helper.dispatch_event(event)
    manager.process()
    assert manager.trigger_sideeffects.call_count == 2
    assert manager.processed == events
    dispatched = [r['event_id'] for r in records() if r['stage'] == 'plugin_dispatched']
    received = [r['event_id'] for r in records() if r['stage'] == 'event_received']
    assert received == dispatched and len(set(received)) == 2
    restored = PluginEvent(plugin_event_name=events[0].plugin_event_name,
                           timestamp=events[0].timestamp, plugin_event_content={})
    assert trace.event_fields(restored)['event_id'] == received[0]
    assert 'PRIVATE' not in json.dumps(records())


def test_model_selected_chatter_silence_has_one_attempt_and_no_dispatch(records, monkeypatch):
    plugin = chatter()
    model = FakeLLM(['SKIP'])
    plugin._llm_model = model
    plugin._original_generate = model.generate
    monkeypatch.setattr(plugin, '_recent_situational_anchors', lambda *args: [{'event': 'Touchdown'}])
    monkeypatch.setattr(plugin, '_choose_chatter_topics', lambda *a, **k: ['ship', 'navigation', 'copilot'])
    assert plugin._prepare_chatter_line() is None
    assert model.calls == 1
    assert any(r.get('reason') == 'model_skip' for r in records())
    assert 'plugin_dispatched' not in [r['stage'] for r in records()]


def test_plugin_reply_checks_preserve_rejection_and_pending_set_selection(records):
    obj = assistant([], [])
    obj.disabled_game_events = []
    obj._process_active_quests = lambda *args: None
    helper = PluginHelper.__new__(PluginHelper)
    helper._assistant = obj
    helper._prompt_generator = Mock()
    helper.register_event('TARSNavigatorTarget',
                          lambda event: event.plugin_event_content['eligible'],
                          lambda event: 'unused')
    for eligible in (False, True):
        obj.on_event(PluginEvent(plugin_event_name='TARSNavigatorTarget',
                                 plugin_event_content={'eligible': eligible}), {})
        assert obj.reply_pending is eligible
    assert [r['selected'] for r in records() if r['stage'] == 'plugin_reply_check'] == [False, False, True]
    assert obj.llmModel.calls == 0
