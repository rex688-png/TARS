"""Confirmed corrective gaps: no network, profiles, game or real audio."""
import json
from unittest.mock import Mock

import pytest
from test_gameplay_speech_quality import pipeline, fact
from test_speech_arbiter import arbiter, clock
from test_chatter_admission import integration
from test_explorer_departure import rig
from test_speech_trace import assistant, user, records, player, StopPlayback
from lib.Event import PluginEvent
from lib.ExplorationSpeech import DeliveryLedger
from lib.ResponsePresentation import is_silence_sentinel
from lib import SpeechTrace as trace

SILENCE = ['Silence.', 'No response.', 'SKIP', '"No reply."', '`No output`',
           'Remain silent.', 'Stay silent!', '“silence”', 'No response is needed.',
           '[Silence.]', '(No reply required.)', 'Do not respond.']


@pytest.mark.parametrize('mode', ['off', 'observe', 'enforce'])
@pytest.mark.parametrize('text', SILENCE)
def test_abstention_has_no_delivery_or_persistence(pipeline, mode, text, records):
    host, run = pipeline(mode)
    host.llmModel.responses = iter([text])
    run(fact())
    assert host.llmModel.calls == 1
    host.tts.say.assert_not_called()
    host.event_manager.add_conversation_event.assert_not_called()
    host.event_manager.add_assistant_speaking.assert_not_called()
    host.event_manager.add_assistant_complete_event.assert_called_once()
    assert not host.speech_arbiter()._delivery_ledger.delivered
    assert any(r.get('reason') == 'silence_sentinel' for r in records())


@pytest.mark.parametrize('text', [
    'Silence is useful when scanning for a signal.',
    'No response means the server has not answered yet.',
    'SKIP is the requested keyword.',
    'Stay silent until the next jump, then report the route.',
    'The phrase "No response." describes an abstention.',
])
def test_user_requested_discussion_of_silence_is_delivered(text):
    question = user()
    question.content = 'Explain silence and the words No response.'
    host = assistant([question], [text])
    host.reply_thread({})
    assert not is_silence_sentinel(text)
    host.tts.say.assert_called_once()
    assert host.event_manager.add_conversation_event.call_args.args[1] == text


@pytest.mark.parametrize('retry', [False, True])
@pytest.mark.parametrize('history', [[], [user()]])
def test_no_new_events_never_builds_prompt_or_generates(retry, history, records):
    for event in history:
        event.responded_at = 1
    host = assistant(history, [])
    host._speech_retry_requested = retry
    host.reply_thread({})
    assert host.llmModel.calls == 0
    host.prompt_generator.generate_prompt.assert_not_called()
    host.tts.say.assert_not_called()
    assert not host.is_replying and not host.reply_pending
    assert any(r.get('reason') == 'no_new_events' for r in records())


def completion(source='TARSExplorerTarget', address=42, count=8, **extra):
    data = dict(system='Synthetic', system_address=address, body_count=count,
                _guard={'triggered_at': 1000.0},
                **{'callout_kind' if source == 'TARSExplorerTarget' else 'finding_type': 'system_complete'})
    data.update(extra)
    return PluginEvent(plugin_event_name=source, plugin_event_content=data, responded_at=None)


@pytest.mark.parametrize('mode', ['observe', 'enforce'])
def test_system_completion_cross_source_identity_and_new_facts(pipeline, mode, records):
    host, run = pipeline(mode)
    host.llmModel.responses = iter(['FSS scan complete: 8 bodies.',
                                    'FSS scan complete: 9 bodies.',
                                    'FSS scan complete: 8 bodies.',
                                    'Stratum confirmed.'])
    first = completion()
    run(first)
    run(completion('TARSObservatoryFact', event_id='PRIVATE feed id'))
    assert host.llmModel.calls == 1
    key = host.speech_arbiter()._delivery_ledger.entity(first)
    assert key == (('address', 42), ('system', 'fss_complete'))
    assert 'body_id' not in first.plugin_event_content
    run(completion(count=9))  # Revised census is new evidence.
    run(completion(address=43))
    run(fact(kind='biology', confirmed_genuses=['Stratum']))
    assert host.llmModel.calls == host.tts.say.call_count == 4
    assert any(r.get('reason') == 'equivalent_facts' for r in records())
    assert 'PRIVATE' not in json.dumps(records())


@pytest.mark.parametrize('outcome', ['no_audio', 'output_failed', 'interrupted'])
def test_system_completion_retries_after_failed_output(pipeline, outcome):
    host, run = pipeline('observe', outcome)
    host.llmModel.responses = iter(['FSS scan complete: 8 bodies.'] * 2)
    run(completion()); run(completion('TARSObservatoryFact'))
    assert host.llmModel.calls == 2


def test_system_completion_requires_source_identity_and_explicit_coverage():
    ledger = DeliveryLedger()
    event = completion()
    _, claims = ledger.select([event])
    assert ledger.covered(claims, [event], 'An interesting destination.') == {}
    event.plugin_event_content.pop('system_address')
    event.plugin_event_content.pop('system')
    assert ledger.entity(event) is None


@pytest.mark.parametrize('text', SILENCE)
def test_real_chatter_candidate_abstains_before_quality_or_retry(integration, text):
    run = integration('observe', [text])
    run.plugin._chatter_quality_reason = Mock(side_effect=AssertionError('quality must not run'))
    run.fire()
    assert run.host.llmModel.calls == 1
    assert run.host.event_manager.incoming.empty()
    assert run.plugin._diagnostic_counts['model_skip'] == 1


