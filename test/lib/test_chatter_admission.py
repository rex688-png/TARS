"""Host polling regressions and real Chatter paths with deterministic providers."""
import json
import queue
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_speech_arbiter import arbiter, clock, finding, replay
from test_speech_trace import assistant, chatter, records, user
from lib.Event import ConversationEvent
from lib.EventManager import EventManager
from lib.Logger import PromptUsageStats
from lib.PluginHelper import PluginHelper


def prepare_host(obj):
    obj.disabled_game_events = []
    obj._process_active_quests = lambda *args: None


@pytest.mark.parametrize('name', ['TARSExplorerTarget', 'TARSNavigatorTarget'])
def test_busy_retry_survives_assistant_completion_and_needs_no_game_event(arbiter, name):
    owner = arbiter.reserve([finding()], {}, 'enforce')
    event = finding(body=8)
    event.plugin_event_name = name
    obj = replay('enforce', arbiter, [[event]])
    prepare_host(obj)
    assert obj.reply_pending and obj.llmModel.calls == 0
    obj.on_event(ConversationEvent(kind='assistant_completed', content=''), {})
    assert obj.reply_pending  # The ordinary host poll must still see the retry.
    arbiter.finish(owner)
    if obj.reply_pending and not obj.is_replying:
        obj.reply_thread({})
    assert obj.llmModel.calls == 1 and not obj.reply_pending


def test_busy_retry_expires_without_indefinite_pending(arbiter, clock):
    owner = arbiter.reserve([finding()], {}, 'enforce')
    obj = replay('enforce', arbiter, [[finding(body=8)]])
    clock.wall += 61
    arbiter.finish(owner)
    if obj.reply_pending:
        obj.reply_thread({})
    assert obj.llmModel.calls == 0 and not obj.reply_pending


