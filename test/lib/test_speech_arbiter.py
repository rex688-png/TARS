"""Deterministic host replay. No providers, devices, scheduling sleeps or API calls."""
import inspect
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_speech_trace import assistant, user, player, StopPlayback, records
from lib.Event import GameEvent, PluginEvent, ToolEvent, MemoryEvent
from lib.Models import LLMModel, LLMError
from lib.SpeechArbiter import SpeechArbiter, identity_and_facts
from lib.TTS import TTSLine


@pytest.fixture
def clock():
    return SimpleNamespace(wall=1000.0, tick=0.0)


@pytest.fixture
def arbiter(clock):
    return SpeechArbiter(clock=lambda: clock.tick, wall_clock=lambda: clock.wall)


def finding(origin='explorer', kind='earth_like_world', body=7, **facts):
    name = 'TARSExplorerTarget' if origin == 'explorer' else 'TARSObservatoryFact'
    data = dict(system_address=42, body_id=body, finding_type=kind,
                _guard={'triggered_at': 1000.0}, **facts)
    return PluginEvent(plugin_event_name=name, plugin_event_content=data, responded_at=None)


def replay(mode, arbiter, events, evidence='output_written', responses=None):
    obj = assistant([], responses or ['A useful finding.'] * len(events))
    obj.config['speech_director_mode'] = mode
    obj._speech_arbiter = arbiter
    old_say = obj.tts.say.side_effect

    def say(*args, **kwargs):
        line = old_say(*args, **kwargs)
        line._playback_evidence = evidence
        return line
    obj.tts.say.side_effect = say
    for batch in events:
        obj.event_manager.get_short_term_memory.return_value = list(reversed(batch))
        obj.reply_thread({})
    return obj


@pytest.mark.parametrize('mode,expected', [('off', 2), ('observe', 2), ('enforce', 1)])
def test_duplicate_cross_source_generation_counts(mode, expected, arbiter, records):
    events = [[finding(value=1000)], [finding('observatory', value=1000)]]
    obj = replay(mode, arbiter, events)
    assert obj.llmModel.calls == expected
    # Admission never acknowledges or deletes events, even when suppressing speech.
    obj.event_manager.short_term_memory.replied_before.assert_not_called()
    assert all(e.responded_at is None for batch in events for e in batch)
    decisions = [r for r in records() if r['stage'] == 'speech_admission']
    if mode == 'off':
        assert decisions == []
    else:
        assert decisions[-1]['reason'] == 'recent_attempt'
        assert decisions[-1]['enforced'] is (mode == 'enforce')


@pytest.mark.parametrize('event', [user(), ToolEvent(request=[], results=[], responded_at=None)])
def test_direct_and_tool_responses_bypass_busy_and_duplicate_rules(arbiter, event):
    active = arbiter.reserve([finding()], {}, 'enforce')
    obj = replay('enforce', arbiter, [[event]])
    assert obj.llmModel.calls == 1
    assert arbiter._active == active.token
    arbiter.finish(active)


def test_complementary_facts_are_combined_without_changing_original_context(arbiter):
    first = finding(value=1000)
    second = finding('observatory', atmosphere='PRIVATE atmosphere')
    snapshot = json.dumps([e.plugin_event_content for e in (first, second)], sort_keys=True)
    obj = replay('enforce', arbiter, [[first, second]])
    assert obj.llmModel.calls == 1
    prompt_args = obj.prompt_generator.generate_prompt.call_args.kwargs
    assert prompt_args['events'] == [first, second]
    assert prompt_args['pending_events'] == [first, second]
    assert json.dumps([e.plugin_event_content for e in (first, second)], sort_keys=True) == snapshot


def test_late_complementary_facts_are_not_silenced(arbiter):
    obj = replay('enforce', arbiter, [[finding(value=1000)],
                                    [finding('observatory', value=1000, biology='new fact')]])
    assert obj.llmModel.calls == 2


@pytest.mark.parametrize('change', [{'body': 8}, {'kind': 'water_world'},
                                   {'kind': 'dss_complete'}, {'system_address': 99}])