def test_generation_and_delivery_ids_correlate_without_private_text(records):
    host = assistant([user()], ['PRIVATE answer', 'PRIVATE answer'])
    host.reply_thread({})
    host.reply_thread({})
    logs = records()
    requests = [r for r in logs if r['stage'] == 'reply_generation_requested']
    deliveries = [r for r in logs if r['stage'] == 'response_delivery']
    assert len({r['generation_id'] for r in requests}) == 2
    assert {r['generation_id'] for r in requests} == {r['generation_id'] for r in deliveries}
    assert len({r['delivery_id'] for r in deliveries}) == 2
    assert 'PRIVATE' not in json.dumps(logs)


@pytest.mark.parametrize('retry', [False, True])
@pytest.mark.parametrize('text', SILENCE)
def test_director_abstention_precedes_quality_logic(integration, text, retry):
    run = integration('observe', ['A rejected draft.', text] if retry else [text])
    run.plugin._main_covas_system_index = lambda messages: 0
    run.plugin._is_spontaneous_turn = lambda messages: True
    run.plugin._explicit_visual_request = lambda messages: None
    run.plugin._prepared_chatter_line = lambda messages: None
    run.plugin._chatter_quality_reason = Mock(return_value='weak')
    result = run.host.llmModel.generate(messages=[{'role': 'system', 'content': 'You are TARS.'}])
    assert result[0] == text
    assert run.host.llmModel.calls == (2 if retry else 1)
    assert run.plugin._chatter_quality_reason.call_count == (1 if retry else 0)


def test_deferred_event_survives_empty_history(pipeline):
    host, run = pipeline('observe')
    event = fact()
    host._speech_deferred = {('retained',): event}
    run()
    assert host.llmModel.calls == 1
    assert not host._speech_deferred


def test_tool_work_is_not_empty_history():
    from lib.Event import ToolEvent
    event = ToolEvent(request=[], results=[], responded_at=None)
    host = assistant([event], ['The requested tool has returned.'])
    host.reply_thread({})
    assert host.llmModel.calls == 1


def test_admission_has_a_system_semantic_identity_without_a_body():
    from lib.SpeechArbiter import identity_and_facts
    first, claims = identity_and_facts(completion())
    second, same = identity_and_facts(completion('TARSObservatoryFact'))
    revised, changed = identity_and_facts(completion(count=9))
    assert first == second == revised == (('address', '42'), 'system_complete')
    assert claims == same and claims != changed


def test_completed_system_composition_is_new_until_explicitly_covered():
    ledger = DeliveryLedger()
    event = completion()
    _, claims = ledger.select([event])
    ledger.confirm(ledger.covered(claims, [event], 'FSS scan complete: 8 bodies.'))
    event.plugin_event_content['system_composition'] = {'composition_confirmed': True, 'planets': 0}
    selected, claims = ledger.select([event])
    assert selected == [event]
    ledger.confirm(ledger.covered(claims, [event], 'FSS scan complete: 8 bodies, no planets.'))
    assert ledger.select([event])[0] == []


def test_playback_retry_keeps_generation_and_delivery_ids(monkeypatch, records):
    from test_tts_terminal_outcomes import run_until_idle
    obj, stream = player(monkeypatch, [b'12', b'34'])
    token = trace.current_generation.set(trace.new_id())
    try:
        line = obj.say('PRIVATE text')
    finally:
        trace.current_generation.reset(token)
    stream.write.side_effect = OSError('private device error')
    with pytest.raises(OSError):
        obj._playback_loop()
    stream.write.side_effect = None
    run_until_idle(obj)
    attempts = [r for r in records() if r['stage'] == 'tts_attempt_finished']
    assert len(attempts) == 2
    assert len({r['attempt_id'] for r in attempts}) == 2
    assert {r['generation_id'] for r in attempts} == {line.generation_id}
    assert {r['delivery_id'] for r in attempts} == {line.line_id}
    assert line.generation_id is not None
    assert 'PRIVATE' not in json.dumps(records())


def test_canonical_fss_payload_deduplicates_without_inventing_body(pipeline, rig):
    plugin = rig.plugin
    plugin._reset_system('Synthetic', 42)
    plugin._fss_complete = True
    plugin._confirmed_body_count = 8
    event = completion(**plugin._system_completion_payload())
    host, run = pipeline('observe')
    host.llmModel.responses = iter(['FSS scan complete: 8 bodies.'])
    run(event)
    run(event)
    assert host.llmModel.calls == 1
    assert host.tts.say.call_count == 1


def test_new_unrecognized_completion_details_fail_open(pipeline):
    host, run = pipeline('observe')
    host.llmModel.responses = iter(['FSS scan complete: 8 bodies.'] * 2)
    run(completion())
    run(completion(new_scientific_detail={'unrecognized': True}))
    assert host.llmModel.calls == 2


@pytest.mark.parametrize('text', ['Silence is useful during a scan.',
                                 'No response means the server has not answered.',
                                 'SKIP is a keyword you asked me to explain.'])
def test_real_director_keeps_user_requested_silence_discussion(integration, text):
    run = integration('observe', [text])
    run.plugin._main_covas_system_index = lambda messages: 0
    run.plugin._is_spontaneous_turn = lambda messages: False
    run.host.event_manager.get_short_term_memory.return_value = [user()]
    run.host.prompt_generator.generate_prompt.return_value = (
        [{'role': 'system', 'content': 'You are TARS.'},
         {'role': 'user', 'content': 'Explain silence and the phrase No response.'}],
        run.host.prompt_generator.generate_prompt.return_value[1])
    run.host.reply_thread({})
    assert run.host.llmModel.calls == 1
    run.host.tts.say.assert_called_once()
    assert run.host.event_manager.add_conversation_event.call_args.args[1] == text
