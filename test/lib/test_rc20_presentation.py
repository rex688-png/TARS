"""Phase 1 host presentation regressions; synthetic text and fake providers only."""
import copy
from unittest.mock import Mock

import pytest

from test_speech_arbiter import arbiter, clock, finding
from test_speech_trace import assistant, user, records, player, StopPlayback
from lib.BodyPresentation import format_body_identifiers, known_body_labels
from lib.ResponsePresentation import is_silence_sentinel
from lib.SpeechText import normalize_spoken_quantities
from lib.Logger import ModelUsageStats


@pytest.mark.parametrize('mode', ['off', 'observe', 'enforce'])
@pytest.mark.parametrize('value', ['SKIP', ' skip ', '"SKIP"', "'Skip'", '“sKiP”', '`SKIP`', 'SKIP.', '" skip "'])
def test_standalone_sentinel_is_never_spoken_displayed_or_saved(mode, value, arbiter, records):
    event = finding()
    host = assistant([event], [value])
    host.config['speech_director_mode'] = mode
    host._speech_arbiter = arbiter
    host.reply_thread({})
    host.tts.say.assert_not_called()
    host.event_manager.add_conversation_event.assert_not_called()
    host.event_manager.add_assistant_speaking.assert_not_called()
    host.event_manager.add_assistant_complete_event.assert_called_once()
    host.event_manager.short_term_memory.replied_before.assert_called_once()
    assert not host.is_replying and not host.reply_pending
    assert arbiter._active is None and not arbiter._recent
    assert any(r.get('reason') == 'silence_sentinel' for r in records())


@pytest.mark.parametrize('answer', ['I will skip that waypoint.', 'Do not skip the next jump.', 'Skipping is optional.', 'SKIP is the requested keyword.'])
def test_legitimate_skip_requests_and_sentences_keep_working(answer):
    question = user()
    question.content = 'Can you skip that waypoint?'
    host = assistant([question], [answer])
    host.reply_thread({})
    assert not is_silence_sentinel(answer)
    host.tts.say.assert_called_once()
    assert host.event_manager.add_conversation_event.call_args.args[1] == answer


def test_sentinel_text_does_not_discard_real_tool_actions():
    host = assistant([user()], [])
    actions = [{'id': 'test-tool'}]
    host.llmModel.generate = Mock(return_value=('SKIP', actions, ModelUsageStats()))
    host.execute_actions = Mock()
    host.reply_thread({})
    host.execute_actions.assert_called_once_with(actions, {})
    host.tts.say.assert_not_called()
    host.event_manager.add_conversation_event.assert_not_called()


def test_busy_retry_then_sentinel_preserves_new_question_pending(arbiter):
    active = arbiter.reserve([finding(body=7)], {}, 'enforce')
    event = finding(body=8)
    event.processed_at = 1
    host = assistant([event], ['SKIP', 'Your answer, Commander.'])
    host.disabled_game_events = []
    host.config['speech_director_mode'] = 'enforce'
    host._speech_arbiter = arbiter
    host.reply_thread({})
    assert host.reply_pending and host.llmModel.calls == 0
    arbiter.finish(active)
    question = user()
    question.processed_at = 2
    original = host.llmModel.generate
    def generate(*args, **kwargs):
        if host.llmModel.calls == 0:
            host.on_event(question, {})
        return original(*args, **kwargs)
    host.llmModel.generate = generate
    host.reply_thread({})
    assert host.reply_pending
    host.tts.say.assert_not_called()
    host.event_manager.short_term_memory.replied_before.assert_called_once_with(1)
    event.responded_at = 1
    host.event_manager.get_short_term_memory.return_value = [question, event]
    host.reply_thread({})
    assert host.llmModel.calls == 2 and not host.reply_pending
    host.tts.say.assert_called_once()
    assert host.event_manager.add_conversation_event.call_count == 1


