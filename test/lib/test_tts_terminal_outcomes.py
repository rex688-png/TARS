"""Deterministic TTS terminal outcomes; real queue/write paths, fake output device."""
from dataclasses import FrozenInstanceError
from unittest.mock import Mock

import pytest

from lib.TTS import TTS, TTSLine
from test_speech_trace import StopPlayback, player


def run_until_idle(obj):
    with pytest.raises(StopPlayback):
        obj._playback_loop()


def test_success_has_one_immutable_result_and_no_audibility_claim(monkeypatch):
    obj, stream = player(monkeypatch, [b'12', b'34', b'56'])
    done = Mock()
    line = obj.say('test', on_complete=done)
    assert line.result is None
    run_until_idle(obj)
    result = line.wait_for_result(timeout=0.01)
    assert result.outcome == 'completed'
    assert result.output_written
    assert result.written_bytes == 6
    assert result.output_drained is None
    assert len(result.attempts) == 1
    assert result.attempts[0].attempt_id
    assert result.ended_at >= result.started_at
    done.assert_called_once_with()
    with pytest.raises(FrozenInstanceError):
        result.outcome = 'interrupted'
    line.mark_completed()
    done.assert_called_once_with()


@pytest.mark.parametrize('mode,expected', [
    ('dropped', 'dropped'),
    ('empty', 'no_audio'),
    ('synthesis', 'synthesis_failed'),
    ('interrupted', 'interrupted'),
])
def test_terminal_non_success_outcomes(monkeypatch, mode, expected):
    obj, stream = player(monkeypatch, [] if mode == 'empty' else [b'12', b'34'])
    done = Mock()
    if mode == 'synthesis':
        obj.tts_model.synthesize = Mock(side_effect=RuntimeError('private synthesis failure'))
    if mode == 'interrupted':
        stream.write.side_effect = lambda *a, **k: obj.abort()
    line = obj.say('private', on_complete=done, drop_if=lambda: mode == 'dropped')
    run_until_idle(obj)
    result = line.wait_for_result(0.01)
    assert result.outcome == expected
    assert not result.output_written
    assert result.output_drained is None
    assert line.is_completed()
    done.assert_called_once_with()


def test_abort_drains_queue_settles_callback_exactly_once():
    import queue
    obj = TTS.__new__(TTS)
    obj.read_queue = queue.Queue()
    obj.is_aborted = False
    obj._abort_revision = 0
    done = Mock()
    line = obj.say('queued', on_complete=done)
    assert line.wait_for_result(0) is None
    obj.abort()
    obj.abort()
    assert line.wait_for_result(0.01).outcome == 'cancelled_before_start'
    assert line.result.attempts == ()
    assert not line.wait_for_speaking()
    done.assert_called_once_with()
    assert obj.read_queue.empty()


def test_device_failure_requeue_keeps_waiters_pending_until_real_terminal(monkeypatch):
    obj, stream = player(monkeypatch, [b'12', b'34'])
    done = Mock()
    started = Mock()
    line = obj.say('retry me', on_start=started, on_complete=done)
    stream.write.side_effect = OSError('private device failure')
    with pytest.raises(OSError):
        obj._playback_loop()
    assert line.result is None
    assert not line.is_completed()
    assert line.wait_for_result(0) is None
    assert len(line._attempts) == 1
    assert line._attempts[0].outcome == 'output_failed'
    assert obj.read_queue.qsize() == 1
    done.assert_not_called()

    stream.write.side_effect = None
    run_until_idle(obj)
    result = line.wait_for_result(0.01)
    assert result.outcome == 'completed'
    assert result.output_written
    assert len(result.attempts) == 2
    assert result.attempts[0].attempt_id != result.attempts[1].attempt_id
    started.assert_called_once_with()
    done.assert_called_once_with()


def test_repeated_output_failure_terminates_after_bounded_attempts(monkeypatch):
    obj, stream = player(monkeypatch, [b'12'])
    done = Mock()
    line = obj.say('never finishes', on_complete=done)
    stream.write.side_effect = OSError('private')
    for attempt in range(3):
        with pytest.raises(OSError):
            obj._playback_loop()
        assert line.is_completed() is (attempt == 2)
    assert line.result.outcome == 'output_failed'
    assert len(line.result.attempts) == 3
    assert obj.read_queue.empty()
    done.assert_called_once_with()


def test_legacy_wait_and_callbacks_are_compatible():
    done = Mock()
    line = TTSLine(on_complete=done)
    line.mark_speaking()
    assert line.wait_for_speaking()
    line.mark_completed()
    line.wait_for_completion()
    assert line.result.outcome == 'unknown'
    assert not line.result.output_written
    assert not line.is_speaking()
    done.assert_called_once_with()
    line.mark_completed()
    done.assert_called_once_with()


def test_audio_file_without_path_terminates_as_no_audio(monkeypatch):
    obj, stream = player(monkeypatch, [b'12'])
    done = Mock()
    obj.play_audio_file('', on_complete=done)
    run_until_idle(obj)
    done.assert_called_once_with()
    assert stream.write.call_count == 0