def test_distinct_valuable_findings_fail_open(arbiter, change):
    base = finding()
    other = finding(body=change.get('body', 7), kind=change.get('kind', 'earth_like_world'))
    if 'system_address' in change:
        other.plugin_event_content['system_address'] = change['system_address']
    obj = replay('enforce', arbiter, [[base], [other]])
    assert obj.llmModel.calls == 2


def test_exobiology_samples_and_species_are_distinct(arbiter):
    events = [[finding(kind='organic_sample', stage=i, species='PRIVATE species')] for i in (1, 2, 3)]
    events.append([finding(kind='organic_sample', stage=3, species='different')])
    assert replay('enforce', arbiter, events).llmModel.calls == 4


def test_real_payload_aliases_and_conservative_missing_identifiers(arbiter):
    explorer = finding()
    explorer.plugin_event_content.pop('finding_type')
    explorer.plugin_event_content.update(callout_kind='scan_value', planet_class='Earthlike body')
    assert replay('enforce', arbiter, [[explorer], [finding('observatory')]]).llmModel.calls == 1
    ambiguous = finding('observatory')
    ambiguous.plugin_event_content.pop('finding_type')
    ambiguous.plugin_event_content['fact_type'] = 'notification:BioInsights'
    assert identity_and_facts(ambiguous)[0] is None
    assert replay('enforce', arbiter, [[ambiguous], [ambiguous]]).llmModel.calls == 2


def test_stale_pending_events_after_jump_remain_context_and_never_generate(arbiter, clock):
    stale = finding()
    clock.wall += 1
    arbiter.note_event(GameEvent(content={'event': 'FSDJump', 'SystemAddress': 99}, historic=False))
    obj = replay('enforce', arbiter, [[stale]])
    assert obj.llmModel.calls == 0
    obj.event_manager.short_term_memory.replied_before.assert_not_called()
    assert stale.responded_at is None
    # The same event is still available to answer a direct question.
    obj.event_manager.get_short_term_memory.return_value = [stale, user()]
    obj.reply_thread({})
    assert obj.llmModel.calls == 1


def test_new_location_epoch_and_expiry_do_not_inherit_suppression(arbiter, clock):
    first = finding()
    replay('enforce', arbiter, [[first]])
    clock.tick += 9
    assert replay('enforce', arbiter, [[finding()]]).llmModel.calls == 1
    arbiter.note_event(GameEvent(content={'event': 'FSDJump', 'SystemAddress': 42}, historic=False))
    assert replay('enforce', arbiter, [[finding()]]).llmModel.calls == 1


@pytest.mark.parametrize('outcome', ['unknown', 'failed', 'cancelled', 'dropped', 'no_audio'])
def test_non_successful_completion_does_not_cover_later_events(arbiter, outcome):
    obj = replay('enforce', arbiter, [[finding()], [finding('observatory')]], evidence=outcome)
    assert obj.llmModel.calls == 2
    assert not arbiter._recent


def test_generation_failure_and_empty_response_release_reservation(arbiter):
    obj = replay('enforce', arbiter, [[finding()], [finding('observatory')]],
                 responses=[LLMError('synthetic'), 'A finding.'])
    assert obj.llmModel.calls == 2
    assert obj.tts.say.call_count == 1
    arbiter._recent.clear()
    obj = replay('enforce', arbiter, [[finding()], [finding('observatory')]],
                 responses=['', 'A finding.'])
    assert obj.llmModel.calls == 2


def test_concurrent_reservations_have_exactly_one_admission(arbiter):
    barrier = threading.Barrier(8)

    def reserve(_):
        barrier.wait()
        return arbiter.reserve([finding()], {}, 'enforce')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))
    assert sum(r.allowed for r in results) == 1
    ticket = next(r for r in results if r.allowed)
    arbiter.finish(ticket, 'cancelled')
    assert arbiter.reserve([finding()], {}, 'enforce').allowed


def test_mode_switch_does_not_enforce_observation_history(arbiter):
    ticket = arbiter.reserve([finding()], {}, 'observe')
    arbiter.finish(ticket, 'output_written')
    assert arbiter.reserve([finding()], {}, 'enforce').allowed


def test_trace_excludes_private_payloads(arbiter, records):
    replay('enforce', arbiter, [[finding(atmosphere='PRIVATE')]])
    assert 'PRIVATE' not in json.dumps(records())
    assert not any(r.get('spoken_success') for r in records())