def test_concurrent_host_retry_does_not_clear_running_flag_or_generate_twice(arbiter):
    event = finding()
    obj = assistant([event], ['Useful finding.'])
    obj.config['speech_director_mode'] = 'enforce'
    obj._speech_arbiter = arbiter
    entered, release = threading.Event(), threading.Event()
    original = obj.llmModel.generate

    def generate(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    obj.llmModel.generate = generate
    worker = threading.Thread(target=obj.reply_thread, args=({},))
    worker.start()
    try:
        assert entered.wait(3)
        obj.reply_thread({})
        assert obj.is_replying
    finally:
        release.set()
        worker.join(3)
    # The store would mark this event responded when the first turn commits.
    event.responded_at = 1.0
    if obj.reply_pending:
        obj.reply_thread({})
    assert obj.llmModel.calls == 1 and not obj.reply_pending

LINE = 'The landing gear has had a busier afternoon than we have.'
MODES = ['off', 'observe', 'enforce']


@pytest.fixture
def integration(monkeypatch, arbiter, clock):
    def make(mode='enforce', responses=None, callback=None):
        host = assistant([], responses or [LINE] * 8)
        prepare_host(host)
        host.reply_pending = False
        host.tts._abort_revision = 0
        host._speech_arbiter = arbiter
        host.config['speech_director_mode'] = mode
        host.event_manager.incoming = queue.Queue()
        helper = PluginHelper.__new__(PluginHelper)
        helper._assistant = host
        helper._config = host.config
        helper._event_manager = host.event_manager
        helper._prompt_generator = host.prompt_generator
        helper._llm_model = host.llmModel
        plugin = chatter()
        plugin.settings = dict(silence_chance=0, event_opportunities=True)
        plugin._helper = helper
        plugin._running = True
        plugin._schedule_next = Mock()
        plugin._visual_observation = lambda now: None
        plugin._event_opportunity_chance = lambda *args: 1.0
        plugin._recent_situational_anchors = lambda *args: [{'event': 'Touchdown'}]
        plugin._choose_chatter_topics = lambda *a, **k: ['ship', 'navigation', 'copilot']
        # Repeatable independent opportunities; real quality/repetition checks remain.
        plugin._chatter_premises = lambda line: []
        base = plugin._fire.__func__.__globals__
        monkeypatch.setitem(base, 'time', SimpleNamespace(time=lambda: clock.wall))
        monkeypatch.setattr(base['random'], 'random', lambda: 0.0)
        monkeypatch.setattr(base['random'], 'uniform', lambda a, b: b)
        monkeypatch.setitem(plugin._should_reply_to_chatter.__func__.__globals__, 'time', SimpleNamespace(time=lambda: clock.wall))
        generate = host.llmModel.generate
        if callback:
            def generate_with_callback(*args, **kwargs):
                callback(host, plugin, host.llmModel.calls)
                return generate(*args, **kwargs)
            host.llmModel.generate = generate_with_callback
        # Real Session + base output wrappers. Candidates use the saved original.
        plugin._install_output_director()
        helper.register_event('TARSChatter', plugin._should_reply_to_chatter, plugin._chatter_prompt)
        return SimpleNamespace(host=host, plugin=plugin, helper=helper,
                               fire=lambda path='timer': plugin._fire() if path == 'timer' else
                               plugin._fire_event_opportunity('FSDJump', clock.wall, plugin._session_id))
    return make


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('path', ['timer', 'gameplay'])
@pytest.mark.parametrize('scenario,calls,events', [('normal', 1, 1), ('quality', 3, 1), ('skip', 1, 0), ('failure', 1, 0)])
def test_real_opportunities_preserve_creativity_and_silence(integration, arbiter, records, mode, path, scenario, calls, events):
    responses = {'normal': [LINE], 'quality': ['short', 'short', LINE],
                 'skip': ['SKIP'], 'failure': [RuntimeError('PRIVATE failure')]}[scenario]
    run = integration(mode, responses)
    run.fire(path)
    assert run.host.llmModel.calls == calls
    assert run.host.event_manager.incoming.qsize() == events
    if not events or mode != 'enforce':
        assert not arbiter._optional
    else:
        event = run.host.event_manager.incoming.get_nowait()
        assert run.helper.optional_speech_event_valid(event)
        assert '_speech_admission' in event.plugin_event_content
    assert 'PRIVATE' not in json.dumps(records())


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('path', ['timer', 'gameplay'])
@pytest.mark.parametrize('priority', ['busy', 'explorer', 'navigator'])
def test_rejection_precedes_generation(integration, arbiter, mode, path, priority):
    run = integration(mode)
    if priority == 'busy':
        active = arbiter.reserve([finding()], {}, mode)
    else:
        event = finding()
        if priority == 'navigator':
            event.plugin_event_name = 'TARSNavigatorTarget'
        # Actual incoming queue, before EventManager has notified side effects.
        run.host.event_manager.incoming.put(event)
    run.fire(path)
    assert run.host.llmModel.calls == (0 if mode == 'enforce' else 1)
    if priority == 'busy':
        arbiter.finish(active)
    assert not arbiter._optional


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('path', ['timer', 'gameplay'])
def test_user_arriving_during_first_rejected_candidate_stops_wasted_retries(integration, arbiter, mode, path):
    def arrive(host, plugin, count):
        if count == 0:
            host.event_manager.incoming.put(user())
    run = integration(mode, ['short', 'short', LINE], arrive)
    run.fire(path)
    assert run.host.llmModel.calls == (1 if mode == 'enforce' else 3)
    assert not arbiter._optional
    # The direct question cannot be blocked by an optional reservation.
    question = run.host.event_manager.incoming.get_nowait()
    arbiter.note_event(question)
    admission = arbiter.reserve([question], {}, mode)
    assert admission.allowed
    arbiter.finish(admission)
    if mode == 'enforce':
        assert run.host.event_manager.incoming.empty()


@pytest.mark.parametrize('mode', MODES)
def test_slow_generation_rechecks_freshness(integration, arbiter, clock, mode):
    def slow(*args):
        clock.tick += 61
        clock.wall += 61
    run = integration(mode, callback=slow)
    run.fire()
    assert run.host.llmModel.calls == 1
    assert run.host.event_manager.incoming.qsize() == (0 if mode == 'enforce' else 1)
    assert not arbiter._optional


@pytest.mark.parametrize('mode', MODES)
def test_simultaneous_opportunities_have_one_enforced_owner(integration, arbiter, mode):
    entered, release = threading.Event(), threading.Event()
    def block(host, plugin, count):
        if threading.current_thread().name == 'first-candidate':
            entered.set()
            assert release.wait(3)
    run = integration(mode, callback=block)
    worker = threading.Thread(target=run.fire, name='first-candidate')
    worker.start()
    try:
        assert entered.wait(3)
        run.fire('gameplay')
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    expected = 1 if mode == 'enforce' else 2
    assert run.host.llmModel.calls == expected
    assert run.host.event_manager.incoming.qsize() == expected
    run.helper.cancel_optional_speech()
    assert not arbiter._optional


@pytest.mark.parametrize('mode', MODES)
def test_real_host_handoff_uses_prepared_line_without_another_model_request(integration, arbiter, clock, monkeypatch, mode):
    run = integration(mode)
    # Real wrapper recognizes a main-host request; retain its prepared-line parser.
    monkeypatch.setattr(run.plugin, '_main_covas_system_index', lambda messages: 0)
    run.fire()
    event = run.host.event_manager.incoming.get_nowait()
    event.timestamp = datetime.fromtimestamp(clock.wall, timezone.utc).isoformat()
    event.responded_at = None  # EventManager marks newly processed events unanswered.
    manager = EventManager.__new__(EventManager)
    manager.incoming = run.host.event_manager.incoming
    manager._processing_lock = threading.Lock()
    manager.short_term_memory = Mock()
    manager.projections, manager.pending, manager.processed = [], [], []
    manager.update_projections = Mock(return_value=[])
    manager.save_projections = Mock()
    manager.sideeffects = [run.host.on_event]
    manager.incoming.put(event)
    manager.process()
    manager.short_term_memory.insert_event.assert_called_once()
    assert run.host.reply_pending
    prompt = '[External Event]\n' + run.plugin._chatter_prompt(event)
    run.host.prompt_generator.generate_prompt.return_value = (
        [{'role': 'system', 'content': 'You are TARS.'}, {'role': 'user', 'content': prompt}], PromptUsageStats())
    run.host.event_manager.get_short_term_memory.return_value = [event]
    run.host.reply_thread({})
    assert run.host.llmModel.calls == 1
    run.host.tts.say.assert_called_once()
    assert not arbiter._optional and arbiter._active is None


@pytest.mark.parametrize('change', ['question', 'mode', 'abort', 'restart'])
def test_cancelled_dispatched_candidate_cannot_hijack_following_reply(integration, arbiter, change):
    run = integration()
    run.fire()
    event = run.host.event_manager.incoming.get_nowait()
    if change == 'question':
        run.host.on_event(user(), {})
    elif change == 'mode':
        arbiter.configure('off')
        arbiter.configure('enforce')
    elif change == 'abort':
        arbiter.note_cancellation(1)
    else:
        run.host.reset_runtime_state()
    assert not run.plugin._should_reply_to_chatter(event)
    assert run.plugin._chatter_prompt(event) == ''
    assert not arbiter._optional


@pytest.mark.parametrize('change', ['stop', 'mode', 'abort'])
def test_inflight_cancellation_stops_creative_retries_and_releases(integration, arbiter, change):
    def cancel(host, plugin, count):
        if change == 'stop':
            plugin.on_chat_stop(plugin._helper)
        elif change == 'mode':
            host.config['speech_director_mode'] = 'off'
        else:
            host.tts._abort_revision += 1
    run = integration(responses=['short', 'short', LINE], callback=cancel)
    run.fire()
    assert run.host.llmModel.calls == 1
    assert run.host.event_manager.incoming.empty()
    assert not arbiter._optional


def test_dispatch_exception_and_atomic_rejection_reschedule_and_release(integration, arbiter):
    run = integration()
    run.helper.dispatch_event = Mock(side_effect=RuntimeError('PRIVATE dispatch'))
    run.fire()
    assert not arbiter._optional
    run.plugin._schedule_next.assert_called_with(30.0)
    run.helper.dispatch_event = Mock()
    # Priority arrives after the last candidate validity check, inside quality screening.
    run.plugin._chatter_quality_reason = lambda line: run.host.event_manager.incoming.put(user())
    run.fire()
    run.helper.dispatch_event.assert_not_called()
    run.plugin._schedule_next.assert_called_with(10.0)
    assert not arbiter._optional


def test_busy_important_event_survives_noisy_history_and_retries_once(arbiter):
    active = arbiter.reserve([finding()], {}, 'enforce')
    event = finding(body=9)
    obj = replay('enforce', arbiter, [[event]])
    for _ in range(3):
        obj.reply_thread({})
    assert obj.reply_pending and obj.llmModel.calls == 0
    # The event has fallen outside the ordinary 150-event window.
    obj.event_manager.get_short_term_memory.return_value = [
        ConversationEvent(kind='assistant_completed', content='', responded_at=1) for _ in range(150)]
    arbiter.finish(active)
    obj.reply_thread({})
    assert obj.llmModel.calls == 1 and not obj.reply_pending
    assert obj.prompt_generator.generate_prompt.call_args.kwargs['pending_events'] == [event]


@pytest.mark.parametrize('mode', MODES)
def test_chance_silence_does_not_reserve_or_generate(integration, arbiter, mode):
    run = integration(mode)
    run.plugin.settings['silence_chance'] = 101
    run.fire()
    run.fire('gameplay')
    assert run.host.llmModel.calls == 0 and not arbiter._optional


@pytest.mark.parametrize('mode', MODES)
def test_stale_gameplay_opportunity_rejected_before_generation(integration, arbiter, clock, mode):
    run = integration(mode)
    run.plugin._fire_event_opportunity('FSDJump', clock.wall - 61, run.plugin._session_id)
    assert run.host.llmModel.calls == (0 if mode == 'enforce' else 1)
    run.helper.cancel_optional_speech()
    assert not arbiter._optional


def test_off_to_enforce_during_generation_invalidates_old_capability(integration, arbiter):
    def change(host, plugin, count):
        host.config['speech_director_mode'] = 'enforce'
    run = integration('off', ['short', 'short', LINE], change)
    run.fire()
    assert run.host.llmModel.calls == 1
    assert run.host.event_manager.incoming.empty() and not arbiter._optional


def test_prior_cancellation_does_not_poison_fresh_reservation(integration, arbiter):
    arbiter.note_cancellation(0)
    run = integration()
    run.host.tts._abort_revision = 1
    run.fire()
    assert run.host.llmModel.calls == 1
    assert run.host.event_manager.incoming.qsize() == 1


def test_legacy_host_keeps_same_candidate_generation(integration):
    run = integration()
    # Real plugin fallback for a host without the new capability methods.
    run.plugin._helper = SimpleNamespace(_llm_model=run.host.llmModel,
                                        dispatch_event=Mock(), _assistant=run.host)
    run.fire()
    assert run.host.llmModel.calls == 1
    run.plugin._helper.dispatch_event.assert_called_once()


def test_plugin_predicate_rejection_releases_queued_capability(integration, arbiter, clock):
    run = integration()
    run.fire()
    event = run.host.event_manager.incoming.get_nowait()
    run.plugin._last_assistant_time = clock.wall + 1
    run.host.on_event(event, {})
    assert not run.host.reply_pending and not arbiter._optional
    assert run.plugin._chatter_prompt(event) == ''


def test_direct_question_can_generate_while_optional_candidate_is_inflight(integration, arbiter):
    entered, release = threading.Event(), threading.Event()
    def block(host, plugin, count):
        if threading.current_thread().name == 'optional-candidate':
            entered.set()
            assert release.wait(3)
    run = integration(responses=['Your answer, Commander.', 'short', LINE], callback=block)
    worker = threading.Thread(target=run.fire, name='optional-candidate')
    worker.start()
    try:
        assert entered.wait(3)
        question = user()
        run.host.on_event(question, {})
        run.host.event_manager.get_short_term_memory.return_value = [question]
        run.host.reply_thread({})
        run.host.tts.say.assert_called_once()
        assert run.host.llmModel.calls == 1
    finally:
        release.set()
        worker.join(3)
    assert run.host.llmModel.calls == 2  # One direct answer and the already in-flight optional call.
    assert run.host.event_manager.incoming.empty() and not arbiter._optional
