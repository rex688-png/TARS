"""Failure-injection regressions using real workers and fake microphone streams."""
import queue
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from src.lib.EDJournal import EDJournal
from src.lib.STT import STT


def wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    assert predicate()


@pytest.mark.parametrize('at_startup', [False, True])
def test_partial_journal_record_survives_append(tmp_path, at_startup):
    path = tmp_path / 'Journal.2000.log'
    path.write_text('{"event":"First"}\n', encoding='utf8')
    partial = '{"event":"Second",'
    if at_startup:
        with path.open('a') as f:
            f.write(partial)
    journal = EDJournal(str(tmp_path))
    try:
        if not at_startup:
            with path.open('a') as f:
                f.write(partial)
            time.sleep(.15)  # Let the old reader consume the incomplete line.
        with path.open('a') as f:
            f.write('"timestamp":"2000-01-01T00:00:00Z"}\n')
        event = journal.events.get(timeout=2)
        assert event['event'] == 'Second'
        assert event['id'].endswith('.000002')
        assert journal.events.empty()
    finally:
        if hasattr(journal, 'stop'):
            journal.stop()


def test_reader_recovers_without_replaying_consumed_records(tmp_path, monkeypatch):
    path = tmp_path / 'Journal.2000.log'
    path.write_text('{"event":"History"}\n', encoding='utf8')
    original = EDJournal.augment_event
    failed = threading.Event()

    def augment(self, entry):
        if entry['event'] == 'Retry' and not failed.is_set():
            failed.set()
            raise OSError('simulated disconnected journal read')
        return original(self, entry)

    monkeypatch.setattr(EDJournal, 'augment_event', augment)
    journal = EDJournal(str(tmp_path))
    try:
        with path.open('a') as f:
            f.write('{"event":"Live"}\n{"event":"Retry"}\n')
        assert journal.events.get(timeout=2)['event'] == 'Live'
        assert journal.events.get(timeout=3)['event'] == 'Retry'
        assert journal.events.empty()
    finally:
        if hasattr(journal, 'stop'):
            journal.stop()


def test_reader_skips_complete_malformed_record_and_stops(tmp_path):
    journal = EDJournal(str(tmp_path))
    try:
        path = tmp_path / 'Journal.2000.log'
        path.write_text('broken\n[]\n{"event":"Good"}\n', encoding='utf8')
        event = journal.events.get(timeout=2)
        assert event['event'] == 'Good'
        assert event['id'].endswith('.000003')
    finally:
        if hasattr(journal, 'stop'):
            journal.stop()
    assert not journal._reader_thread.is_alive()


def make_stt(monkeypatch):
    monkeypatch.setattr('src.lib.STT.SileroVoiceActivityDetector', lambda: Mock(chunk_bytes=lambda: 1024))
    return STT(Mock(), 'fake')


def test_stt_instances_never_share_transcriptions(monkeypatch):
    first, second = make_stt(monkeypatch), make_stt(monkeypatch)
    first.resultQueue.put('prior session input')
    assert second.resultQueue.empty()


@pytest.mark.parametrize('mode', ['ptt', 'continuous'])
def test_microphone_closed_on_read_failure(monkeypatch, mode):
    stt = make_stt(monkeypatch)
    source = Mock()
    stt._get_microphone = lambda: source
    stt._read_stream_buffer = Mock(side_effect=OSError('device disconnected'))
    stt.listening = True
    with pytest.raises(OSError):
        (stt._listen_once_thread if mode == 'ptt' else stt._listen_continuous_loop)()
    source.close.assert_called_once()
    assert stt.recording is False


def test_ptt_microphone_closed_on_provider_failure(monkeypatch):
    stt = make_stt(monkeypatch)
    source = Mock()
    stt._get_microphone = lambda: source
    stt._read_stream_buffer = lambda _: b''
    stt._transcribe = Mock(side_effect=RuntimeError('provider unavailable'))
    with pytest.raises(RuntimeError):
        stt._listen_once_thread()
    source.close.assert_called_once()
    assert stt.recording is False


def test_action_registry_does_not_retain_prior_session_actuators(monkeypatch):
    from src.lib.ActionManager import ActionManager
    monkeypatch.setattr('src.lib.ActionManager.KeyValueStore', Mock())
    first, second = ActionManager(), ActionManager()
    actuator = Mock(return_value='executed')
    first.set_allowed_actions({'fireWeapons': True})
    first.registerAction('oldControl', 'Prior session', {}, actuator, permission='fireWeapons')
    assert 'oldControl' not in second.actions
    from openai.types.chat import ChatCompletionMessageFunctionToolCall
    call = ChatCompletionMessageFunctionToolCall(id='audit', type='function',
        function={'name': 'oldControl', 'arguments': '{}'})
    result = second.runAction(call, {})
    assert 'does not exist' in result['content']
    actuator.assert_not_called()


def test_tts_quit_stops_idle_worker_and_releases_device(monkeypatch):
    from src.lib.TTS import TTS
    audio, stream = Mock(), Mock()
    audio.open.return_value = stream
    audio.get_sample_size.return_value = 2
    monkeypatch.setattr('src.lib.TTS.pyaudio.PyAudio', lambda: audio)
    monkeypatch.setattr(TTS, '_get_output_device_index', lambda _: None)
    tts = TTS()
    wait_until(lambda: audio.open.called)
    tts.quit()
    tts.quit()  # Repeated cleanup remains harmless.
    assert not tts._worker_thread.is_alive()
    stream.close.assert_called_once()
    audio.terminate.assert_called_once()
    assert not tts.get_is_playing()