@pytest.mark.parametrize('mode', ['normal', 'interrupt', 'drop', 'failure', 'empty', 'synthesis_failure'])
def test_actual_tts_evidence_is_not_inferred_from_line_completion(mode, monkeypatch):
    obj, stream = player(monkeypatch, [] if mode == 'empty' else [b'12', b'34'])
    if mode == 'interrupt':
        stream.write.side_effect = lambda *a, **k: obj.abort()
    if mode == 'failure':
        stream.write.side_effect = IOError('synthetic')
    if mode == 'synthesis_failure':
        obj.tts_model.synthesize = Mock(side_effect=ValueError('synthetic'))
    line = obj.say('synthetic', drop_if=lambda: mode == 'drop')
    with pytest.raises(IOError if mode == 'failure' else StopPlayback):
        obj._playback_loop()
    expected = {'normal': 'output_written', 'interrupt': 'cancelled', 'drop': 'dropped',
                'failure': 'failed', 'empty': 'no_audio', 'synthesis_failure': 'failed'}
    assert line._playback_evidence == expected[mode]
    if mode != 'failure':
        assert line.is_completed()


def test_model_descriptors_inheritance_abstractness_and_saved_bound_methods():
    class Static(LLMModel):
        @staticmethod
        def generate(messages, tools=None):
            return messages
    class Class(LLMModel):
        @classmethod
        def generate(cls, messages, tools=None):
            return cls, messages
    class Derived(Static):
        pass
    class Abstract(LLMModel):
        pass
    assert inspect.isabstract(Abstract)
    assert Static('fake').generate(['x']) == ['x']
    assert Derived('fake').generate(['x']) == ['x']
    model = Class('fake')
    saved = model.generate
    model.generate = lambda messages, **kwargs: saved(messages, **kwargs)
    assert model.generate(['x']) == (Class, ['x'])
    assert str(inspect.signature(Static.generate)) == '(messages, tools=None)'


def test_config_uses_existing_persisted_setting(monkeypatch, tmp_path):
    from lib import Config
    monkeypatch.chdir(tmp_path)
    config = Config.load_config()
    assert config['speech_director_mode'] == 'observe'
    config = Config.update_config(config, {'speech_director_mode': 'enforce'})
    assert Config.load_config()['speech_director_mode'] == 'enforce'
    with pytest.raises(ValueError):
        Config.update_config(config, {'speech_director_mode': 'unexpected'})


def test_memory_and_context_survive_a_suppressed_turn_and_a_later_question(arbiter):
    first = finding()
    replay('enforce', arbiter, [[first]])
    duplicate = finding('observatory')
    memory = MemoryEvent(content='PRIVATE memory', metadata={}, embedding=[], responded_at=None)
    obj = replay('enforce', arbiter, [[duplicate, memory], [duplicate, memory, user()]])
    assert obj.llmModel.calls == 1
    assert memory in obj.prompt_generator.generate_prompt.call_args.kwargs['events']
    assert duplicate in obj.prompt_generator.generate_prompt.call_args.kwargs['events']
    assert memory.responded_at is None


def test_direct_activity_invalidates_inflight_attempt_without_acknowledging_it(arbiter):
    ticket = arbiter.reserve([finding()], {}, 'enforce')
    arbiter.note_event(user())
    arbiter.finish(ticket, 'output_written')
    assert not arbiter._recent


def test_priority_orders_one_batch_without_losing_optional_context(arbiter):
    chatter = PluginEvent(plugin_event_name='TARSChatter', plugin_event_content={'candidate': 'PRIVATE'},
                          timestamp='1970-01-01T00:16:40+00:00', responded_at=None)
    admission = arbiter.reserve([chatter, finding()], {}, 'enforce')
    assert [d.source for _, d in admission.decisions] == ['explorer', 'chatter']
    assert admission.decisions[1][1].optional
    assert all(d.accepted for _, d in admission.decisions)
    arbiter.finish(admission)
    obj = replay('enforce', arbiter, [[chatter, finding()]])
    assert obj.llmModel.calls == 1
    assert chatter in obj.prompt_generator.generate_prompt.call_args.kwargs['events']