@pytest.mark.parametrize('source,display,spoken', [
    ('Planet A five', 'Planet A5', 'Planet A five'),
    ('body A two', 'body A2', 'body A two'),
    ('World B three', 'World B3', 'World B three'),
    ('planet AB four', 'planet AB4', 'planet AB four'),
    ('A five is terraformable.', 'A5 is terraformable.', 'A five is terraformable.'),
    ('A5', 'A5', 'A five'),
])
def test_verified_body_labels_have_separate_display_and_speech(source, display, spoken):
    labels = {'A5'}
    assert format_body_identifiers(source, known_labels=labels) == display
    assert format_body_identifiers(display, known_labels=labels, spoken=True) == spoken


@pytest.mark.parametrize('text', [
    'A five star rating', 'A two-hour flight', 'class A five', 'module A5',
    'Col 285 Sector AB 12-3', 'HIP 22460 A 1', 'HIP 22460 A five',
    'ship FIX-01, 5A FSD, Krait Mk II, M5 V', 'A five', 'A5',
    'body A5 a', 'planet A one hundred', 'planet A05', 'body AB00', 'coordinates -12.5, 4.2',
])
def test_ambiguous_text_and_non_body_identifiers_are_untouched(text):
    assert format_body_identifiers(text) == text
    assert format_body_identifiers(text, spoken=True) == text


@pytest.mark.parametrize('text,expected', [
    ('95,200,000 credits', 'ninety-five million, two hundred thousand credits'),
    ('7,472 ly', 'seven thousand, four hundred and seventy-two light-years'),
    ('4,123,456,789 credits', 'four billion, one hundred and twenty-three million, four hundred and fifty-six thousand, seven hundred and eighty-nine credits'),
    ('12.05 ly', 'twelve point zero five light-years'),
    ('99.5%', 'ninety-nine point five percent'),
    ('-0.3 ly', 'minus zero point three light-years'),
    ('+12.5 ly', 'plus twelve point five light-years'),
    ('Gravity: 0.3 g', 'Gravity: zero point three standard gravities'),
    ('pressure: 0.01 atm', 'pressure: zero point zero one atmospheres'),
    ('pressure: 1 Pa', 'pressure: one pascal'),
])
def test_actual_quantity_gaps_without_regressing_working_ranges(text, expected):
    assert normalize_spoken_quantities(text) == expected


@pytest.mark.parametrize('text', ['Col 285 Sector AB 12-3', 'HIP 22460 A 1', 'module 5A', 'FIX-01', '0.3 g', '95,20 credits', 'HIP-12.5 ly', '12PA', '2ATM'])
def test_quantity_normalization_does_not_rewrite_designations_or_partial_numbers(text):
    assert normalize_spoken_quantities(text) == text


def test_host_display_and_real_tts_keep_values_and_journal_data_separate(monkeypatch):
    states = {'Location': {'StarSystem': 'HIP 22460', 'Body': 'HIP 22460 A5'}}
    snapshot = copy.deepcopy(states)
    answer = 'Planet A five: 95,200,000 credits (base: 19,200,000, bonus: 76,000,000); 7,472 ly.'
    host = assistant([user()], [answer])
    host.reply_thread(states)
    visible = host.event_manager.add_conversation_event.call_args.args[1]
    assert visible.startswith('Planet A5: 95,200,000 credits')
    assert '19,200,000' in visible and '76,000,000' in visible and '7,472 ly' in visible
    assert states == snapshot and known_body_labels(states, []) == {'A5'}
    queued = host.tts.say.call_args.args[0]
    assert queued.startswith('Planet A five: 95,200,000 credits')
    tts, stream = player(monkeypatch, [b'12', b'34'])
    tts.tts_model.synthesize = Mock(return_value=iter([b'12', b'34']))
    line = tts.say(queued)
    with pytest.raises(StopPlayback):
        tts._playback_loop()
    spoken = tts.tts_model.synthesize.call_args.args[0]
    assert 'ninety-five million, two hundred thousand credits' in spoken
    assert 'base: nineteen million, two hundred thousand' in spoken
    assert 'bonus: seventy-six million' in spoken
    assert 'seven thousand, four hundred and seventy-two light-years' in spoken
    assert line.result.outcome == 'completed' and line.result.output_written
    assert stream.write.call_count == 2