def test_tts_failed_device_stream_is_closed_before_retry(monkeypatch):
    from src.lib.TTS import TTS
    audio, stream = Mock(), Mock()
    audio.open.return_value = stream
    audio.get_sample_size.return_value = 2
    stream.start_stream.side_effect = OSError('device removed')
    monkeypatch.setattr('src.lib.TTS.pyaudio.PyAudio', lambda: audio)
    monkeypatch.setattr(TTS, '_get_output_device_index', lambda _: None)
    tts = TTS()
    wait_until(lambda: stream.close.called)
    tts.quit()
    assert not tts._worker_thread.is_alive()
    stream.close.assert_called_once()
    audio.terminate.assert_called_once()


def test_muting_discards_incomplete_voice_phrase(monkeypatch):
    stt = make_stt(monkeypatch)
    source = Mock()
    stt._get_microphone = lambda: source
    stt.phrase_end_pause = .1
    stt.vad = lambda chunk: 1 if chunk == b'v' else 0
    stt._transcribe = Mock(return_value='unwanted prior phrase')
    chunks = iter([b'v'] * 8 + [b'mute'] + [b's'] * 20)
    def read(_):
        chunk = next(chunks, b'')
        stt.continuous_listening_paused = chunk == b'mute'
        if not chunk:
            stt.listening = False
        return chunk
    stt._read_stream_buffer = read
    stt.listening = True
    stt._listen_continuous_loop()
    stt._transcribe.assert_not_called()
    source.close.assert_called_once()


def test_stt_repeated_start_keeps_single_worker_and_stop_interrupts_backoff(monkeypatch):
    stt = make_stt(monkeypatch)
    failed = threading.Event()
    def disconnected():
        failed.set()
        raise OSError('disconnected')
    stt._listen_continuous_loop = disconnected
    stt.listen_continuous()
    assert failed.wait(1)
    worker = stt._worker_thread
    stt.listen_continuous()
    assert stt._worker_thread is worker
    stt.stop()
    assert not worker.is_alive()
    stt.listen_continuous()
    assert stt._worker_thread is worker  # Closed instance cannot restart.


@pytest.mark.parametrize('startup_fails', [False, True])
def test_chat_cleanup_survives_startup_and_cleanup_failure(monkeypatch, startup_fails):
    # Exercise the production orchestration method without importing the CLI's
    # eager device/provider dependencies into this fault-injection harness.
    import ast
    from types import SimpleNamespace, MethodType
    tree = ast.parse((Path(__file__).resolve().parents[2] / 'src' / 'Chat.py').read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Chat')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
    namespace = {'log': Mock(), 'speech_trace': Mock()}
    exec(compile(ast.Module(body=[method], type_ignores=[]), 'Chat.run', 'exec'), namespace)
    chat = SimpleNamespace()
    chat.run = MethodType(namespace['run'], chat)
    chat._run = Mock(side_effect=RuntimeError('startup failed') if startup_fails else None)
    for name in ('controller_manager', 'stt', 'plugin_manager', 'jn', 'status_parser', 'event_manager', 'tts'):
        setattr(chat, name, Mock())
    chat.plugin_helper = Mock()
    chat.stt.stop.side_effect = OSError('cleanup failed')
    if startup_fails:
        with pytest.raises(RuntimeError, match='startup failed'):
            chat.run()
    else:
        chat.run()
    chat.controller_manager._stop_listeners.assert_called_once()
    chat.plugin_manager.on_chat_stop.assert_called_once_with(chat.plugin_helper)
    chat.jn.stop.assert_called_once()
    chat.status_parser.stop.assert_called_once()
    chat.event_manager.stop.assert_called_once()
    chat.tts.quit.assert_called_once()


def test_late_tts_submission_after_shutdown_settles_without_playback(monkeypatch):
    from src.lib.TTS import TTS
    audio = Mock()
    audio.get_sample_size.return_value = 2
    monkeypatch.setattr('src.lib.TTS.pyaudio.PyAudio', lambda: audio)
    monkeypatch.setattr(TTS, '_get_output_device_index', lambda _: None)
    tts = TTS()
    tts.quit()
    completed = Mock()
    line = tts.say('late provider result', on_complete=completed)
    tts.play_audio_file('late.wav', on_complete=completed)
    assert line.wait_for_result(.1).outcome == 'cancelled_before_start'
    assert tts.read_queue.empty()
    assert completed.call_count == 2


def test_idle_event_poll_does_not_commit_or_rewrite_projection_store():
    from src.lib.EventManager import EventManager
    manager = EventManager.__new__(EventManager)
    manager._processing_lock = threading.Lock()
    manager.incoming = queue.Queue()
    manager.pending, manager.processed = [], []
    manager.short_term_memory = Mock()
    manager.save_projections = Mock()
    assert manager.process() is None
    manager.short_term_memory.commit.assert_not_called()
    manager.save_projections.assert_not_called()


def test_status_watcher_stop_releases_thread(tmp_path):
    from src.lib.StatusParser import StatusParser
    (tmp_path / 'Status.json').write_text('{"Flags":0}', encoding='utf8')
    parser = StatusParser(str(tmp_path))
    parser.stop()
    parser.stop()
    assert not parser.watch_thread.is_alive()


def test_projection_timer_stop_releases_thread():
    from src.lib.EventManager import EventManager
    manager = EventManager.__new__(EventManager)
    manager._timer_stop_event = threading.Event()
    manager._timer_interval = .01
    manager.process_timer_tick = Mock()
    manager._timer_thread = threading.Thread(target=manager._run_projection_timer)
    manager._timer_thread.start()
    wait_until(lambda: manager.process_timer_tick.called)
    manager.stop()
    manager.stop()
    assert not manager._timer_thread.is_alive()