def test_short_generation_window_is_not_a_permanent_announcement(arbiter, clock):
    obj = replay('enforce', arbiter, [[finding()], [finding('observatory')]])
    assert obj.llmModel.calls == 1
    clock.tick += 8.01
    assert replay('enforce', arbiter, [[finding('observatory')]]).llmModel.calls == 1


def test_unknown_payload_shapes_fail_open_and_cannot_block_direct_questions(arbiter):
    event = finding(finding_type_override=object())
    assert identity_and_facts(event)[0] is None
    event.plugin_event_content['finding_type'] = ['unexpected']
    assert identity_and_facts(event)[0] is None
    obj = replay('enforce', arbiter, [[event, user()]])
    assert obj.llmModel.calls == 1


def test_stop_speaking_after_write_completion_invalidates_attempt_lease(arbiter):
    arbiter.note_cancellation(0)
    ticket = arbiter.reserve([finding()], {}, 'enforce')
    arbiter.finish(ticket, 'output_written')
    assert arbiter._recent
    arbiter.note_cancellation(1)
    assert not arbiter._recent
    assert arbiter.reserve([finding('observatory')], {}, 'enforce').allowed


def test_off_transition_clears_prior_enforcement_state(arbiter):
    replay('enforce', arbiter, [[finding()]])
    assert arbiter._recent
    obj = replay('off', arbiter, [[finding('observatory')]])
    assert obj.llmModel.calls == 1
    assert not arbiter._recent


def test_native_gameplay_freshness_uses_journal_timestamp(arbiter):
    event = GameEvent(content={'event': 'UnderAttack', 'timestamp': '1970-01-01T00:00:01Z'}, historic=False)
    admission = arbiter.reserve([event], {}, 'enforce')
    assert not admission.allowed
    assert admission.decisions[0][1].source == 'native'
    assert admission.decisions[0][1].reason == 'stale'


def test_competing_unique_host_turn_is_deferred_and_can_be_retried(arbiter):
    owner = arbiter.reserve([finding()], {}, 'enforce')
    other = finding(body=8, value=2000)
    obj = replay('enforce', arbiter, [[other]])
    assert obj.llmModel.calls == 0 and obj.reply_pending
    obj.event_manager.short_term_memory.replied_before.assert_not_called()
    arbiter.finish(owner, 'output_written')
    obj.reply_thread({})
    assert obj.llmModel.calls == 1


def test_observe_keeps_identical_prompt_tts_and_turn_bookkeeping(clock):
    batches = [[finding(value=1000)], [finding('observatory', value=1000)]]
    off = replay('off', SpeechArbiter(clock=lambda: clock.tick, wall_clock=lambda: clock.wall), batches)
    observe = replay('observe', SpeechArbiter(clock=lambda: clock.tick, wall_clock=lambda: clock.wall), batches)
    assert off.prompt_generator.generate_prompt.call_args_list == observe.prompt_generator.generate_prompt.call_args_list
    assert off.tts.say.call_args_list == observe.tts.say.call_args_list
    assert off.event_manager.add_conversation_event.call_args_list == observe.event_manager.add_conversation_event.call_args_list
    assert off.event_manager.add_assistant_complete_event.call_count == observe.event_manager.add_assistant_complete_event.call_count == 2


def test_unknown_identifier_placeholders_cannot_deduplicate_distinct_discoveries(arbiter):
    unknown = finding()
    unknown.plugin_event_content.update(system_address=0, body_id=-1, body='Unknown body')
    assert identity_and_facts(unknown)[0] is None
    assert replay('enforce', arbiter, [[unknown], [unknown]]).llmModel.calls == 2


def test_advisory_chatter_interface_respects_mode_without_generation(arbiter):
    from lib.PluginHelper import PluginHelper
    ticket = arbiter.reserve([finding()], {}, 'enforce')
    obj = assistant([], [])
    obj._speech_arbiter = arbiter
    helper = PluginHelper.__new__(PluginHelper)
    helper._assistant = obj
    helper._event_manager = Mock()
    helper._event_manager.get_current_state.return_value = ([], {})
    helper._config = obj.config
    for mode, expected in [('off', True), ('observe', True), ('enforce', False)]:
        obj.config['speech_director_mode'] = mode
        assert helper.preview_optional_speech() is expected
    assert obj.llmModel.calls == 0
    arbiter.finish(ticket)
